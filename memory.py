import chromadb
from chromadb.utils import embedding_functions
import os
import time
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
MEMORY_COLLECTION = os.getenv("MEMORY_COLLECTION", "conversation_memory")

# Подключаемся к той же ChromaDB
client = chromadb.PersistentClient(path=CHROMA_PATH)

# Используем те же эмбеддинги OpenAI
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="text-embedding-3-small"
)

# Коллекция для памяти диалогов
memory_collection = client.get_or_create_collection(
    name=MEMORY_COLLECTION,
    embedding_function=openai_ef
)

def add_to_memory(user_id: str, user_message: str, assistant_response: str):
    """Сохраняет один оборот диалога в память"""
    doc = f"Пользователь: {user_message}\nАссистент: {assistant_response}"
    doc_id = f"{user_id}_{int(time.time()*1000)}"
    memory_collection.upsert(
        ids=[doc_id],
        documents=[doc],
        metadatas=[{"user_id": user_id, "timestamp": time.time()}]
    )

def retrieve_memory(user_id: str, query: str, n_results=3):
    """Ищет релевантные прошлые диалоги для данного пользователя"""
    results = memory_collection.query(
        query_texts=[query],
        n_results=n_results,
        where={"user_id": user_id}  # только этого пользователя
    )
    if results['documents'] and results['documents'][0]:
        return "\n\n---\n\n".join(results['documents'][0])
    return ""
