import os
import requests
from flask import Flask, request
import google.generativeai as genai
import google.auth
import google.auth.transport.requests

app = Flask(__name__)

# ==========================================
# 1. ЗАГРУЗКА И ОЧИСТКА ПЕРЕМЕННЫХ (.strip() удаляет случайные пробелы)
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "us-central1")
RENDER_URL = "https://sadovod-ai.onrender.com"

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ ЛЕГКОЙ МОДЕЛИ (GEMINI)
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)
vision_model = genai.GenerativeModel('gemini-1.5-flash')

def get_vertex_token():
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

# ==========================================
# 3. АВТОМАТИЧЕСКАЯ УСТАНОВКА ВЕБХУКА
# Сервер сам свяжется с Телеграмом при старте
# ==========================================
def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    response = requests.post(url, json={"url": f"{RENDER_URL}/"})
    print(f"Webhook setup status: {response.json()}")

# ==========================================
# 4. ГЛАВНЫЙ СЕРВЕР (FLASK WEBHOOK)
# ==========================================
@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        update = request.get_json()
        if update and "message" in update:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"].get("text", "")
            
            if text == "/start":
                send_telegram_message(chat_id, "Привет! Студия Садовод AI готова к работе. Пришли мне описание одежды, и я сгенерирую видео через Google Veo!")
            else:
                send_telegram_message(chat_id, "Принято! Начинаю обработку через спаренную нейросеть Gemini + Veo. Это может занять несколько минут...")
        return "OK", 200
    return "Сервер Студия Садовод AI успешно работает!", 200

if __name__ == "__main__":
    set_webhook() # <-- Эта команда всё сделает за нас
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
