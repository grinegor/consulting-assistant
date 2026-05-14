# Consulting Assistant

AI-powered Telegram consulting assistant for business use cases around AI adoption. The bot can chat with users, run a multi-agent business consultation flow, save new business cases to Notion, and search saved cases through a local ChromaDB RAG knowledge base.

## What It Does

- Provides a Telegram bot interface with chat, business consultation, help, and case-saving modes.
- Uses a CrewAI-based workflow with researcher, consultant, and critic agents for business consultation questions.
- Searches AI business cases stored in ChromaDB through `rag_tool.py`.
- Stores conversation memory in ChromaDB through `memory.py`.
- Saves structured business cases to Notion through `Scribe.py`.
- Syncs Notion business cases into ChromaDB through the Notion-to-Chroma scripts.

## Main Files

- `telegram_bot.py` - Telegram bot entry point, menus, commands, and message handling.
- `orchestrator.py` - Routes messages between simple chat and business consultation mode.
- `agents.py` - Agent-related setup and helpers.
- `rag_tool.py` - ChromaDB search tool for business cases.
- `memory.py` - Conversation memory storage and retrieval.
- `Scribe.py` - Creates new business case pages in Notion.
- `notion_to_chromadb.py` - Full rebuild from Notion into ChromaDB.
- `sync_notion_to_chromadb.py` - Incremental Notion-to-ChromaDB synchronization.
- `digest.py` - Digest-related logic.
- `main.py` - Minimal environment-loading starter file.
- `requirements.txt` - Python dependencies.

## Environment Variables

Create a local `.env` file in the project root. Do not commit it.

Required variables:

```env
OPENAI_API_KEY=your_openai_key
TELEGRAMBOT_API_KEY=your_telegram_bot_token
NOTION_API_KEY=your_notion_integration_secret
PROXY_URL=optional_proxy_url
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run The Bot

```bash
python telegram_bot.py
```

## Sync Notion Cases To ChromaDB

For a full rebuild of the `business_cases` collection:

```bash
python notion_to_chromadb.py
```

For incremental sync based on updated Notion pages:

```bash
python sync_notion_to_chromadb.py
```

## Notes

- `.env`, `.venv`, `.idea`, and local `chroma_db` files are intentionally ignored by Git.
- The local ChromaDB database is generated runtime data and should be recreated or synced locally.
- Keep API keys and bot tokens only in `.env` or your deployment environment.
