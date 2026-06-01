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
    RT --> CDB["ChromaDB<br/>business_cases"]
    CDB --> RT
    RT --> R
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
    P --> E["OpenAI embeddings<br/>text-embedding-3-small"]
    E --> C["ChromaDB collection<br/>business_cases"]
    C --> R["RAG search"]
    R --> AG["Researcher agent"]
```

## Key Modules

- `telegram_bot.py` handles Telegram commands, menus, text messages, voice messages, image messages, and save-case interactions.
- `orchestrator.py` routes messages between chat mode, consultation mode, and auto mode.
- `rag_tool.py` wraps ChromaDB search as a CrewAI tool.
- `memory.py` stores and retrieves conversation memory from ChromaDB.
- `scribe.py` creates structured Notion pages for new business cases.
- `notion_to_chromadb.py` performs a full rebuild from Notion into ChromaDB.
- `sync_notion_to_chromadb.py` performs incremental Notion synchronization.

## Configuration Boundary

Secrets and private IDs are loaded from environment variables. The repository includes `.env.example` but does not commit real `.env` values, Notion database IDs, tokens, or ChromaDB data.
