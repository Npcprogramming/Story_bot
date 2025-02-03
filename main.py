import logging
import sqlite3
import os
import uuid
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Подключение к базе данных SQLite
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

# Создание таблицы пользователей, если она ещё не существует
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    referral_id INTEGER,
    referrals_count INTEGER DEFAULT 0,
    story_progress INTEGER DEFAULT 1
)
"""
)
conn.commit()


# Функция генерации частей истории по прогрессу
def get_story_part(progress):
    story = {
        1: {
            "text": (
                "История в этом боте понравилась предыдущим читателям и дошла до тебя.\n\n"
                "Но даже хорошие рассказы приходится продвигать 😁\n\n"
                "Пригласи двух своих знакомых, чтобы здесь началось настоящее повествование. "
                "Как только они присоединятся — начнётся сюжет. Я честно старался ❤️"
            ),
            # Для первой части кнопка проверки подписок больше не нужна
            "photo": None,
            "audio": None,
            "button_text": None,
            "callback_data": None,
        },
        2: {
            "text": (
                "Спасибо, что пригласил друзей!\n\n"
                "Теперь начинается настоящее повествование.\n\n"
                "Нажми 'Далее', чтобы продолжить."
            ),
            "photo": None,
            "audio": None,
            "button_text": "Далее",
            "callback_data": "continue_story",
        },
        3: {
            "text": (
                "Внизу приложена песня для максимального погружения. Я бы на твоем месте ее включил.\n\n"
                "Да начнется бесконечная история!\n\n"
                "Мэри и Джерри – два главных героя моего повествования. Хочу, чтобы ты придал им свои образы – это будет лучше, чем если я опишу лишь общие черты.\n\n"
                "Сейчас этих героев разделяет большое расстояние. Я даже не гарантирую, что это будет история о счастливой любви.\n\n"
                "Итак, Джерри с утра открыл почтовый ящик и увидел запечатанный конверт..."
            ),
            "photo": "photo1.jpg",
            "audio": "Spring.mp3",
            "button_text": "Читать дальше",
            "callback_data": "continue_story",
        },
        # Другие части истории можно добавить по аналогии...
        35: {
            "text": (
                "Как я и обещал в самом начале - эта история бесконечна. \n\n"
                "Но в этом нет смысла без читателей. Если увижу, что людей заинтересовало, то начну выпускать продолжение:\n\n"
                "В этом же боте. Ежедневно. В 22:00 по МСК. Начиная с 1 марта.\n\n"
                "Так что постарайся распространить ссылку на этого бота всем знакомым. Вот она: @HotelSpringBot\n\n"                                
                "Этим ты очень сильно поможешь❤️"
            ),
            "photo": None,
            "audio": None,
            "button_text": None,
            "callback_data": None,
        },
    }
    return story.get(progress, {"text": "История закончилась.", "photo": None, "audio": None})


# Обработка команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    args = context.args[0] if context.args else None

    # Регистрируем пользователя, если его нет в базе
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        ref_id = int(args) if args and args.isdigit() else None
        cursor.execute(
            "INSERT INTO users (id, username, referral_id) VALUES (?, ?, ?)",
            (user_id, username, ref_id),
        )
        conn.commit()
        # Если новый пользователь пришёл по реферальной ссылке,
        # увеличиваем счетчик приглашенных у реферера и проверяем, достиг ли он нужного количества
        if ref_id:
            cursor.execute(
                "UPDATE users SET referrals_count = referrals_count + 1 WHERE id = ?",
                (ref_id,),
            )
            conn.commit()
            cursor.execute(
                "SELECT referrals_count, story_progress FROM users WHERE id = ?", (ref_id,)
            )
            data = cursor.fetchone()
            if data:
                referrals_count, story_progress = data
                # Если приглашено минимум 2 человека и история ещё не продолжена,
                # обновляем progress и отправляем рефереру часть 2 истории
                if referrals_count >= 2 and story_progress == 1:
                    cursor.execute(
                        "UPDATE users SET story_progress = 2 WHERE id = ?", (ref_id,)
                    )
                    conn.commit()
                    story_part = get_story_part(2)
                    keyboard = None
                    if story_part.get("button_text") and story_part.get("callback_data"):
                        keyboard = InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        story_part["button_text"],
                                        callback_data=story_part["callback_data"],
                                    )
                                ]
                            ]
                        )
                    await context.bot.send_message(
                        chat_id=ref_id, text=story_part["text"], reply_markup=keyboard
                    )

    # Отправляем приветственное сообщение пользователю (без реферальной ссылки)
    await update.message.reply_text(
        f"Привет, {username}!\nНажмите кнопку ниже, чтобы начать историю."
    )

    # Формируем клавиатуру: только кнопка «Поделиться» с реферальной ссылкой
    referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
    share_button = InlineKeyboardButton("Поделиться", switch_inline_query=referral_link)
    keyboard = InlineKeyboardMarkup([[share_button]])

    story_part = get_story_part(1)
    if story_part["photo"]:
        await update.message.reply_photo(
            photo=story_part["photo"],
            caption=story_part["text"],
            reply_markup=keyboard,
        )
    else:
        await update.message.reply_text(
            story_part["text"],
            reply_markup=keyboard,
        )


# Обработчик inline-запроса для кнопки "Поделиться"
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.inline_query.from_user.id
    referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
    results = [
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="Моя реферальная ссылка",
            input_message_content=InputTextMessageContent(
                f"Присоединяйся к боту: {referral_link}"
            ),
        )
    ]
    await update.inline_query.answer(results)


# Callback для продолжения истории (для всех кнопок с callback_data="continue_story")
async def continue_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    cursor.execute("SELECT story_progress FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    if not result:
        await query.message.reply_text("Ошибка: пользователь не найден.")
        return

    current_progress = result[0]
    new_progress = current_progress + 1
    cursor.execute(
        "UPDATE users SET story_progress = ? WHERE id = ?", (new_progress, user_id)
    )
    conn.commit()

    story_part = get_story_part(new_progress)
    if story_part["text"] == "История закончилась.":
        await end_story(update, context)
        return

    keyboard = None
    if story_part.get("button_text") and story_part.get("callback_data"):
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(story_part["button_text"], callback_data=story_part["callback_data"])]]
        )

    if story_part.get("photo"):
        await query.message.reply_photo(
            photo=story_part["photo"],
            caption=story_part["text"],
            reply_markup=keyboard,
        )
    else:
        await query.message.reply_text(
            story_part["text"],
            reply_markup=keyboard,
        )
    if story_part.get("audio"):
        try:
            with open(story_part["audio"], "rb") as audio_file:
                await query.message.reply_audio(audio=audio_file)
        except Exception as e:
            logger.error(f"Ошибка при отправке аудио: {e}")


# Callback для завершения истории
async def end_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text("История закончена. Спасибо за внимание!")
    else:
        await update.message.reply_text("История закончена. Спасибо за внимание!")


# Команда /stats для проверки статистики пользователя
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT referrals_count, story_progress FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text("Пользователь не найден. Запустите /start для регистрации.")
        return
    referrals_count, story_progress = result
    await update.message.reply_text(
        f"Ваша статистика:\n"
        f"Приглашено друзей: {referrals_count}\n"
        f"Прогресс истории: Часть {story_progress}"
    )


def main():
    # Получаем токен бота из переменной окружения (рекомендуется для безопасности)
    token = "7767052595:AAHSLtGeGeBUDXpdcnV80PECZxuqzlbRpJs"
    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CallbackQueryHandler(continue_story, pattern="continue_story"))
    application.add_handler(InlineQueryHandler(inline_query))

    logger.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()
