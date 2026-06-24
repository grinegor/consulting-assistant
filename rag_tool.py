import os
import re
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.utils import embedding_functions
from crewai.tools import BaseTool
from dotenv import load_dotenv

from logging_config import configure_logging, get_logger

load_dotenv()
configure_logging()
logger = get_logger(__name__)

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
BUSINESS_CASES_COLLECTION = os.getenv("BUSINESS_CASES_COLLECTION", "business_cases")
RAG_CHUNK_WORDS = int(os.getenv("RAG_CHUNK_WORDS", "700"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
RAG_SEMANTIC_CANDIDATES = int(os.getenv("RAG_SEMANTIC_CANDIDATES", "20"))
RAG_BM25_CANDIDATES = int(os.getenv("RAG_BM25_CANDIDATES", "20"))
RAG_RRF_K = int(os.getenv("RAG_RRF_K", "60"))
ENABLE_RERANKING = os.getenv("RAG_ENABLE_RERANKING", os.getenv("ENABLE_RERANKING", "false")).lower() in {"1", "true", "yes"}
RERANKER_MODEL = os.getenv("RAG_RERANKER_MODEL", os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))


@dataclass(frozen=True)
class RetrievedCase:
    doc_id: str
    document: str
    metadata: dict[str, Any]
    distance: float | None = None
    semantic_rank: int | None = None
    bm25_rank: int | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\wА-Яа-яЁё]+", text.lower())


