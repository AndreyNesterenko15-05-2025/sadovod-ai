import os
import requests
from flask import Flask, request
import google.generativeai as genai
import google.auth
import google.auth.transport.requests

app = Flask(__name__)

# ==========================================
# 1. ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ИЗ RENDER
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "us-central1")

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ ЛЕГКОЙ МОДЕЛИ (GEMINI)
# Для анализа фото и написания промптов
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)
vision_model = genai.GenerativeModel('gemini-1.5-flash')

# ==========================================
# 3. АВТОРИЗАЦИЯ ТЯЖЕЛОЙ МОДЕЛИ (VERTEX AI / VEO)
# Автоматически читает файл google-credentials.json
# ==========================================
def get_vertex_token():
    # Запрашиваем права на облачные вычисления
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token

# ==========================================
# 4. ФУНКЦИИ ТЕЛЕГРАМ БОТА
# ==========================================
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

# ==========================================
# 5. ГЛАВНЫЙ СЕРВЕР (FLASK WEBHOOK)
# ==========================================
@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        update = request.get_json()
        
        # Проверяем, есть ли сообщение
        if "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")
            
            if text == "/start":
                send_telegram_message(chat_id, "Привет! Студия Садовод AI готова к работе. Пришли мне описание одежды, и я сгенерирую видео через Google Veo!")
            else:
                send_telegram_message(chat_id, "Принято! Начинаю обработку через спаренную нейросеть Gemini + Veo. Это может занять несколько минут...")
                
                # Здесь будет логика генерации видео после утверждения промпта
                # token = get_vertex_token()
                # ...
                
        return "OK", 200
        
    return "Сервер Студия Садовод AI успешно работает!", 200

if __name__ == "__main__":
    # Render выдает свой порт, его нужно обязательно слушать
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
