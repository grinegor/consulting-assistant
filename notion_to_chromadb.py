import os

import chromadb
import httpx
import requests
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from openai import OpenAI

from logging_config import configure_logging, get_logger
from rag_tool import chunk_records

load_dotenv()
configure_logging()
logger = get_logger(__name__)

PROXY_URL = os.getenv("PROXY_URL")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION_NAME = os.getenv("BUSINESS_CASES_COLLECTION", "business_cases")


class ProxyOpenAIEmbeddingFunction(embedding_functions.EmbeddingFunction):
    def __init__(self, client, model_name):
        self._client = client
        self._model_name = model_name

    def __call__(self, input):
        if isinstance(input, str):
            input = [input]
        response = self._client.embeddings.create(
            model=self._model_name,
            input=input
        )
        return [data.embedding for data in response.data]


def create_openai_client():
    http_client = httpx.Client(proxy=PROXY_URL) if PROXY_URL else None
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        http_client=http_client
    )


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


def fetch_notion_cases():
    url = f"https://api.notion.com/v1/databases/{get_notion_database_id()}/query"
    headers = {
        "Authorization": f"Bearer {os.getenv('NOTION_API_KEY')}",
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
        logger.warning("notion_cases_empty")
        return []

    sample_props = all_results[0].get("properties", {})
    logger.info("notion_fields_discovered", fields=list(sample_props.keys()))

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

    logger.info("notion_field_mapping_built", field_mapping=field_mapping)

    cases = []
    for page in all_results:
        props = page.get("properties", {})
        title = safe_get_text(props.get(field_mapping.get("Name"))) if field_mapping.get("Name") else ""
        if not title:
            continue
        cases.append({
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
        })
    return cases


def build_chroma_payload(cases):
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

    return documents, metadatas, ids


def rebuild_chroma_from_notion():
    openai_client = create_openai_client()
    embed_fn = ProxyOpenAIEmbeddingFunction(openai_client, "text-embedding-3-small")

    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        logger.info("chroma_collection_deleted", collection=COLLECTION_NAME)
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn
    )
    logger.info("chroma_collection_created", collection=COLLECTION_NAME)

    cases = fetch_notion_cases()
    logger.info("notion_cases_fetched", count=len(cases))

    if not cases:
        logger.warning("notion_cases_missing_titles")
        return 0

    documents, metadatas, ids = build_chroma_payload(cases)
    documents, metadatas, ids = chunk_records(documents, metadatas, ids)
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    logger.info("chroma_documents_loaded", count=len(documents), collection=COLLECTION_NAME)
    return len(documents)


if __name__ == "__main__":
    rebuild_chroma_from_notion()
