from crewai.tools import BaseTool
import chromadb
from chromadb.utils import embedding_functions
import os
from dotenv import load_dotenv

load_dotenv()


class ChromaRAGTool(BaseTool):
    name: str = "Business Cases Search"
    description: str = """
    Ищет релевантные бизнес-кейсы по внедрению ИИ в базе знаний.
    Используйте этот инструмент, когда нужно найти примеры из практики,
    методологии оптимизации или конкретные реализации ИИ-решений.
    Вход: поисковый запрос (строка).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, '_client', None)
        object.__setattr__(self, '_openai_ef', None)
        object.__setattr__(self, '_collection', None)

    def _ensure_initialized(self):
        if self._client is None:
            object.__setattr__(self, '_client', chromadb.PersistentClient(path="./chroma_db"))
            object.__setattr__(self, '_openai_ef', embedding_functions.OpenAIEmbeddingFunction(
                api_key=os.getenv("OPENAI_API_KEY"),
                model_name="text-embedding-3-small"
            ))
            object.__setattr__(self, '_collection', self._client.get_collection(
                name="business_cases",
                embedding_function=self._openai_ef
            ))

    def _run(self, query: str) -> str:
        print(f"[RAG] Поиск по запросу: {query}")
        self._ensure_initialized()
        results = self._collection.query(
            query_texts=[query],
            n_results=5  # оптимальное значение, можно регулировать
        )
        print(f"[RAG] Найдено результатов: {len(results['documents'][0]) if results['documents'] else 0}")
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0][:2]):  # покажем первые 2
                print(f"[RAG] Результат {i + 1}: {doc[:200]}...")
        else:
            print("[RAG] Нет результатов")
            return "Релевантных бизнес-кейсов не найдено."

        # Форматируем вывод для агента
        formatted = []
        for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
        )):
            relevance = 1 - min(distance, 1.0)
            formatted.append(f"""
    ┌────────────── КЕЙС {i + 1} (релевантность: {relevance:.0%}) ──────────────┐
    📌 Название: {metadata.get('title', 'Без названия')}
    📂 Категория: {metadata.get('category', 'Не указана')}
    📝 Содержание:
    {doc[:1200]}...
    └────────────────────────────────────────────────────────────────┘
    """)
        return "\n".join(formatted)


if __name__ == "__main__":
    tool = ChromaRAGTool()
    result = tool._run("автоматизация поддержки клиентов")
    print(result)