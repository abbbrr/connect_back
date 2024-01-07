# Используйте официальный образ Python
FROM python:3.8

# Установка зависимостей
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Копирование файлов в образ
COPY . /app/

# Команда для запуска приложения
CMD ["python", "app.py"]
