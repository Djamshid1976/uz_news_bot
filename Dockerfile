# 1. Используем официальный образ Python 3.11
FROM python:3.11-slim

# 2. Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# 3. Копируем файл с зависимостями
COPY requirements.txt .

# 4. Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем все остальные файлы проекта
COPY . .

# Команда для запуска (будет переопределена в настройках Render)
# CMD ["gunicorn", "webapp:app"]