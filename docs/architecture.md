# Architecture

This project is organized around a Telegram interface, an orchestration layer, a multi-agent consultation workflow, and a local RAG knowledge base backed by ChromaDB.

## Runtime Flow

```mermaid
flowchart LR
    U["Telegram User"] --> B["Telegram Bot<br/>telegram_bot.py"]
    B --> O["Orchestrator<br/>orchestrator.py"]
    O --> C["Chat mode<br/>direct OpenAI response"]
    O --> K["Consultation mode<br/>CrewAI agents"]
    B --> S["Save case mode<br/>scribe.py"]
    S --> N["Notion Database"]
    O --> M["Conversation memory<br/>memory.py"]
    M --> DB["ChromaDB"]
```

## Consultation Mode

```mermaid
flowchart LR
    Q["User business question"] --> R["Researcher"]
    R --> RT["RAG Tool<br/>Business Cases Search"]
    RT --> HR["Hybrid Retrieval<br/>Semantic + BM25 + RRF"]
    HR --> CDB["ChromaDB<br/>business_cases"]
    HR --> RR["Optional Cross-Encoder<br/>reranking"]
    CDB --> HR
    RR --> R
    R --> A["Consultant"]
    A --> C["Critic"]
    C --> F["Final answer<br/>Telegram Markdown"]
```

The Researcher is responsible for grounding recommendations in retrieved cases. The Consultant translates context into practical implementation advice. The Critic highlights weak evidence, hidden costs, compliance concerns, and implementation risks.

## Data Pipeline

```mermaid
flowchart LR
    N["Notion DB<br/>curated AI business cases"] --> SY["Sync scripts"]
    SY --> P["Payload builder<br/>documents + metadata + ids"]
    P --> CH["Chunking<br/>700 words / 120 overlap"]
    CH --> E["OpenAI embeddings<br/>text-embedding-3-small"]
    E --> C["ChromaDB collection<br/>business_cases"]
    C --> R["RAG search"]
    R --> AG["Researcher agent"]
```

## Evaluation Boundary

```mermaid
flowchart LR
    EQ["25 synthetic portfolio-safe questions"] --> ER["Offline lexical retriever<br/>evals/portfolio_rag_eval.py"]
    ED["12 synthetic case documents"] --> ER
    ER --> EM["baseline vs improved<br/>precision@5 + recall@5"]
    ER --> LJ["Optional LLM-as-judge<br/>only with OPENAI_API_KEY"]
```

The eval pipeline is intentionally separate from the live ChromaDB/OpenAI RAG path. It gives the repository a fast, deterministic retrieval-quality check without requiring model downloads, real Notion data, ChromaDB services, or OpenAI credentials in CI. The latest local deterministic run compares a title/category baseline against an improved full-text retrieval pass. The optional LLM judge is a qualitative overlay and is skipped when `OPENAI_API_KEY` is absent.

## Key Modules

- `telegram_bot.py` handles Telegram commands, menus, text messages, voice messages, image messages, and save-case interactions.
- `orchestrator.py` routes messages between chat mode, consultation mode, and auto mode.
- `rag_tool.py` wraps hybrid ChromaDB/BM25/RRF retrieval as a CrewAI tool and can optionally apply cross-encoder reranking.
- `evals/portfolio_rag_eval.py` runs the offline synthetic RAG eval and writes the latest local JSON report.
- `memory.py` stores and retrieves conversation memory from ChromaDB.
- `scribe.py` creates structured Notion pages for new business cases.
- `notion_to_chromadb.py` performs a full rebuild from Notion into ChromaDB.
- `sync_notion_to_chromadb.py` performs incremental Notion synchronization.

## Configuration Boundary

Secrets and private IDs are loaded from environment variables. The repository includes `.env.example` but does not commit real `.env` values, Notion database IDs, tokens, or ChromaDB data.
