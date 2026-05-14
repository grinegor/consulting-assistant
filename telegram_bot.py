import asyncio
import logging
import warnings
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from telegram.warnings import PTBUserWarning
from orchestrator import orchestrate
from scribe import ScribeAgent

# Отключаем предупреждения библиотеки
warnings.filterwarnings("ignore", category=PTBUserWarning)
logging.getLogger("telegram.ext.ConversationHandler").setLevel(logging.ERROR)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAMBOT_API_KEY")

# Категории для кейсов
CATEGORIES = ["Marketing", "Support", "Automation", "Agents", "Analytics"]

# Состояние для создания кейса (одно состояние)
ASK_CASE_BLOCK = 1

# ---------- Постоянная reply-клавиатура (левая группа кнопок) ----------
def get_reply_keyboard():
    keyboard = [
        [KeyboardButton("💬 Чат"), KeyboardButton("📊 Бизнес-консультация")],
        [KeyboardButton("✍️ Сохранить кейс"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("ℹ️ О системе"), KeyboardButton("🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# ---------- Главное inline-меню (правая группа) ----------
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Главное меню:"):
    keyboard = [
        [InlineKeyboardButton("💬 Чат", callback_data="chat")],
        [InlineKeyboardButton("📊 Бизнес-консультация", callback_data="consult")],
        [InlineKeyboardButton("✍️ Сохранить кейс", callback_data="new_case")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
        [InlineKeyboardButton("ℹ️ О системе", callback_data="info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

# ---------- Команды /start, /menu, /info ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *AI-консультант*\n\n"
        "Я умею:\n"
        "• 💬 Общаться\n"
        "• 📊 Проводить бизнес-консультации по внедрению ИИ (с тремя экспертами)\n"
        "• ✍️ Сохранять новые бизнес-кейсы в Notion одним сообщением\n\n"
        "Выберите действие в меню 👇",
        parse_mode="Markdown",
        reply_markup=get_reply_keyboard()
    )
    await main_menu(update, context)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode"):
        context.user_data.pop("mode", None)
    # Определяем, откуда вызвано: из callback или из обычного сообщения
    if update.callback_query:
        await update.callback_query.message.reply_text("🔁 Возвращаюсь в главное меню.", reply_markup=get_reply_keyboard())
        await main_menu(update, context)
    else:
        await update.message.reply_text("🔁 Возвращаюсь в главное меню.", reply_markup=get_reply_keyboard())
        await main_menu(update, context)
    return ConversationHandler.END

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_text = (
        "ℹ️ О системе\n\n"
        "У меня есть два основных режима:\n"
        "1) Чат – обычный диалог, я отвечаю сам.\n"
        "2) Бизнес-консультация – подключаются три субагента: Исследователь, Консультант, Критик.\n\n"
        "Также я умею сохранять бизнес-кейсы в Notion и искать их через RAG.\n\n"
        "Режим выбирается в меню (/menu)."
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(info_text)
    else:
        await update.message.reply_text(info_text)

# ---------- Обработка inline-кнопок ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[DEBUG] button_callback called with data: {update.callback_query.data}")
    query = update.callback_query
    await query.answer()

    if query.data == "chat":
        context.user_data["mode"] = "chat"
        await query.edit_message_text(
            "💬 *Режим чата активирован*\n\nНапишите сообщение – я отвечу.\n\n"
            "Чтобы переключить режим, просто нажмите другую кнопку в меню.",
            parse_mode="Markdown"
        )
    elif query.data == "consult":
        context.user_data["mode"] = "consult"
        await query.edit_message_text(
            "📊 *Режим бизнес-консультации активирован*\n\n"
            "Опишите вашу задачу. Я подключу трёх субагентов.\n\n"
            "Чтобы переключить режим, просто нажмите другую кнопку в меню.",
            parse_mode="Markdown"
        )

    elif query.data == "new_case" or query.data == "new_case_again":
        # Сбрасываем предыдущий режим, если был
        context.user_data.pop("mode", None)
        # Устанавливаем флаг ожидания кейса
        context.user_data["awaiting_case"] = True
        instructions = (
            "✍️ *Отправьте кейс в формате:*\n\n"
            "```\nНазвание кейса\nКатегория (Marketing/Support/Automation/Agents/Analytics)\nUse Case\nИнструменты (через запятую)\nКраткое описание (Summary)\nРеализация (Implementation)\nПлюсы (через запятую)\nМинусы (через запятую)\nСсылка на источник\nДата (ДД.ММ.ГГГГ)\n```\n\n"
            "⚠️ *Важно:* каждая строка — одно поле.\n"
            "Пример:\n"
            "```\nDocument Processing Agent\nAutomation\nАвтоматизация обработки документов\nGPT-4, OCR, 1C API\nAI-агент для распознавания\nOCR + LLM + интеграция\nСкорость, точность\nТребует качественных сканов\nhttps://example.com\n01.05.2026\n```"
        )
        await query.edit_message_text(instructions, parse_mode="Markdown")
        # Не возвращаем ничего, просто завершаем callback
        return

    elif query.data == "to_menu":
        # Завершаем диалог и показываем меню
        await query.message.reply_text("Главное меню:", reply_markup=get_reply_keyboard())
        await main_menu(update, context)
        return ConversationHandler.END
    elif query.data == "help":
        help_text = (
            "📖 *Помощь*\n\n"
            "• /start – начать работу\n"
            "• /menu – главное меню\n"
            "• /info – о системе\n"
            "• Используйте кнопки под строкой ввода для быстрого переключения режимов.\n\n"
            "📌 *Как создать кейс:*\n"
            "Нажмите «✍️ Сохранить кейс» и отправьте 10 строк по шаблону."
        )
        await query.edit_message_text(help_text, parse_mode="Markdown")
        await main_menu(update, context, "Вернуться в меню?")
    elif query.data == "info":
        await info_command(update, context)
    elif query.data == "cancel_case":
        await query.edit_message_text("❌ Создание кейса отменено.")
        await main_menu(update, context)
        return ConversationHandler.END
    else:
        # неизвестная команда – игнорируем
        pass

# ---------- Обработка обычных сообщений (без автоматического меню) ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    mode = context.user_data.get("mode")

    if context.user_data.get("awaiting_case"):
        text = update.message.text.strip()
        lines = text.split('\n')
        if len(lines) < 10:
            await update.message.reply_text("❌ Недостаточно строк. Нужно 10 строк. Отправьте ещё раз или /cancel.")
            return

        title = lines[0].strip()
        category = lines[1].strip()
        use_case = lines[2].strip()
        tools = lines[3].strip()
        summary = lines[4].strip()
        implementation = lines[5].strip()
        pros = lines[6].strip()
        cons = lines[7].strip()
        source = lines[8].strip()
        date_str = lines[9].strip()

        if not title or category not in CATEGORIES:
            await update.message.reply_text(f"❌ Категория должна быть: {', '.join(CATEGORIES)}")
            return

        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, "%d.%m.%Y")
            date_iso = date_obj.strftime("%Y-%m-%d")
        except:
            await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
            return

        case_data = {
            "title": title,
            "category": category,
            "use_case": use_case,
            "summary": summary,
            "implementation": implementation,
            "pros": pros,
            "cons": cons,
            "tools": tools,
            "source": source,
            "date": date_iso
        }

        from scribe import ScribeAgent
        scribe = ScribeAgent()
        result = await asyncio.to_thread(scribe.create_case, case_data)
        await update.message.reply_text(result)

        # Сбрасываем флаг
        context.user_data.pop("awaiting_case", None)

        # Предлагаем добавить ещё или вернуться в меню
        keyboard = [
            [InlineKeyboardButton("➕ Добавить ещё один кейс", callback_data="new_case_again")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="to_menu")]
        ]
        await update.message.reply_text("Что дальше?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ---- Обработка REPLY-КНОПОК (левое меню) ----
    if update.message.text:
        user_message = update.message.text
        if user_message == "💬 Чат":
            context.user_data["mode"] = "chat"
            await update.message.reply_text(
                "💬 *Режим чата активирован*\n\nНапишите сообщение – я отвечу.",
                parse_mode="Markdown"
            )
            return
        elif user_message == "📊 Бизнес-консультация":
            context.user_data["mode"] = "consult"
            await update.message.reply_text(
                "📊 *Режим бизнес-консультации активирован*\n\nОпишите вашу задачу.",
                parse_mode="Markdown"
            )
            return

        elif user_message == "✍️ Сохранить кейс":
            context.user_data["awaiting_case"] = True
            instructions = (
                "✍️ *Отправьте кейс в формате:*\n\n"
                "```\nНазвание кейса\nКатегория (Marketing/Support/Automation/Agents/Analytics)\nUse Case\nИнструменты (через запятую)\nКраткое описание (Summary)\nРеализация (Implementation)\nПлюсы (через запятую)\nМинусы (через запятую)\nСсылка на источник\nДата (ДД.ММ.ГГГГ)\n```\n\n"
                "⚠️ *Важно:* каждая строка — одно поле.\n"
                "Пример:\n"
                "```\nDocument Processing Agent\nAutomation\nАвтоматизация обработки документов\nGPT-4, OCR, 1C API\nAI-агент для распознавания\nOCR + LLM + интеграция\nСкорость, точность\nТребует качественных сканов\nhttps://example.com\n01.05.2026\n```"
            )
            await update.message.reply_text(instructions, parse_mode="Markdown")
            return

        elif user_message == "❓ Помощь":
            help_text = (
                "📖 *Помощь*\n\n"
                "• /start – начать работу\n"
                "• /menu – главное меню\n"
                "• /info – о системе\n"
                "• Используйте кнопки под строкой ввода для быстрого переключения режимов.\n\n"
                "📌 *Как создать кейс:*\n"
                "Нажмите «✍️ Сохранить кейс» и отправьте 10 строк по шаблону."
            )
            await update.message.reply_text(help_text, parse_mode="Markdown")
            return
        elif user_message == "ℹ️ О системе":
            await info_command(update, context)
            return
        elif user_message == "🏠 Главное меню":
            await menu_command(update, context)
            return

    # ---- ОБРАБОТКА ГОЛОСОВЫХ СООБЩЕНИЙ ----
    if update.message.voice:
        if mode is None:
            await update.message.reply_text("⚠️ Сначала выберите режим в меню (кнопки внизу или команда /menu).")
            return

        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            ogg_path = f"/tmp/voice_{user_id}.ogg"
            await file.download_to_drive(ogg_path)

            # Транскрипция через Whisper
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            with open(ogg_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f
                )
            user_text = transcript.text
            os.remove(ogg_path)

            # Отправляем текст в оркестратор в зависимости от режима
            await update.message.chat.send_action(action="typing")
            if mode == "chat":
                response = await asyncio.to_thread(orchestrate, user_id, user_text, "chat")
            elif mode == "consult":
                response = await asyncio.to_thread(orchestrate, user_id, user_text, "consult")
            else:
                response = await asyncio.to_thread(orchestrate, user_id, user_text, "auto")

            if len(response) > 4096:
                for i in range(0, len(response), 4096):
                    await update.message.reply_text(response[i:i+4096], parse_mode="Markdown")
            else:
                await update.message.reply_text(response, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при обработке голосового: {e}")
        return

    # ---- ОБРАБОТКА ФОТОГРАФИЙ (только в режиме чата) ----
    if update.message.photo:
        if mode != "chat":
            await update.message.reply_text("⚙️ Анализ изображений доступен только в режиме 'Чат'. Включите его в меню.")
            return

        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            file_url = file.file_path
            caption = update.message.caption or "Опиши это изображение"

            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-5.4-mini",
                messages=[
                    {"role": "user", "content": [
                        {"type": "text", "text": caption},
                        {"type": "image_url", "image_url": {"url": file_url}}
                    ]}
                ],
                max_completion_tokens=500
            )
            answer = response.choices[0].message.content
            await update.message.reply_text(answer, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при анализе фото: {e}")
        return

    # ---- ОБЫЧНЫЕ ТЕКСТОВЫЕ СООБЩЕНИЯ (без фото/голоса) ----
    if not update.message.text:
        return  # игнорируем стикеры, видео и т.п.

    user_message = update.message.text
    if mode is None:
        await update.message.reply_text(
            "⚠️ Сначала выберите режим в меню (кнопки внизу или команда /menu)."
        )
        return

    await update.message.chat.send_action(action="typing")
    try:
        if mode == "chat":
            response = await asyncio.to_thread(orchestrate, user_id, user_message, "chat")
        elif mode == "consult":
            response = await asyncio.to_thread(orchestrate, user_id, user_message, "consult")
        else:
            response = await asyncio.to_thread(orchestrate, user_id, user_message, "auto")

        if len(response) > 4096:
            for i in range(0, len(response), 4096):
                await update.message.reply_text(response[i:i+4096], parse_mode="Markdown")
        else:
            await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_case"):
        context.user_data.pop("awaiting_case", None)
        await update.message.reply_text("❌ Создание кейса отменено.")
    else:
        await update.message.reply_text("Нет активного действия для отмены.")
    await main_menu(update, context)

# ---------- Запуск ----------
def main():
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(
        connect_timeout=120.0,
        read_timeout=120.0,
        write_timeout=120.0
    )
    application = Application.builder() \
        .token(TELEGRAM_TOKEN) \
        .request(request) \
        .build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(new_case|new_case_again)$"))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(chat|consult|help|info|cancel_case|new_case_again|to_menu)$"))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_message))

    print("🚀 Бот запущен. Доступны команды: /start, /menu, /info")
    application.run_polling()

if __name__ == "__main__":
    main()