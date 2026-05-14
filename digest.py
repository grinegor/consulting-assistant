import feedparser
import httpx
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

# Настройка клиента OpenAI с прокси (как в test.py)
PROXY_URL = os.getenv("PROXY_URL")
http_client = httpx.Client(proxy=PROXY_URL) if PROXY_URL else None
openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    http_client=http_client
)

# Список RSS-источников AI-новостей
NEWS_SOURCES = [
    "https://openai.com/blog/feed/feed.xml",
    "https://ai.googleblog.com/feeds/posts/default",
    "https://huggingface.co/blog/feed.xml",
    "https://www.technologyreview.com/feed/ai/",
    "https://venturebeat.com/category/ai/feed/",
]

def fetch_news(limit_per_source=3):
    """Собирает свежие новости из RSS-лент"""
    all_news = []
    for url in NEWS_SOURCES:
        try:
            feed = feedparser.parse(url)
            entries = feed.entries[:limit_per_source]
            for entry in entries:
                all_news.append({
                    "title": entry.title,
                    "link": entry.link,
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", "")[:200]  # краткий отрывок
                })
        except Exception as e:
            print(f"Ошибка при загрузке {url}: {e}")
    return all_news

def generate_digest():
    """Генерирует дайджест с помощью GPT-5.4-mini"""
    news = fetch_news()
    if not news:
        return "❌ Не удалось загрузить новости. Попробуйте позже."

    # Формируем текстовый список для промпта
    news_list = "\n".join([
        f"- {item['title']}\n  {item['link']}\n  {item['summary'][:150]}..."
        for item in news
    ])

    prompt = f"""
Ты — бизнес-аналитик по AI. Вот свежие новости из мира искусственного интеллекта:

{news_list}

Задача:
1. Отбери 3–5 самых важных новостей.
2. Для каждой напиши:
   - **Заголовок**
   - **О чем:** кратко (1-2 предложения)
   - **Для бизнеса:** практическая польза (1 предложение)
3. Оформи итог в виде готового сообщения для Telegram. Используй эмодзи для разделения новостей. Не используй markdown, только обычный текст. Длина не более 4000 символов.
"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_completion_tokens=2000
        )
        digest = response.choices[0].message.content
        return digest
    except Exception as e:
        return f"❌ Ошибка при генерации дайджеста: {e}"

# Для теста модуля
if __name__ == "__main__":
    print(generate_digest())