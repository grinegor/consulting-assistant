# Known Limitations

This repository is an MVP portfolio project, not a production consulting platform.

## Runtime

- The bot uses Telegram long polling, not a horizontally scalable webhook deployment.
- Local ChromaDB is used by default. Production usage would need backups, monitoring, and a migration plan for larger datasets.
- There is no enterprise auth, RBAC, tenant isolation, or audit trail.
- There is no production observability layer for agent traces, retrieval quality, latency, or API costs.

## Data And Privacy

- Notion is treated as the source of truth, but schema validation is lightweight.
- ChromaDB may contain private business-case text, so `chroma_db/` is intentionally excluded from Git.
- `.env` must never be committed because it contains API keys and private workspace IDs.

## Model Behavior

- The multi-agent flow reduces but does not eliminate hallucination risk.
- The Critic agent can highlight uncertainty, but it is not a formal compliance or security review.
- Telegram Markdown output may need stricter escaping for arbitrary model-generated content.

## Integrations

- The Notion sync scripts assume expected property names and simple field types.
- Voice transcription depends on Whisper availability through the OpenAI API.
- Photo analysis is available only in chat mode and depends on model support.

## Testing Scope

- Tests use mocks/fakes and do not call real Telegram, OpenAI, Notion, CrewAI, or ChromaDB services.
- Integration tests with real sandbox accounts would be the next step before production deployment.
