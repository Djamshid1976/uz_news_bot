# Файл: bot_logic.py
import os
import sys
import time
import atexit
import sqlite3
import yaml
import feedparser
import telegram
from openai import OpenAI
from dotenv import load_dotenv

# --- НАСТРОЙКА И КОНСТАНТЫ ---

# Загружаем .env файл.
load_dotenv()

# Абсолютные пути к файлам. Замените 'Djamshid1976' на ваше имя пользователя.
PROJECT_PATH = "/home/Djamshid1976/uz_news_bot"
PID_FILE = os.path.join(PROJECT_PATH, "bot.pid")
DB_FILE = os.path.join(PROJECT_PATH, "news.db")
SOURCES_FILE = os.path.join(PROJECT_PATH, "sources.yml")

# Получение настроек из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KEYWORDS = os.getenv("KEYWORDS", "iqtisodiyot, texnologiya, siyosat") # Ключевые слова по умолчанию

# --- ЛОГИКА УПРАВЛЕНИЯ ПРОЦЕССОМ (PID) ---

def create_pid_file():
    if os.path.exists(PID_FILE):
        print("PID-файл уже существует. Выход.")
        sys.exit(1)
    pid = str(os.getpid())
    with open(PID_FILE, 'w') as f:
        f.write(pid)
    print(f"Бот запущен с PID: {pid}.")

def remove_pid_file():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        print("PID-файл удален.")

atexit.register(remove_pid_file)

# --- РАБОТА С БАЗОЙ ДАННЫХ ---

def db_init():
    """Инициализирует БД и создает таблицу, если её нет."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posted (
                id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                source TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    print("База данных инициализирована.")

def get_posted_ids():
    """Получает список ID уже опубликованных новостей."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM posted")
        return {row[0] for row in cursor.fetchall()}

def add_to_posted(article_id, title, url, source):
    """Добавляет новость в базу данных как опубликованную."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO posted (id, title, url, source) VALUES (?, ?, ?, ?)",
                       (article_id, title, url, source))
        conn.commit()

# --- ОСНОВНАЯ ЛОГИКА БОТА ---

def translate_and_summarize(client, article):
    """Переводит и обобщает новость с помощью OpenAI."""
    if not client:
        return f"<b>{article['title']}</b>\n\n{article.get('summary', 'Summary not available.')}"

    prompt = f"""
    Translate the following news article title and summary into Uzbek.
    Focus on these topics: {KEYWORDS}.
    The summary should be concise, neutral, and informative, about 2-3 sentences long.
    Format the output exactly as follows:
    TITLE: [Uzbek title]
    SUMMARY: [Uzbek summary]

    Original Title: {article['title']}
    Original Summary: {article.get('summary', '')}
    """
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        response_text = completion.choices[0].message.content
        title = response_text.split("TITLE:")[1].split("SUMMARY:")[0].strip()
        summary = response_text.split("SUMMARY:")[1].strip()
        return f"<b>{title}</b>\n\n{summary}"
    except Exception as e:
        print(f"Ошибка OpenAI: {e}")
        # В случае ошибки возвращаем просто заголовок
        return f"<b>{article['title']}</b>"


def do_one_cycle(bot, openai_client):
    """Выполняет один цикл работы: сбор, обработка и постинг новостей."""
    print("Начинаю новый цикл...")
    
    # 1. Загружаем источники
    with open(SOURCES_FILE, 'r') as f:
        sources = yaml.safe_load(f)['sources']

    # 2. Получаем ID уже опубликованных новостей
    posted_ids = get_posted_ids()
    print(f"В базе {len(posted_ids)} уже опубликованных новостей.")

    # 3. Собираем все новые статьи
    new_articles = []
    for source in sources:
        print(f"Проверяю источник: {source['name']}")
        feed = feedparser.parse(source['url'])
        for entry in feed.entries:
            article_id = entry.get('guid', entry.link)
            if article_id not in posted_ids:
                new_articles.append({
                    'id': article_id,
                    'title': entry.title,
                    'link': entry.link,
                    'summary': entry.get('summary', ''),
                    'source_name': source['name']
                })

    if not new_articles:
        print("Новых статей не найдено.")
        return

    print(f"Найдено {len(new_articles)} новых статей. Начинаю обработку...")

    # 4. Обрабатываем и публикуем каждую новую статью
    for article in reversed(new_articles): # Публикуем сначала старые
        processed_text = translate_and_summarize(openai_client, article)
        
        message = (
            f"{processed_text}\n\n"
            f"<i>Манба: {article['source_name']}</i>\n"
            f"<a href='{article['link']}'>Батафсил</a>"
        )
        
        try:
            bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='HTML')
            print(f"✅ Опубликовано: {article['title']}")
            add_to_posted(article['id'], article['title'], article['link'], article['source_name'])
            time.sleep(10) # Небольшая задержка между постами
        except Exception as e:
            print(f"❌ Ошибка публикации: {e}")


# --- ГЛАВНЫЙ ЦИКЛ ---

if __name__ == "__main__":
    create_pid_file()
    
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN и CHANNEL_ID должны быть установлены.")
    
    db_init()
    
    bot_instance = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    openai_instance = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
    
    if openai_instance:
        print("Клиент OpenAI инициализирован.")
    else:
        print("API ключ OpenAI не найден, перевод и обобщение будут пропущены.")

    try:
        post_interval_minutes = int(os.getenv("POST_INTERVAL_MINUTES", 15))
        sleep_duration_seconds = post_interval_minutes * 60
        
        print(f"Бот входит в основной цикл. Интервал: {post_interval_minutes} минут.")
        while True:
            do_one_cycle(bot_instance, openai_instance)
            print(f"Цикл завершен. Засыпаю на {sleep_duration_seconds} секунд...")
            time.sleep(sleep_duration_seconds)
            
    except KeyboardInterrupt:
        print("Получен сигнал прерывания. Завершение работы...")
    except Exception as e:
        print(f"Произошла критическая ошибка: {e}")
        sys.exit(1)