import requests
import chromadb
import os
import time
import json
from datetime import datetime
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv()

STATE_FILE = os.getenv("SYNC_STATE_FILE", "sync_state.json")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION_NAME = os.getenv("BUSINESS_CASES_COLLECTION", "business_cases")


def get_notion_database_id():
    database_id = os.getenv("NOTION_DATABASE_ID")
    if not database_id:
        raise ValueError("NOTION_DATABASE_ID is required")
    return database_id

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
        return [item.get("name", "") for item in ms if isinstance(item, dict) and item.get("name")]
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

def get_all_notion_pages():
    url = f"https://api.notion.com/v1/databases/{get_notion_database_id()}/query"
    headers = {
        "Authorization": f"Bearer {os.getenv('NOTION_API_KEY')}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    all_pages = []
    start_cursor = None
    while True:
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        all_pages.extend(data["results"])
        if not data.get("has_more"):
            break
        start_cursor = data["next_cursor"]
    return all_pages

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_sync": 0, "processed_ids": []}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def page_to_chroma_payload(page):
    props = page.get("properties", {})
    title = safe_get_text(props.get("Name")) or safe_get_text(props.get("Название"))
    if not title:
        return None

    doc_text = f"""
Название: {title}
Категория: {safe_get_select(props.get("Category"))}
Use Case: {safe_get_text(props.get("Use Case"))}
Описание: {safe_get_text(props.get("Summary"))}
Реализация: {safe_get_text(props.get("Implementation"))}
Плюсы: {safe_get_text(props.get("Pros"))}
Минусы: {safe_get_text(props.get("Cons"))}
Инструменты: {', '.join(safe_get_multi_select(props.get("Tools")))}
Источник: {safe_get_url(props.get("Source"))}
"""
    metadata = {
        "title": title,
        "category": safe_get_select(props.get("Category")),
        "notion_id": page["id"]
    }
    return page["id"], doc_text, metadata

def sync():
    print("🔄 Синхронизация Notion -> ChromaDB...")
    state = load_state()
    last_sync = state["last_sync"]

    all_pages = get_all_notion_pages()
    print(f"📄 Всего страниц в Notion: {len(all_pages)}")

    updated_pages = []
    if last_sync == 0:
        updated_pages = all_pages
    else:
        for page in all_pages:
            edited_time = page.get("last_edited_time")
            if edited_time:
                edited_ts = datetime.fromisoformat(edited_time.replace('Z', '+00:00')).timestamp()
                if edited_ts > last_sync:
                    updated_pages.append(page)

    print(f"📝 Обновлённых страниц: {len(updated_pages)}")

    if not updated_pages:
        print("✅ Нет изменений.")
        return

    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_name="text-embedding-3-small"
    )
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=openai_ef
    )

    for page in updated_pages:
        payload = page_to_chroma_payload(page)
        if not payload:
            continue
        page_id, doc_text, metadata = payload

        collection.upsert(
            ids=[page_id],
            documents=[doc_text],
            metadatas=[metadata]
        )
        print(f"  ✅ Обновлён: {metadata['title']}")

    state["last_sync"] = int(time.time())
    save_state(state)
    print("✅ Синхронизация завершена.")

if __name__ == "__main__":
    sync()
