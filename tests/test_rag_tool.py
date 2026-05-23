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
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    result = tool_with_collection(rag_module, EmptyCollection())._run("support automation")

    assert result == "Релевантных бизнес-кейсов не найдено."


def test_rag_tool_formats_results_and_clamps_relevance(monkeypatch):
    rag_module = import_rag_tool(monkeypatch)

    class FakeCollection:
        def query(self, **kwargs):
            assert kwargs["query_texts"] == ["support automation"]
            assert kwargs["n_results"] == 5
            return {
                "documents": [["Doc 1 body", "Doc 2 body"]],
                "metadatas": [[
                    {"title": "Case 1", "category": "Support"},
                    {"title": "Case 2", "category": "Automation"},
                ]],
                "distances": [[0.2, 1.7]],
            }

    result = tool_with_collection(rag_module, FakeCollection())._run("support automation")

    assert "КЕЙС 1" in result
    assert "Название: Case 1" in result
    assert "Категория: Support" in result
    assert "релевантность: 80%" in result
    assert "КЕЙС 2" in result
    assert "релевантность: 0%" in result
