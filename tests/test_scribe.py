import importlib
import sys
import types

import pytest


def import_scribe(monkeypatch):
    fake_crewai = types.ModuleType("crewai")
    fake_tools = types.ModuleType("crewai.tools")

    class BaseTool:
        def __init__(self, **kwargs):
            pass

    fake_tools.BaseTool = BaseTool
    fake_crewai.tools = fake_tools
    monkeypatch.setitem(sys.modules, "crewai", fake_crewai)
    monkeypatch.setitem(sys.modules, "crewai.tools", fake_tools)
    sys.modules.pop("scribe", None)
    return importlib.import_module("scribe")


def test_notion_create_case_tool_builds_expected_properties(monkeypatch):
    scribe = import_scribe(monkeypatch)
    created = {}

    class FakePages:
        def create(self, **kwargs):
            created.update(kwargs)
            return {"url": "https://notion.so/case"}

    class FakeClient:
        pages = FakePages()

    monkeypatch.setenv("NOTION_API_KEY", "notion-token")
    monkeypatch.setenv("NOTION_DATABASE_ID", "test-database-id")
    monkeypatch.setattr(scribe, "Client", lambda auth: FakeClient())

    tool = scribe.NotionCreateCaseTool()
    result = tool._run(
        title="Support Bot",
        category="Support",
        use_case="Automate L1 support",
        summary="Answers common questions",
        implementation="Telegram + LLM",
        pros="Fast, scalable",
        cons="Needs QA",
        tools="OpenAI, ChromaDB, , Telegram",
        source="https://example.com",
        date="2026-05-01",
    )

    props = created["properties"]
    assert "успешно создан" in result
    assert created["parent"] == {"database_id": "test-database-id"}
    assert props["Name"]["title"][0]["text"]["content"] == "Support Bot"
    assert props["Category"]["select"]["name"] == "Support"
    assert props["Tools"]["multi_select"] == [
        {"name": "OpenAI"},
        {"name": "ChromaDB"},
        {"name": "Telegram"},
    ]


def test_build_notion_case_properties_filters_empty_tools(monkeypatch):
    scribe = import_scribe(monkeypatch)

    props = scribe.build_notion_case_properties({
        "title": "Case",
        "category": "Automation",
        "tools": "OpenAI, , ChromaDB",
    })

    assert props["Name"]["title"][0]["text"]["content"] == "Case"
    assert props["Category"]["select"]["name"] == "Automation"
    assert props["Tools"]["multi_select"] == [{"name": "OpenAI"}, {"name": "ChromaDB"}]


def test_notion_create_case_tool_returns_error_on_notion_failure(monkeypatch):
    scribe = import_scribe(monkeypatch)

    class FakePages:
        def create(self, **kwargs):
            raise RuntimeError("boom")

    class FakeClient:
        pages = FakePages()

    monkeypatch.setattr(scribe, "Client", lambda auth: FakeClient())
    monkeypatch.setenv("NOTION_DATABASE_ID", "test-database-id")

    tool = scribe.NotionCreateCaseTool()

    assert "Ошибка при создании кейса: boom" in tool._run(title="Broken")


def test_scribe_agent_delegates_to_tool(monkeypatch):
    scribe = import_scribe(monkeypatch)

    class FakeTool:
        def _run(self, **kwargs):
            return f"created {kwargs['title']}"

    monkeypatch.setattr(scribe, "NotionCreateCaseTool", lambda: FakeTool())

    agent = scribe.ScribeAgent()

    assert agent.create_case({"title": "Case"}) == "created Case"


def test_notion_create_case_tool_requires_database_id(monkeypatch):
    scribe = import_scribe(monkeypatch)
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)

    with pytest.raises(ValueError, match="NOTION_DATABASE_ID is required"):
        scribe.NotionCreateCaseTool()