def chunk_text(text: str, chunk_words: int = RAG_CHUNK_WORDS, overlap: int = RAG_CHUNK_OVERLAP) -> list[str]:
    """Split long documents into overlapping word chunks for RAG indexing."""
    words = text.split()
    if chunk_words <= 0:
        raise ValueError("chunk_words must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_words:
        raise ValueError("overlap must be smaller than chunk_words")
    if len(words) <= chunk_words:
        return [text.strip()] if text.strip() else []

    chunks = []
    step = chunk_words - overlap
    for start in range(0, len(words), step):
        chunk = " ".join(words[start:start + chunk_words]).strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_words >= len(words):
            break
    return chunks


def chunk_records(
    documents: list[str],
    metadatas: list[dict[str, Any]],
    ids: list[str],
    chunk_words: int = RAG_CHUNK_WORDS,
    overlap: int = RAG_CHUNK_OVERLAP,
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    chunked_docs: list[str] = []
    chunked_metadatas: list[dict[str, Any]] = []
    chunked_ids: list[str] = []

    for doc, metadata, doc_id in zip(documents, metadatas, ids):
        chunks = chunk_text(doc, chunk_words=chunk_words, overlap=overlap)
        total_chunks = len(chunks)
        for index, chunk in enumerate(chunks):
            chunk_id = doc_id if total_chunks == 1 else f"{doc_id}::chunk-{index}"
            chunk_metadata = {
                **metadata,
                "source_id": doc_id,
                "chunk_index": index,
                "chunk_count": total_chunks,
            }
            chunked_docs.append(chunk)
            chunked_metadatas.append(chunk_metadata)
            chunked_ids.append(chunk_id)

    return chunked_docs, chunked_metadatas, chunked_ids


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = RAG_RRF_K,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked_ids in ranked_lists:
        for rank, doc_id in enumerate(ranked_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def _extract_chroma_rows(results: dict[str, Any]) -> list[RetrievedCase]:
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    ids = (results.get("ids") or [[]])[0]

    rows = []
    for index, document in enumerate(documents):
        doc_id = ids[index] if index < len(ids) else f"semantic-{index}"
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        distance = distances[index] if index < len(distances) else None
        rows.append(
            RetrievedCase(
                doc_id=doc_id,
                document=document,
                metadata=metadata,
                distance=distance,
                semantic_rank=index + 1,
            )
        )
    return rows


def _rank_bm25(query: str, rows: list[RetrievedCase], limit: int) -> list[str]:
    if not rows:
        return []
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("bm25_unavailable", dependency="rank_bm25")
        return []

    corpus = [tokenize(row.document) for row in rows]
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    scores = BM25Okapi(corpus).get_scores(query_tokens)
    ranked = sorted(
        zip(rows, scores),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [row.doc_id for row, score in ranked[:limit] if score > 0]


def _safe_collection_get(collection) -> list[RetrievedCase]:
    try:
        corpus = collection.get(include=["documents", "metadatas"])
    except Exception as exc:
        logger.warning("bm25_corpus_load_failed", error=str(exc))
        return []

    documents = corpus.get("documents") or []
    metadatas = corpus.get("metadatas") or []
    ids = corpus.get("ids") or []
    rows = []
    for index, document in enumerate(documents):
        rows.append(
            RetrievedCase(
                doc_id=ids[index] if index < len(ids) else f"bm25-{index}",
                document=document,
                metadata=metadatas[index] if index < len(metadatas) and metadatas[index] else {},
            )
        )
    return rows


def _merge_results(
    semantic_rows: list[RetrievedCase],
    bm25_rows: list[RetrievedCase],
    bm25_ranked_ids: list[str],
    limit: int,
) -> list[RetrievedCase]:
    rows_by_id = {row.doc_id: row for row in bm25_rows}
    rows_by_id.update({row.doc_id: row for row in semantic_rows})

    semantic_ids = [row.doc_id for row in semantic_rows]
    scores = reciprocal_rank_fusion([semantic_ids, bm25_ranked_ids])
    bm25_rank_by_id = {doc_id: rank for rank, doc_id in enumerate(bm25_ranked_ids, start=1)}

    merged = []
    for doc_id, score in scores.items():
        row = rows_by_id[doc_id]
        merged.append(
            RetrievedCase(
                doc_id=row.doc_id,
                document=row.document,
                metadata=row.metadata,
                distance=row.distance,
                semantic_rank=row.semantic_rank,
                bm25_rank=bm25_rank_by_id.get(doc_id),
                rrf_score=score,
                rerank_score=row.rerank_score,
            )
        )
    return sorted(merged, key=lambda row: row.rrf_score, reverse=True)[:limit]


def _maybe_rerank(query: str, rows: list[RetrievedCase]) -> list[RetrievedCase]:
    if not ENABLE_RERANKING or not rows:
        return rows
    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(RERANKER_MODEL)
        scores = model.predict([(query, row.document) for row in rows])
    except Exception as exc:
        logger.warning("reranker_unavailable", model=RERANKER_MODEL, error=str(exc))
        return rows

    reranked = [
        RetrievedCase(
            doc_id=row.doc_id,
            document=row.document,
            metadata=row.metadata,
            distance=row.distance,
            semantic_rank=row.semantic_rank,
            bm25_rank=row.bm25_rank,
            rrf_score=row.rrf_score,
            rerank_score=float(score),
        )
        for row, score in zip(rows, scores)
    ]
    return sorted(reranked, key=lambda row: row.rerank_score or 0.0, reverse=True)


def format_results(rows: list[RetrievedCase]) -> str:
    if not rows:
        return "Релевантных бизнес-кейсов не найдено."

    formatted = []
    for index, row in enumerate(rows, start=1):
        distance = row.distance if row.distance is not None else 1.0 - min(row.rrf_score, 1.0)
        relevance = 1 - min(max(distance, 0.0), 1.0)
        formatted.append(f"""
    ┌────────────── КЕЙС {index} (релевантность: {relevance:.0%}) ──────────────┐
    📌 Название: {row.metadata.get('title', 'Без названия')}
    📂 Категория: {row.metadata.get('category', 'Не указана')}
    🔎 Ранги: semantic={row.semantic_rank or '-'}, bm25={row.bm25_rank or '-'}, rrf={row.rrf_score:.4f}
    📝 Содержание:
    {row.document[:1200]}...
    └────────────────────────────────────────────────────────────────┘
    """)
    return "\n".join(formatted)


class ChromaRAGTool(BaseTool):
    name: str = "Business Cases Search"
    description: str = """
    Ищет релевантные бизнес-кейсы по внедрению ИИ в базе знаний.
    Используйте этот инструмент, когда нужно найти примеры из практики,
    методологии оптимизации или конкретные реализации ИИ-решений.
    Вход: поисковый запрос (строка).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_client", None)
        object.__setattr__(self, "_openai_ef", None)
        object.__setattr__(self, "_collection", None)

    def _ensure_initialized(self):
        if self._client is None:
            object.__setattr__(self, "_client", chromadb.PersistentClient(path=CHROMA_PATH))
            object.__setattr__(self, "_openai_ef", embedding_functions.OpenAIEmbeddingFunction(
                api_key=os.getenv("OPENAI_API_KEY"),
                model_name="text-embedding-3-small",
            ))
            object.__setattr__(self, "_collection", self._client.get_collection(
                name=BUSINESS_CASES_COLLECTION,
                embedding_function=self._openai_ef,
            ))

    def search(self, query: str, n_results: int = 5) -> list[RetrievedCase]:
        self._ensure_initialized()
        logger.info("rag_search_started", query_length=len(query or ""), n_results=n_results)

        semantic_results = self._collection.query(
            query_texts=[query],
            n_results=max(n_results, RAG_SEMANTIC_CANDIDATES),
        )
        semantic_rows = _extract_chroma_rows(semantic_results)
        corpus_rows = _safe_collection_get(self._collection)
        bm25_ranked_ids = _rank_bm25(query, corpus_rows, RAG_BM25_CANDIDATES)
        merged = _merge_results(semantic_rows, corpus_rows, bm25_ranked_ids, n_results)
        reranked = _maybe_rerank(query, merged)[:n_results]

        logger.info(
            "rag_search_finished",
            query_length=len(query or ""),
            semantic_results=len(semantic_rows),
            bm25_results=len(bm25_ranked_ids),
            returned=len(reranked),
            reranking_enabled=ENABLE_RERANKING,
        )
        return reranked

    def _run(self, query: str) -> str:
        return format_results(self.search(query, n_results=5))


if __name__ == "__main__":
    tool = ChromaRAGTool()
    logger.info("rag_manual_result", result=tool._run("автоматизация поддержки клиентов"))
