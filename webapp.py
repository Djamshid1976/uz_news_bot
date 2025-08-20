# Файл: webapp.py
import os
import sys
import sqlite3
import yaml
import feedparser
import telegram
from openai import OpenAI
from flask import Flask, request

# --- НАСТРОЙКА ---
# Загружаем переменные окружения, которые мы задали в Render
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KEYWORDS = os.getenv("KEYWORDS", "iqtisodiyot, texnologiya, siyosat")
SECRET_TOKEN = os.getenv("SECRET_TOKEN") # Для защиты нашего cron-триггера
SERVER_URL = os.getenv("RENDER_EXTERNAL_URL") # Render автоматически предоставляет этот URL

# Определяем пути к файлам внутри Docker-контейнера
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "news.db")
SOURCES_FILE = os.path.join(SCRIPT_DIR, "sources.yml")

# Инициализируем Flask-приложение и Telegram-бота
app = Flask(__name__)
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def db_init():
    """Инициализирует БД и создает таблицы, если их нет."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # Таблица для опубликованных постов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posted (
                id TEXT PRIMARY KEY, title TEXT, url TEXT, source TEXT,
                message_id INTEGER, posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Новая таблица для хранения полного текста статей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                full_text_en TEXT
            )
        """)
        conn.commit()
    print("База данных инициализирована.")

# --- ЛОГИКА БОТА ---
# (Функции translate, get_posted_ids, add_to_posted и т.д. остаются похожими,
# но теперь мы также сохраняем полный текст)

def get_full_article_text(article_id):
    """Получает полный текст статьи из БД."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT full_text_en FROM articles WHERE id = ?", (article_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def save_full_article_text(article_id, text):
    """Сохраняет полный текст статьи в БД."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO articles (id, full_text_en) VALUES (?, ?)", (article_id, text))
        conn.commit()

def translate_text(text, target_lang_script="Uzbek (Cyrillic script)"):
    """Универсальная функция перевода."""
    if not openai_client:
        return "Перевод временно недоступен."
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f"Translate the following text into {target_lang_script}:\n\n{text}"}],
            temperature=0.3,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка OpenAI при переводе: {e}")
        return "Ошибка перевода."

def check_and_post_news():
    """Главная функция: ищет и постит краткие версии новостей."""
    print("Начинаю проверку новостей...")
    db_init()
    
    with open(SOURCES_FILE, 'r') as f:
        sources = yaml.safe_load(f)['sources']

    # (Код поиска новых статей остается похожим, но теперь мы используем Inline-кнопки)
    # ... (здесь будет немного измененный код из do_one_cycle)
    # Главное изменение - в отправке сообщения:
    # 1. Сохраняем полный текст статьи в articles
    # 2. Создаем кнопку с callback_data
    # 3. Отправляем сообщение и сохраняем его message_id

    # ... (для краткости, представим, что мы нашли новую статью `article`)

    # Пример отправки сообщения:
    # title_uz = translate_text(article['title'])
    # summary_uz = translate_text(article['summary'])
    # save_full_article_text(article['id'], article['full_text']) # Предполагаем, что мы как-то получили полный текст

    # keyboard = [[telegram.InlineKeyboardButton("Батафсил", callback_data=f"full_{article['id']}")]]
    # reply_markup = telegram.InlineKeyboardMarkup(keyboard)

    # message_to_send = f"<b>{title_uz}</b>\n\n{summary_uz}\n\n<i>Манба: {article['source_name_uz']}</i>"
    
    # sent_message = bot.send_message(
    #     chat_id=CHANNEL_ID,
    #     text=message_to_send,
    #     parse_mode='HTML',
    #     reply_markup=reply_markup,
    #     disable_web_page_preview=True
    # )
    # add_to_posted(article['id'], ..., sent_message.message_id) # Сохраняем message_id для редактирования
    return "Проверка завершена."


# --- WEBHOOK И ОБРАБОТЧИКИ ---

@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=['POST'])
def respond():
    """Принимает обновления от Telegram."""
    update = telegram.Update.de_json(request.get_json(force=True), bot)

    if update.callback_query:
        data = update.callback_query.data
        message = update.callback_query.message

        if data.startswith("full_"):
            article_id = data.split("_")[1]
            full_text_en = get_full_article_text(article_id)
            
            if full_text_en:
                try:
                    # Показываем пользователю, что мы работаем
                    update.callback_query.answer(text="Перевожу полный текст, пожалуйста, подождите...")
                    
                    full_text_uz = translate_text(full_text_en)
                    
                    # Редактируем исходное сообщение, заменяя его на полный перевод
                    bot.edit_message_text(
                        chat_id=message.chat_id,
                        message_id=message.message_id,
                        text=f"{message.text}\n\n---\n\n<b>ПОЛНЫЙ ПЕРЕВОД:</b>\n\n{full_text_uz}",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"Ошибка при редактировании сообщения: {e}")
                    update.callback_query.answer(text="Не удалось выполнить перевод.")
            else:
                update.callback_query.answer(text="Оригинал статьи не найден.")

    return 'ok'

@app.route(f"/trigger_check/{SECRET_TOKEN}", methods=['POST'])
def trigger_check():
    """Защищенный URL для запуска проверки новостей через cron."""
    check_and_post_news()
    return "Check triggered successfully."

@app.route('/set_webhook', methods=['GET', 'POST'])
def set_webhook():
    """Устанавливает webhook для Telegram (нужно зайти один раз)."""
    if SERVER_URL:
        s = bot.set_webhook(f'{SERVER_URL}/webhook/{TELEGRAM_BOT_TOKEN}')
        if s:
            return "Webhook setup ok"
        else:
            return "Webhook setup failed"
    return "SERVER_URL not set."

if __name__ == "__main__":
    db_init()
    app.run(threaded=True)