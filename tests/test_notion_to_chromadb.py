from types import SimpleNamespace

import notion_to_chromadb as rebuild_module


def test_proxy_embedding_function_accepts_string_and_list():
    calls = []

    class FakeEmbeddings:
        def create(self, model, input):
            calls.append((model, input))
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[float(i)]) for i, _ in enumerate(input)]
            )

    fake_client = SimpleNamespace(embeddings=FakeEmbeddings())
    embed_fn = rebuild_module.ProxyOpenAIEmbeddingFunction(fake_client, "text-embedding-3-small")

    assert embed_fn("one") == [[0.0]]
    assert embed_fn(["one", "two"]) == [[0.0], [1.0]]
    assert calls == [
        ("text-embedding-3-small", ["one"]),
        ("text-embedding-3-small", ["one", "two"]),
    ]


def test_build_chroma_payload_formats_documents_and_metadata():
    cases = [
        {
            "id": "case-1",
            "title": "Support Bot",
            "category": "Support",
            "use_case": "Answer customer questions",
            "summary": "Automates L1 support",
            "implementation": "Telegram + LLM",
            "pros": "Fast",
            "cons": "Needs monitoring",
            "tools": ["OpenAI", "ChromaDB"],
            "source": "https://example.com",
            "date": "2026-05-01",
        }
    ]

    documents, metadatas, ids = rebuild_module.build_chroma_payload(cases)

    assert ids == ["case-1"]
    assert metadatas == [{"title": "Support Bot", "category": "Support", "notion_id": "case-1"}]
    assert "Название: Support Bot" in documents[0]
    assert "Инструменты: OpenAI, ChromaDB" in documents[0]
    assert "Источник: https://example.com" in documents[0]


def test_fetch_notion_cases_paginates_and_maps_ru_fields(monkeypatch):
    monkeypatch.setenv("NOTION_DATABASE_ID", "test-database-id")
    responses = [
        {
            "results": [
                {
                    "id": "case-1",
                    "properties": {
                        "Название": {"title": [{"text": {"content": "Кейс"}}]},
                        "Категория": {"select": {"name": "Automation"}},
                        "Описание": {"rich_text": [{"text": {"content": "Описание"}}]},
                        "Инструменты": {"multi_select": [{"name": "OpenAI"}]},
                        "Источник": {"url": "https://example.com"},
                        "Дата": {"date": {"start": "2026-05-01"}},
                    },
                }
            ],
            "has_more": True,
            "next_cursor": "cursor-2",
        },
        {
            "results": [
                {
                    "id": "case-2",
                    "properties": {
                        "Название": {"title": []},
                    },
                }
            ],
            "has_more": False,
            "next_cursor": None,
        },
    ]
    payloads = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_post(url, headers, json):
        payloads.append(json)
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr(rebuild_module.requests, "post", fake_post)

    cases = rebuild_module.fetch_notion_cases()

    assert payloads == [{}, {"start_cursor": "cursor-2"}]
    assert cases == [
        {
            "id": "case-1",
            "title": "Кейс",
            "category": "Automation",
            "use_case": "",
            "summary": "Описание",
            "implementation": "",
            "pros": "",
            "cons": "",
            "tools": ["OpenAI"],
            "source": "https://example.com",
            "date": "2026-05-01",
        }
    ]


def test_rebuild_returns_zero_when_notion_has_no_cases(monkeypatch):
    class FakeClient:
        def delete_collection(self, name):
            return None

        def create_collection(self, **kwargs):
            return SimpleNamespace(add=lambda **add_kwargs: None)

    monkeypatch.setattr(rebuild_module, "create_openai_client", lambda: object())
    monkeypatch.setattr(rebuild_module.chromadb, "PersistentClient", lambda path: FakeClient())
    monkeypatch.setattr(rebuild_module, "fetch_notion_cases", lambda: [])

    assert rebuild_module.rebuild_chroma_from_notion() == 0
