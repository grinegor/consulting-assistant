import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import sync_notion_to_chromadb as sync_module


def notion_page(page_id, title, edited="2026-05-23T10:00:00Z"):
    props = {
        "Name": {"title": [{"text": {"content": title}}]} if title is not None else {"title": []},
        "Category": {"select": {"name": "Automation"}},
        "Use Case": {"rich_text": [{"text": {"content": "Automate support"}}]},
        "Summary": {"rich_text": [{"text": {"content": "Short summary"}}]},
        "Implementation": {"rich_text": [{"text": {"content": "LLM + workflow"}}]},
        "Pros": {"rich_text": [{"text": {"content": "Fast"}}]},
        "Cons": {"rich_text": [{"text": {"content": "Needs QA"}}]},
        "Tools": {"multi_select": [{"name": "OpenAI"}, {"name": "ChromaDB"}]},
        "Source": {"url": "https://example.com"},
    }
    return {"id": page_id, "last_edited_time": edited, "properties": props}


def test_safe_getters_handle_empty_values():
    assert sync_module.safe_get_text(None) == ""
    assert sync_module.safe_get_text({"title": [{"text": {"content": "Title"}}]}) == "Title"
    assert sync_module.safe_get_text({"rich_text": [{"text": {"content": "Body"}}]}) == "Body"
    assert sync_module.safe_get_select({"select": {"name": "Support"}}) == "Support"
    assert sync_module.safe_get_select({"select": None}) == ""
    assert sync_module.safe_get_multi_select({"multi_select": [{"name": "A"}, {"bad": "ignored"}]}) == ["A", ""]
    assert sync_module.safe_get_multi_select({"multi_select": "not-a-list"}) == []
    assert sync_module.safe_get_url({"url": "https://example.com"}) == "https://example.com"
    assert sync_module.safe_get_date({"date": {"start": "2026-05-23"}}) == "2026-05-23"


def test_state_load_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = {"last_sync": 123, "processed_ids": ["a", "b"]}

    sync_module.save_state(state)

    assert json.loads((tmp_path / sync_module.STATE_FILE).read_text()) == state
    assert sync_module.load_state() == state


def test_page_to_chroma_payload_valid_page():
    page_id, document, metadata = sync_module.page_to_chroma_payload(notion_page("page-1", "Case A"))

    assert page_id == "page-1"
    assert "Название: Case A" in document
    assert "Инструменты: OpenAI, ChromaDB" in document
    assert metadata == {
        "title": "Case A",
        "category": "Automation",
        "notion_id": "page-1",
    }


def test_page_to_chroma_payload_skips_pages_without_title():
    assert sync_module.page_to_chroma_payload(notion_page("page-1", None)) is None


def test_sync_only_upserts_changed_pages(monkeypatch):
    old_sync = datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc).timestamp()
    pages = [
        notion_page("old", "Old", "2026-05-23T08:00:00Z"),
        notion_page("new", "New", "2026-05-23T10:00:00Z"),
        notion_page("untitled", None, "2026-05-23T11:00:00Z"),
    ]
    upserts = []
    saved_states = []

    class FakeCollection:
        def upsert(self, **kwargs):
            upserts.append(kwargs)

    class FakeClient:
        def get_or_create_collection(self, **kwargs):
            assert kwargs["name"] == "business_cases"
            return FakeCollection()

    monkeypatch.setattr(sync_module, "load_state", lambda: {"last_sync": old_sync, "processed_ids": []})
    monkeypatch.setattr(sync_module, "save_state", lambda state: saved_states.append(state))
    monkeypatch.setattr(sync_module, "get_all_notion_pages", lambda: pages)
    monkeypatch.setattr(sync_module.chromadb, "PersistentClient", lambda path: FakeClient())
    monkeypatch.setattr(sync_module.embedding_functions, "OpenAIEmbeddingFunction", lambda **kwargs: object())
    monkeypatch.setattr(sync_module.time, "time", lambda: 1770000000)

    sync_module.sync()

    assert len(upserts) == 1
    assert upserts[0]["ids"] == ["new"]
    assert "Название: New" in upserts[0]["documents"][0]
    assert saved_states == [{"last_sync": 1770000000, "processed_ids": []}]


def test_sync_no_changes_does_not_open_chroma(monkeypatch):
    monkeypatch.setattr(sync_module, "load_state", lambda: {"last_sync": 9999999999, "processed_ids": []})
    monkeypatch.setattr(sync_module, "get_all_notion_pages", lambda: [notion_page("old", "Old")])
    monkeypatch.setattr(
        sync_module.chromadb,
        "PersistentClient",
        lambda path: pytest.fail("ChromaDB should not be opened when there are no updates"),
    )

    assert sync_module.sync() is None


@pytest.mark.stress
def test_sync_large_initial_batch_stress(monkeypatch):
    pages = [notion_page(f"page-{i}", f"Case {i}") for i in range(1500)]
    upserts = []

    class FakeCollection:
        def upsert(self, **kwargs):
            upserts.append(kwargs)

    monkeypatch.setattr(sync_module, "load_state", lambda: {"last_sync": 0, "processed_ids": []})
    monkeypatch.setattr(sync_module, "save_state", lambda state: None)
    monkeypatch.setattr(sync_module, "get_all_notion_pages", lambda: pages)
    monkeypatch.setattr(
        sync_module.chromadb,
        "PersistentClient",
        lambda path: SimpleNamespace(get_or_create_collection=lambda **kwargs: FakeCollection()),
    )
    monkeypatch.setattr(sync_module.embedding_functions, "OpenAIEmbeddingFunction", lambda **kwargs: object())
    monkeypatch.setattr(sync_module.time, "time", lambda: 1770000000)

    sync_module.sync()

    assert len(upserts) == 1500
    assert upserts[0]["ids"] == ["page-0"]
    assert upserts[-1]["ids"] == ["page-1499"]
