import asyncio
import importlib
import sys
import types

import pytest


class FakeChat:
    def __init__(self):
        self.actions = []

    async def send_action(self, action):
        self.actions.append(action)


class FakeMessage:
    def __init__(self, text=None, voice=None, photo=None, caption=None):
        self.text = text
        self.voice = voice
        self.photo = photo
        self.caption = caption
        self.chat = FakeChat()
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeUpdate:
    def __init__(self, message):
        self.message = message
        self.callback_query = None
        self.effective_user = types.SimpleNamespace(id=123)


class FakeContext:
    def __init__(self, user_data=None):
        self.user_data = user_data or {}
        self.bot = types.SimpleNamespace()


def import_telegram_bot(monkeypatch):
    fake_orchestrator = types.ModuleType("orchestrator")
    fake_orchestrator.orchestrate = lambda *args, **kwargs: "ok"
    fake_scribe = types.ModuleType("scribe")
    fake_scribe.ScribeAgent = lambda: object()
    monkeypatch.setitem(sys.modules, "orchestrator", fake_orchestrator)
    monkeypatch.setitem(sys.modules, "scribe", fake_scribe)
    monkeypatch.setenv("TELEGRAMBOT_API_KEY", "test-token")
    sys.modules.pop("telegram_bot", None)
    return importlib.import_module("telegram_bot")


def valid_case_text():
    return "\n".join([
        "Document Processing Agent",
        "Automation",
        "Автоматизация обработки документов",
        "GPT-4, OCR, 1C API",
        "AI-агент для распознавания",
        "OCR + LLM + интеграция",
        "Скорость, точность",
        "Требует качественных сканов",
        "https://example.com",
        "01.05.2026",
    ])


def test_parse_case_text_valid(monkeypatch):
    bot = import_telegram_bot(monkeypatch)

    case = bot.parse_case_text(valid_case_text() + "\nextra line is ignored")

    assert case == {
        "title": "Document Processing Agent",
        "category": "Automation",
        "use_case": "Автоматизация обработки документов",
        "tools": "GPT-4, OCR, 1C API",
        "summary": "AI-агент для распознавания",
        "implementation": "OCR + LLM + интеграция",
        "pros": "Скорость, точность",
        "cons": "Требует качественных сканов",
        "source": "https://example.com",
        "date": "2026-05-01",
    }


@pytest.mark.parametrize(
    ("text", "expected_error"),
    [
        ("too\nshort", "Недостаточно строк"),
        (valid_case_text().replace("Automation", "Unknown", 1), "Категория должна"),
        (valid_case_text().replace("01.05.2026", "2026-05-01"), "Неверный формат даты"),
        (valid_case_text().replace("Document Processing Agent", "", 1), "Недостаточно строк"),
    ],
)
def test_parse_case_text_boundaries(monkeypatch, text, expected_error):
    bot = import_telegram_bot(monkeypatch)

    with pytest.raises(bot.CaseValidationError, match=expected_error):
        bot.parse_case_text(text)


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("", 4096, [""]),
        ("a", 4096, ["a"]),
        ("x" * 4096, 4096, ["x" * 4096]),
        ("x" * 4097, 4096, ["x" * 4096, "x"]),
        ("abcdef", 2, ["ab", "cd", "ef"]),
    ],
)
def test_split_telegram_message_boundaries(monkeypatch, text, limit, expected):
    bot = import_telegram_bot(monkeypatch)

    assert bot.split_telegram_message(text, limit) == expected


def test_split_telegram_message_rejects_invalid_limit(monkeypatch):
    bot = import_telegram_bot(monkeypatch)

    with pytest.raises(ValueError, match="positive"):
        bot.split_telegram_message("text", 0)


def test_reply_text_chunked_preserves_kwargs(monkeypatch):
    bot = import_telegram_bot(monkeypatch)

    class FakeMessage:
        def __init__(self):
            self.calls = []

        async def reply_text(self, text, **kwargs):
            self.calls.append((text, kwargs))

    message = FakeMessage()
    asyncio.run(bot.reply_text_chunked(message, "abcde", parse_mode="Markdown"))

    assert message.calls == [("abcde", {"parse_mode": "Markdown"})]


def test_handle_message_without_mode_prompts_user_to_choose_mode(monkeypatch):
    bot = import_telegram_bot(monkeypatch)
    message = FakeMessage(text="hello")
    update = FakeUpdate(message)
    context = FakeContext()

    asyncio.run(bot.handle_message(update, context))

    assert len(message.replies) == 1
    assert "Сначала выберите режим" in message.replies[0][0]
    assert message.chat.actions == []


def test_handle_message_splits_long_orchestrator_response(monkeypatch):
    bot = import_telegram_bot(monkeypatch)
    monkeypatch.setattr(bot, "orchestrate", lambda user_id, text, mode: "x" * 4097)
    message = FakeMessage(text="hello")
    update = FakeUpdate(message)
    context = FakeContext({"mode": "chat"})

    asyncio.run(bot.handle_message(update, context))

    assert message.chat.actions == ["typing"]
    assert [len(reply[0]) for reply in message.replies] == [4096, 1]
    assert all(reply[1] == {"parse_mode": "Markdown"} for reply in message.replies)


def test_handle_message_saves_case_through_scribe(monkeypatch):
    bot = import_telegram_bot(monkeypatch)
    created_cases = []

    class FakeScribeAgent:
        def create_case(self, case_data):
            created_cases.append(case_data)
            return "created"

    sys.modules["scribe"].ScribeAgent = FakeScribeAgent
    message = FakeMessage(text=valid_case_text())
    update = FakeUpdate(message)
    context = FakeContext({"awaiting_case": True})

    asyncio.run(bot.handle_message(update, context))

    assert created_cases == [bot.parse_case_text(valid_case_text())]
    assert "awaiting_case" not in context.user_data
    assert message.replies[0] == ("created", {})
    assert message.replies[1][0] == "Что дальше?"
