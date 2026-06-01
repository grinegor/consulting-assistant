import importlib
import sys
import types


def import_memory_with_fakes(monkeypatch):
    upserts = []
    queries = []

    fake_chromadb = types.ModuleType("chromadb")
    fake_utils = types.ModuleType("chromadb.utils")
    fake_embedding_functions = types.ModuleType("chromadb.utils.embedding_functions")

    class FakeOpenAIEmbeddingFunction:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeCollection:
        def upsert(self, **kwargs):
            upserts.append(kwargs)

        def query(self, **kwargs):
            queries.append(kwargs)
            return {"documents": [["previous answer", "older answer"]]}

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def get_or_create_collection(self, **kwargs):
            return FakeCollection()

    fake_embedding_functions.OpenAIEmbeddingFunction = FakeOpenAIEmbeddingFunction
    fake_utils.embedding_functions = fake_embedding_functions
    fake_chromadb.PersistentClient = FakeClient

    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)
    monkeypatch.setitem(sys.modules, "chromadb.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "chromadb.utils.embedding_functions", fake_embedding_functions)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CHROMA_PATH", "/tmp/test-chroma")
    monkeypatch.setenv("MEMORY_COLLECTION", "test-memory")
    sys.modules.pop("memory", None)

    module = importlib.import_module("memory")
    return module, upserts, queries


def test_add_to_memory_upserts_user_scoped_turn(monkeypatch):
    memory, upserts, _ = import_memory_with_fakes(monkeypatch)
    monkeypatch.setattr(memory.time, "time", lambda: 1234.567)

    memory.add_to_memory("user-1", "hello", "answer")

    assert upserts == [{
        "ids": ["user-1_1234567"],
        "documents": ["Пользователь: hello\nАссистент: answer"],
        "metadatas": [{"user_id": "user-1", "timestamp": 1234.567}],
    }]


def test_retrieve_memory_filters_by_user(monkeypatch):
    memory, _, queries = import_memory_with_fakes(monkeypatch)

    result = memory.retrieve_memory("user-1", "support automation", n_results=2)

    assert result == "previous answer\n\n---\n\nolder answer"
    assert queries == [{
        "query_texts": ["support automation"],
        "n_results": 2,
        "where": {"user_id": "user-1"},
    }]
