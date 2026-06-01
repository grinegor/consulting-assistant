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
4. recreates the `business_cases` ChromaDB collection;
5. stores documents with OpenAI embeddings.

## Incremental Sync

Use incremental sync during normal development:

```bash
python sync_notion_to_chromadb.py
```

The script:

1. loads `sync_state.json`;
2. fetches all Notion pages;
3. selects pages edited after the last sync timestamp;
4. upserts updated documents into ChromaDB;
5. writes the new sync timestamp.

## Retrieval

`rag_tool.py` loads the `business_cases` collection and queries it with the user's business question. Results are formatted with title, category, truncated content, and an approximate relevance score before being passed back to the Researcher agent.

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
```
