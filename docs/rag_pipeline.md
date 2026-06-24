# RAG Pipeline

The RAG pipeline turns curated Notion business cases into searchable context for the multi-agent consultation workflow.

## Source Of Truth

Notion is treated as the editable source of truth for business cases. Each page is expected to contain fields such as:

- Name or Название
- Category
- Use Case
- Summary
- Implementation
- Pros
- Cons
- Tools
- Source
- Date

## Full Rebuild

Use the full rebuild script when the local ChromaDB collection should be recreated from scratch:

```bash
python notion_to_chromadb.py
```

The script:

1. queries the configured Notion database;
2. maps Notion properties into normalized case dictionaries;
3. builds document text, metadata, and ids;
4. chunks long records into 700-word windows with 120-word overlap;
5. recreates the `business_cases` ChromaDB collection;
6. stores chunks with OpenAI embeddings.

## Incremental Sync

Use incremental sync during normal development:

```bash
python sync_notion_to_chromadb.py
```

The script:

1. loads `sync_state.json`;
2. fetches all Notion pages;
3. selects pages edited after the last sync timestamp;
4. chunks long records into 700-word windows with 120-word overlap;
5. upserts updated chunks into ChromaDB;
6. writes the new sync timestamp.

## Retrieval

`rag_tool.py` loads the `business_cases` collection and retrieves candidates with a hybrid strategy:

1. Semantic retrieval from ChromaDB over OpenAI embeddings.
2. BM25 lexical retrieval over the locally stored Chroma documents.
3. Reciprocal Rank Fusion (RRF) to merge semantic and lexical rankings.
4. Optional cross-encoder reranking with `cross-encoder/ms-marco-MiniLM-L-6-v2`.

Reranking is disabled by default because it can download a heavy model and slow the bot. To enable it locally:

```bash
pip install -r requirements-rerank.txt
RAG_ENABLE_RERANKING=true python telegram_bot.py
```

Results are formatted with title, category, truncated content, rank traces, and an approximate relevance score before being passed back to the Researcher agent.

## Offline Evaluation

The repository includes a deterministic synthetic RAG eval that does not call ChromaDB, Notion, OpenAI embeddings, or live services:

```bash
.venv/bin/python -m evals.portfolio_rag_eval --skip-llm
```

The eval uses 25 portfolio-safe questions and 12 synthetic business-case documents. It compares a title/category-only baseline with an improved full-text retrieval pass and reports `precision@5`, `recall@5`, and metric deltas. This is not a replacement for live ChromaDB retrieval validation, but it provides a quick regression check for dataset shape, metric computation, and retrieval expectations.

To enable optional LLM-as-judge, run the same module without `--skip-llm` and set `OPENAI_API_KEY`. If the key is missing or the judge is unavailable, the eval marks the judge as skipped while keeping deterministic metrics.

Latest local deterministic result:

- baseline: `precision@5 = 0.192`, `recall@5 = 0.92`
- improved: `precision@5 = 0.208`, `recall@5 = 1.0`
- delta: `+0.016 precision@5`, `+0.08 recall@5`
- LLM judge skipped with `--skip-llm`
- full report in `evals/latest_local_result.json`

## Local Persistence

ChromaDB persists to `CHROMA_PATH`, which defaults to `./chroma_db`. The directory is intentionally ignored by Git because it may contain private data and generated vector index files.

## Configuration

Required environment variables:

```env
OPENAI_API_KEY=your_openai_api_key
NOTION_API_KEY=your_notion_integration_secret
NOTION_DATABASE_ID=your_notion_database_id
```

Optional:

```env
CHROMA_PATH=./chroma_db
BUSINESS_CASES_COLLECTION=business_cases
SYNC_STATE_FILE=sync_state.json
RAG_CHUNK_WORDS=700
RAG_CHUNK_OVERLAP=120
RAG_SEMANTIC_CANDIDATES=20
RAG_BM25_CANDIDATES=20
RAG_RRF_K=60
RAG_ENABLE_RERANKING=false
RAG_RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```
