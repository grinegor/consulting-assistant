import importlib
import sys
import types

import pytest


def import_orchestrator_with_fakes(monkeypatch):
    fake_crewai = types.ModuleType("crewai")

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeTask:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.expected_output = kwargs.get("expected_output", "")

    class FakeCrew:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def kickoff(self):
            return "crew result"

    fake_crewai.Agent = FakeAgent
    fake_crewai.Task = FakeTask
    fake_crewai.Crew = FakeCrew

    fake_rag = types.ModuleType("rag_tool")
    fake_rag.ChromaRAGTool = lambda: object()

    fake_memory = types.ModuleType("memory")
    fake_memory.retrieve_memory = lambda user_id, query, n_results=3: "history"
    fake_memory.add_to_memory = lambda user_id, user_message, assistant_response: None

    fake_scribe = types.ModuleType("scribe")
    fake_scribe.ScribeAgent = lambda: object()

    fake_openai = types.ModuleType("openai")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **create_kwargs: types.SimpleNamespace(
                        choices=[
                            types.SimpleNamespace(
                                message=types.SimpleNamespace(content="direct response")
                            )
                        ]
                    )
                )
            )

    fake_openai.OpenAI = FakeOpenAI

    monkeypatch.setitem(sys.modules, "crewai", fake_crewai)
    monkeypatch.setitem(sys.modules, "rag_tool", fake_rag)
    monkeypatch.setitem(sys.modules, "memory", fake_memory)
    monkeypatch.setitem(sys.modules, "scribe", fake_scribe)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    sys.modules.pop("orchestrator", None)
    return importlib.import_module("orchestrator")


@pytest.mark.eval
def test_business_routing_eval_dataset(monkeypatch):
    orchestrator = import_orchestrator_with_fakes(monkeypatch)
    positives = [
        "Покажи кейсы внедрения ИИ в поддержке",
        "Нужна автоматизация бизнес-процесса",
        "Какие риски у AI агента для продаж?",
        "Оцени рентабельность нейросети для аналитики",
        "Есть пример успешного внедрения чат-бота?",
    ]
    negatives = [
        "Привет, как дела?",
        "Перефразируй этот текст дружелюбнее",
        "Составь короткое поздравление",
        "Что значит слово orchestration?",
    ]

    assert all(orchestrator.should_use_business_crew(query) for query in positives)
    assert not any(orchestrator.should_use_business_crew(query) for query in negatives)


@pytest.mark.eval
def test_orchestrate_modes_route_to_expected_path(monkeypatch):
    orchestrator = import_orchestrator_with_fakes(monkeypatch)
    calls = []

    monkeypatch.setattr(orchestrator, "retrieve_memory", lambda user_id, query, n_results=3: "history")
    monkeypatch.setattr(orchestrator, "add_to_memory", lambda *args: calls.append(("memory", args)))
    monkeypatch.setattr(orchestrator, "direct_chat", lambda message, history: f"chat:{message}:{history}")
    monkeypatch.setattr(orchestrator, "run_business_crew", lambda query: f"crew:{query}")

    assert orchestrator.orchestrate("u1", "hello", mode="chat") == "chat:hello:history"
    assert orchestrator.orchestrate("u1", "hello", mode="consult") == "crew:hello"
    assert orchestrator.orchestrate("u1", "нужен кейс внедрения ИИ", mode="auto") == "crew:нужен кейс внедрения ИИ"
    assert orchestrator.orchestrate("u1", "привет", mode="auto") == "chat:привет:history"
    assert len(calls) == 4
