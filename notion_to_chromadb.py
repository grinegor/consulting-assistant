import requests
import chromadb
from chromadb.utils import embedding_functions
import os
import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = "3538cd80a7f480aab786c93e0c370bf5"
PROXY_URL = os.getenv("PROXY_URL")  # должен быть в .env

# ---- Настройка OpenAI клиента с прокси ----
http_client = httpx.Client(proxy=PROXY_URL)
openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    http_client=http_client
)


# ---- Кастомная embedding функция с прокси ----
class ProxyOpenAIEmbeddingFunction(embedding_functions.EmbeddingFunction):
    def __init__(self, client, model_name):
        self._client = client
        self._model_name = model_name

    def __call__(self, input):
        # ChromaDB может передать как строку, так и список строк
        if isinstance(input, str):
            input = [input]
        response = self._client.embeddings.create(
            model=self._model_name,
            input=input
        )
        return [data.embedding for data in response.data]


# Создаём экземпляр embedding функции
embed_fn = ProxyOpenAIEmbeddingFunction(openai_client, "text-embedding-3-small")

# ---- Подготовка ChromaDB ----
chroma_client = chromadb.PersistentClient(path="./chroma_db")
try:
    chroma_client.delete_collection("business_cases")
    print("🗑️ Старая коллекция удалена")
except:
    pass

collection = chroma_client.create_collection(
    name="business_cases",
    embedding_function=embed_fn  # ← используем кастомную функцию
)
print("✅ Коллекция создана с эмбеддингами text-embedding-3-small (через прокси)")


# ---- Получение кейсов из Notion (без изменений) ----
def safe_get_text(prop, default=""):
    if not prop:
        return default
    if "title" in prop and prop["title"]:
        return prop["title"][0].get("text", {}).get("content", default)
    if "rich_text" in prop and prop["rich_text"]:
        return prop["rich_text"][0].get("text", {}).get("content", default)
    return default


def safe_get_select(prop, default=""):
    if not prop:
        return default
    select_obj = prop.get("select")
    if select_obj and isinstance(select_obj, dict):
        return select_obj.get("name", default)
    return default


def safe_get_multi_select(prop):
    if not prop:
        return []
    ms = prop.get("multi_select", [])
    if isinstance(ms, list):
        return [item.get("name", "") for item in ms if isinstance(item, dict)]
    return []


def safe_get_url(prop, default=""):
    if not prop:
        return default
    return prop.get("url", default)


def safe_get_date(prop, default=""):
    if not prop:
        return default
    date_obj = prop.get("date")
    if date_obj and isinstance(date_obj, dict):
        return date_obj.get("start", default)
    return default


def fetch_notion_cases():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    all_results = []
    has_more = True
    next_cursor = None
    while has_more:
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        all_results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    if not all_results:
        print("⚠️ В базе данных нет страниц (кейсов).")
        return []

    sample_props = all_results[0].get("properties", {})
    print("🔍 Доступные поля в Notion:", list(sample_props.keys()))

    field_mapping = {}
    for eng, rus in [("Name", "Название"), ("Category", "Категория"),
                     ("Use Case", "Use Case"), ("Summary", "Описание"),
                     ("Implementation", "Реализация"), ("Pros", "Плюсы"),
                     ("Cons", "Минусы"), ("Tools", "Инструменты"),
                     ("Source", "Источник"), ("Date", "Дата")]:
        if eng in sample_props:
            field_mapping[eng] = eng
        elif rus in sample_props:
            field_mapping[eng] = rus
        else:
            found = None
            for key in sample_props:
                if eng.lower() in key.lower():
                    found = key
                    break
            field_mapping[eng] = found

    print("📋 Соответствие полей:", field_mapping)

    cases = []
    for page in all_results:
        props = page.get("properties", {})
        title = safe_get_text(props.get(field_mapping.get("Name"))) if field_mapping.get("Name") else ""
        if not title:
            continue
        case = {
            "id": page["id"],
            "title": title,
            "category": safe_get_select(props.get(field_mapping.get("Category"))),
            "use_case": safe_get_text(props.get(field_mapping.get("Use Case"))),
            "summary": safe_get_text(props.get(field_mapping.get("Summary"))),
            "implementation": safe_get_text(props.get(field_mapping.get("Implementation"))),
            "pros": safe_get_text(props.get(field_mapping.get("Pros"))),
            "cons": safe_get_text(props.get(field_mapping.get("Cons"))),
            "tools": safe_get_multi_select(props.get(field_mapping.get("Tools"))),
            "source": safe_get_url(props.get(field_mapping.get("Source"))),
            "date": safe_get_date(props.get(field_mapping.get("Date")))
        }
        cases.append(case)
    return cases


# ---- Загрузка в ChromaDB ----
cases = fetch_notion_cases()
print(f"📥 Найдено {len(cases)} кейсов в Notion")

if not cases:
    print("⚠️ Нет кейсов для загрузки. Убедитесь, что в базе есть страницы с заполненным полем 'Name' или 'Название'.")
    exit()

documents = []
metadatas = []
ids = []

for case in cases:
    doc_text = f"""
Название: {case['title']}
Категория: {case['category']}
Use Case: {case['use_case']}
Описание: {case['summary']}
Реализация: {case['implementation']}
Плюсы: {case['pros']}
Минусы: {case['cons']}
Инструменты: {', '.join(case['tools'])}
Источник: {case['source']}
"""
    documents.append(doc_text)
    metadatas.append({
        "title": case['title'],
        "category": case['category'],
        "notion_id": case['id']
    })
    ids.append(case['id'])

collection.add(
    documents=documents,
    metadatas=metadatas,
    ids=ids
)

print(f"✅ Загружено {len(documents)} документов в ChromaDB")
print("\n🎉 Готово! Теперь RAG может искать по этим кейсам.")