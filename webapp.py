# Файл: webapp.py (Финальная стабильная версия)
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
KEYWORDS = os.getenv("KEYWORDS", "iqtisodiyot, texnologiya, siyosat")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "news.db")
SOURCES_FILE = os.path.join(SCRIPT_DIR, "sources.yml")

app = Flask(__name__)
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def db_init():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posted (
                id TEXT PRIMARY KEY, title TEXT, url TEXT, source TEXT,
                message_id INTEGER, posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

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

# --- ЛОГИКА БОТА ---
def translate_text(text_to_translate):
    if not openai_client:
        return text_to_translate
    try:
        prompt = f"""
        Translate the following news title into Uzbek (Cyrillic script).
        The translation must be in the Uzbek Cyrillic alphabet (ўзбек кирилл алифбосида).
        Do not add any extra phrases or prefixes. Just return the translation.

        Original Title: "{text_to_translate}"
        """
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f">>> ОШИБКА OpenAI при переводе: {e}", file=sys.stderr)
        return f"[ОШИБКА ПЕРЕВОДА] {text_to_translate}"

def check_and_post_news():
    print("\n--- НАЧАЛО ЦИКЛА ПРОВЕРКИ НОВОСТЕЙ ---")
    db_init()
    
    try:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            sources = yaml.safe_load(f)['sources']
        print(f">>> Загружено {len(sources)} источников из sources.yml")
    except Exception as e:
        print(f">>> КРИТИЧЕСКАЯ ОШИБКА: Не удалось прочитать sources.yml: {e}", file=sys.stderr)
        return "Ошибка чтения sources.yml"

    posted_ids = get_posted_ids()
    print(f">>> В базе данных {len(posted_ids)} опубликованных новостей.")

    new_articles = []
    for source in sources:
        print(f">>> Проверяю источник: {source.get('name_uz', source.get('name', 'Неизвестный источник'))}")
        try:
            feed = feedparser.parse(source['url'])
            for entry in feed.entries:
                article_id = entry.get('guid', entry.link)
                if article_id not in posted_ids:
                    new_articles.append({
                        'id': article_id,
                        'title': entry.title,
                        'link': entry.link,
                        'source_name_uz': source.get('name_uz', source.get('name')),
                    })
        except Exception as e:
            print(f">>> ОШИБКА при парсинге RSS {source['url']}: {e}", file=sys.stderr)
    
    if not new_articles:
        print("--- Новых статей не найдено. Цикл завершен. ---\n")
        return "Новых статей не найдено."

    # *** ГЛАВНОЕ ИЗМЕНЕНИЕ: ОГРАНИЧИВАЕМ КОЛИЧЕСТВО ПОСТОВ ЗА РАЗ ***
    articles_to_post = new_articles[:5] # Берем только первые 5 новостей
    
    print(f"\n>>> Всего найдено {len(new_articles)} новых статей. Будет опубликовано {len(articles_to_post)}.")
    
    published_count = 0
    for article in reversed(articles_to_post):
        try:
            title_uz = article['title'] # ВРЕМЕННО ОТКЛЮЧАЕМ ПЕРЕВОД
            
            message_text = (
                f"<b>{title_uz}</b>\n\n"
                f"<i>Манба: {article['source_name_uz']}</i>\n"
                f"<a href='{article['link']}'>Батафсил</a>"
            )
            
            sent_message = bot.send_message(
                chat_id=CHANNEL_ID,
                text=message_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            print(f"✅ УСПЕХ! Опубликовано: \"{article['title']}\"")
            
            add_to_posted(article['id'], article['title'], article['link'], article['source_name_uz'], sent_message.message_id)
            published_count += 1
            
        except Exception as e:
            print(f">>> КРИТИЧЕСКАЯ ОШИБКА при отправке в Telegram: {e}", file=sys.stderr)
    
    report = f"Публикация завершена. Опубликовано {published_count} статей."
    print(f"--- {report} ---\n")
    return report

# --- WEBHOOK И ОБРАБОТЧИКИ ---
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=['POST'])
def respond():
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