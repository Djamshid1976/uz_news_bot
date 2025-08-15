# Файл: webapp.py
from flask import Flask

app = Flask(__name__)

@app.route("/")
def status_page():
    # Render сам управляет процессами. Эта страница теперь просто для информации.
    return """
    <html>
        <head><title>Панель управления</title></head>
        <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1>🚀 Панель управления ботом</h1>
            <p>Веб-сервис (эта страница) и фоновый бот (bot_logic.py) запущены и управляются Render.</p>
            <p>Статус процессов и логи смотрите в дашборде Render.</p>
        </body>
    </html>
    """

if __name__ == '__main__':
    app.run()