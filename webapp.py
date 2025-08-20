# Файл: webapp.py (версия с подробным логированием)
import os
import sys
import sqlite3
import yaml
import feedparser
import telegram
from openai import OpenAI
from flask import Flask, request, jsonify

# --- НАСТРОЙКА ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SECRET_TOKEN = os.getenv("SECRET_TOKEN")
SERVER_URL = os.getenv("RENDER_EXTERNAL_URL")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "news.db")
SOURCES_FILE = os.path.join(SCRIPT_DIR, "sources.yml")

app = Flask(__name__)
try:
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
    print(">>> Инициализация Flask, Telegram Bot и OpenAI прошла успешно.")
except Exception as e:
    print(f">>> КРИТИЧЕСКАЯ ОШИБКА при инициализации: {e}", file=sys.stderr)

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def db_init():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted (
                    id TEXT PRIMARY KEY, title TEXT, url TEXT, source TEXT,
                    message_id INTEGER, posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    full_text_en TEXT
                )
            """)
            conn.commit()
        print(">>> База данных инициализирована успешно.")
    except Exception as e:
        print(f">>> ОШИБКА при инициализации БД: {e}", file=sys.stderr)

# ... (остальные функции БД без изменений)

# --- ЛОГИКА БОТА ---
# (основные функции остаются, но check_and_post_news будет изменена)
def get_posted_ids():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM posted")
        return {row[0] for row in cursor.fetchall()}

def add_to_posted(article_id, title, url, source, message_id):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO posted (id, title, url, source, message_id) VALUES (?, ?, ?, ?, ?)",
                       (article_id, title, url, source, message_id))
        conn.commit()

def translate_text(text, target_lang_script="Uzbek (Cyrillic script)"):
    if not openai_client:
        print(">>> OpenAI клиент не настроен, перевод пропускается.")
        return text # Возвращаем оригинал, если нет ключа
    
    print(f">>> Отправляю текст на перевод в OpenAI...")
    try:
        # Здесь должен быть ваш код для перевода, я оставлю заглушку
        # ...
        translated_text = f"[ПЕРЕВЕДЕНО] {text}" # ЗАГЛУШКА
        print(">>> Перевод от OpenAI получен успешно.")
        return translated_text
    except Exception as e:
        print(f">>> ОШИБКА OpenAI при переводе: {e}", file=sys.stderr)
        return f"[ОШИБКА ПЕРЕВОДА] {text}"


def check_and_post_news():
    print("\n--- ЗАПУСК НОВОГО ЦИКЛА ПРОВЕРКИ НОВОСТЕЙ ---")
    db_init()
    
    try:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            sources = yaml.safe_load(f)['sources']
        print(f">>> Загружено {len(sources)} источников из sources.yml")
    except Exception as e:
        print(f">>> КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить или прочитать sources.yml: {e}", file=sys.stderr)
        return "Ошибка чтения sources.yml"

    posted_ids = get_posted_ids()
    print(f">>> В базе данных найдено {len(posted_ids)} уже опубликованных новостей.")

    new_articles_to_post = []
    for source in sources:
        print(f"\n>>> Проверяю источник: {source.get('name_uz', 'Неизвестный источник')}")
        try:
            feed = feedparser.parse(source['url'])
            if feed.bozo:
                print(f">>> ПРЕДУПРЕЖДЕНИЕ: RSS-лента для '{source['name_uz']}' может быть некорректной. Ошибка: {feed.bozo_exception}")
            
            found_in_source = 0
            for entry in feed.entries:
                article_id = entry.get('guid', entry.link)
                if article_id not in posted_ids:
                    found_in_source += 1
                    new_articles_to_post.append({
                        'id': article_id,
                        'title': entry.title,
                        'summary': entry.get('summary', 'Нет краткого содержания.'),
                        'link': entry.link,
                        'source_name_uz': source.get('name_uz', 'Неизвестный источник'),
                    })
            print(f">>> Найдено {found_in_source} новых статей в этом источнике.")

        except Exception as e:
            print(f">>> ОШИБКА при парсинге RSS-ленты {source['url']}: {e}", file=sys.stderr)
            continue
    
    if not new_articles_to_post:
        print("--- Новых статей для публикации не найдено. Цикл завершен. ---\n")
        return "Новых статей не найдено."

    print(f"\n>>> Всего найдено {len(new_articles_to_post)} новых статей. Начинаю публикацию...")
    
    for article in reversed(new_articles_to_post):
        try:
            print(f">>> Перевожу заголовок: \"{article['title']}\"")
            title_uz = translate_text(article['title'])
            
            message_text = f"<b>{title_uz}</b>\n\n<i>Манба: {article['source_name_uz']}</i>\n<a href='{article['link']}'>Батафсил</a>"
            
            print(f">>> Пытаюсь отправить сообщение в канал {CHANNEL_ID}...")
            sent_message = bot.send_message(
                chat_id=CHANNEL_ID,
                text=message_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            print(f"✅ УСПЕХ! Сообщение отправлено. Message ID: {sent_message.message_id}")
            
            add_to_posted(article['id'], article['title'], article['link'], article['source_name_uz'], sent_message.message_id)
            print(f">>> Статья \"{article['title']}\" добавлена в базу данных опубликованных.")
            
        except Exception as e:
            print(f">>> КРИТИЧЕСКАЯ ОШИБКА при отправке сообщения в Telegram: {e}", file=sys.stderr)
            print("--- Цикл прерван из-за ошибки. ---\n")
            return "Ошибка отправки в Telegram"
    
    print(f"--- Публикация завершена. Опубликовано {len(new_articles_to_post)} статей. ---\n")
    return f"Опубликовано {len(new_articles_to_post)} новостей."

# --- WEBHOOK И ОБРАБОТЧИКИ ---
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=['POST'])
def respond():
    # Эта часть пока не будет работать, так как мы не реализовали кнопки
    return 'ok'

@app.route(f"/trigger_check/{SECRET_TOKEN}", methods=['POST'])
def trigger_check():
    report = check_and_post_news()
    return jsonify({"status": "ok", "report": report})

@app.route('/set_webhook', methods=['GET', 'POST'])
def set_webhook():
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