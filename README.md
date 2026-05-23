# Consulting Assistant

AI-консультант в формате Telegram-бота для бизнес-задач, связанных с внедрением искусственного интеллекта. Бот умеет вести обычный чат, запускать многоагентный сценарий бизнес-консультации, сохранять новые бизнес-кейсы в Notion и искать сохраненные кейсы через локальную RAG-базу знаний на ChromaDB.

## Что Умеет Проект

- Предоставляет Telegram-интерфейс с режимами чата, бизнес-консультации, помощи и сохранения кейсов.
- Использует CrewAI-сценарий с агентами исследователя, консультанта и критика для вопросов по бизнес-консалтингу.
- Ищет AI-бизнес-кейсы, сохраненные в ChromaDB, через `rag_tool.py`.
- Хранит память диалогов в ChromaDB через `memory.py`.
- Сохраняет структурированные бизнес-кейсы в Notion через `scribe.py`.
- Синхронизирует бизнес-кейсы из Notion в ChromaDB через Notion-to-Chroma скрипты.

## Основные Файлы

- `telegram_bot.py` - точка входа Telegram-бота, меню, команды и обработка сообщений.
- `orchestrator.py` - маршрутизация сообщений между обычным чатом и режимом бизнес-консультации.
- `agents.py` - настройка агентов и вспомогательная логика.
- `rag_tool.py` - инструмент поиска бизнес-кейсов в ChromaDB.
- `memory.py` - сохранение и поиск памяти диалогов.
- `scribe.py` - создание новых страниц с бизнес-кейсами в Notion.
- `notion_to_chromadb.py` - полная пересборка базы ChromaDB из Notion.
- `sync_notion_to_chromadb.py` - инкрементальная синхронизация Notion -> ChromaDB.
- `digest.py` - логика генерации дайджеста.
- `main.py` - минимальный стартовый файл с загрузкой переменных окружения.
- `requirements.txt` - зависимости Python.

## Переменные Окружения

Создайте локальный файл `.env` в корне проекта. Не коммитьте его в Git.

Обязательные переменные:

```env
OPENAI_API_KEY=your_openai_key
TELEGRAMBOT_API_KEY=your_telegram_bot_token
NOTION_API_KEY=your_notion_integration_secret
PROXY_URL=optional_proxy_url
```

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Запуск Бота

```bash
python telegram_bot.py
```

## Синхронизация Кейсов Из Notion В ChromaDB

Полная пересборка коллекции `business_cases`:

```bash
python notion_to_chromadb.py
```

Инкрементальная синхронизация обновленных страниц Notion:

```bash
python sync_notion_to_chromadb.py
```

## Тестирование

В проекте есть автоматические тесты для основной логики бота, синхронизации Notion/ChromaDB, форматирования RAG-ответов, создания Notion payload через Scribe и eval-проверок маршрутизации. Внешние сервисы, включая Telegram, Notion, OpenAI, ChromaDB и CrewAI, замоканы в тестах, поэтому suite запускается без реальных API-вызовов и секретов.

Запустить все тесты:

```bash
python -m pytest -q
```

Запустить только легкие eval-проверки маршрутизации:

```bash
python -m pytest -q -m eval
```

Запустить только локальные stress/boundary проверки:

```bash
python -m pytest -q -m stress
```

Проверить компиляцию Python-файлов проекта:

```bash
python -m compileall -q telegram_bot.py scribe.py agents.py digest.py main.py memory.py notion_to_chromadb.py orchestrator.py rag_tool.py sync_notion_to_chromadb.py tests
```

GitHub Actions автоматически запускает тесты и compile-check при push и pull request в ветку `main`.

## Заметки

- `.env`, `.venv`, `.idea` и локальные файлы `chroma_db` намеренно игнорируются Git.
- Локальная база ChromaDB является runtime-данными и должна пересоздаваться или синхронизироваться локально.
- API-ключи и токены бота нужно хранить только в `.env` или в переменных окружения deployment-среды.
