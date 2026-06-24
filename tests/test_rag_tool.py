import importlib
import sys
import types


def import_rag_tool(monkeypatch):
    fake_crewai = types.ModuleType("crewai")
    fake_tools = types.ModuleType("crewai.tools")

    class BaseTool:
        def __init__(self, **kwargs):
            pass

    fake_tools.BaseTool = BaseTool
    fake_crewai.tools = fake_tools
    monkeypatch.setitem(sys.modules, "crewai", fake_crewai)
    monkeypatch.setitem(sys.modules, "crewai.tools", fake_tools)
    sys.modules.pop("rag_tool", None)
    return importlib.import_module("rag_tool")


def tool_with_collection(rag_module, collection):
    tool = rag_module.ChromaRAGTool()
    object.__setattr__(tool, "_client", object())
    object.__setattr__(tool, "_openai_ef", object())
    object.__setattr__(tool, "_collection", collection)
    return tool


def test_rag_tool_returns_clear_message_when_no_results(monkeypatch):
    rag_module = import_rag_tool(monkeypatch)

    class EmptyCollection:
        def query(self, **kwargs):
            assert kwargs["query_texts"] == ["support automation"]
            assert kwargs["n_results"] == rag_module.RAG_SEMANTIC_CANDIDATES
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        def get(self, **kwargs):
            assert kwargs["include"] == ["documents", "metadatas"]
            return {"ids": [], "documents": [], "metadatas": []}

    result = tool_with_collection(rag_module, EmptyCollection())._run("support automation")

    assert result == "Релевантных бизнес-кейсов не найдено."


def test_chunk_text_uses_700_words_and_120_word_overlap(monkeypatch):
    rag_module = import_rag_tool(monkeypatch)

    words = [f"w{i}" for i in range(820)]
    chunks = rag_module.chunk_text(" ".join(words))

    first_chunk = chunks[0].split()
    second_chunk = chunks[1].split()
    assert len(first_chunk) == 700
    assert first_chunk[-120:] == second_chunk[:120]
    assert second_chunk[-1] == "w819"


def test_chunk_records_preserves_single_chunk_ids(monkeypatch):
    rag_module = import_rag_tool(monkeypatch)

    docs, metadatas, ids = rag_module.chunk_records(
        ["short document", " ".join(f"w{i}" for i in range(820))],
        [{"title": "Short"}, {"title": "Long"}],
        ["short-id", "long-id"],
    )

    assert ids[0] == "short-id"
    assert ids[1:] == ["long-id::chunk-0", "long-id::chunk-1"]
    assert metadatas[0]["source_id"] == "short-id"
    assert metadatas[1]["chunk_count"] == 2


def test_hybrid_search_merges_semantic_and_bm25_with_rrf(monkeypatch):
    rag_module = import_rag_tool(monkeypatch)

    monkeypatch.setattr(rag_module, "_rank_bm25", lambda query, rows, limit: ["doc-bm25", "doc-semantic"])

    class FakeCollection:
        def query(self, **kwargs):
            assert kwargs["query_texts"] == ["support automation"]
            assert kwargs["n_results"] == rag_module.RAG_SEMANTIC_CANDIDATES
            return {
                "ids": [["doc-semantic"]],
                "documents": [["Doc semantic body"]],
                "metadatas": [[
                    {"title": "Semantic Case", "category": "Support"},
                ]],
                "distances": [[0.2]],
            }

        def get(self, **kwargs):
            assert kwargs["include"] == ["documents", "metadatas"]
            return {
                "ids": ["doc-semantic", "doc-bm25"],
                "documents": ["Doc semantic body", "Doc BM25 body"],
                "metadatas": [
                    {"title": "Semantic Case", "category": "Support"},
                    {"title": "BM25 Case", "category": "Automation"},
                ],
            }

    result = tool_with_collection(rag_module, FakeCollection())._run("support automation")

    assert "КЕЙС 1" in result
    assert "Название: Semantic Case" in result
    assert "Категория: Support" in result
    assert "релевантность: 80%" in result
    assert "КЕЙС 2" in result
    assert "Название: BM25 Case" in result
    assert "bm25=1" in result


def test_format_results_clamps_distance_relevance(monkeypatch):
    rag_module = import_rag_tool(monkeypatch)

    result = rag_module.format_results([
        rag_module.RetrievedCase(
            doc_id="case-1",
            document="Doc body",
            metadata={"title": "Case 1", "category": "Support"},
            distance=1.7,
        )
    ])

    assert "Название: Case 1" in result
    assert "релевантность: 0%" in result


def test_reranking_falls_back_when_enabled_model_unavailable(monkeypatch):
    rag_module = import_rag_tool(monkeypatch)
    fake_sentence_transformers = types.ModuleType("sentence_transformers")

    class BrokenCrossEncoder:
        def __init__(self, model_name):
            raise RuntimeError(f"model unavailable: {model_name}")

    fake_sentence_transformers.CrossEncoder = BrokenCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_sentence_transformers)
    monkeypatch.setattr(rag_module, "ENABLE_RERANKING", True)
    rows = [
        rag_module.RetrievedCase(
            doc_id="case-1",
            document="Doc body",
            metadata={},
            rrf_score=0.9,
        )
    ]

    assert rag_module._maybe_rerank("support automation", rows) == rows
