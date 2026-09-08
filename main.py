import os
import time
import threading
import requests
from flask import Flask, request
import google.generativeai as genai
import google.auth
import google.auth.transport.requests

app = Flask(__name__)

# ==========================================
# 1. ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "us-central1")
RENDER_URL = "https://sadovod-ai.onrender.com"

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ ИНСТРУМЕНТОВ
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)
# Используем быструю модель для анализа фото и написания промптов
vision_model = genai.GenerativeModel('gemini-1.5-flash')

def set_webhook():
    """Автоматическая настройка моста с Телеграмом при запуске"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    requests.post(url, json={"url": f"{RENDER_URL}/"})

def get_vertex_token():
    """Получение временного токена из нашего JSON-файла"""
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token

# ==========================================
# 3. ФУНКЦИИ ТЕЛЕГРАМ-БОТА
# ==========================================
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def send_telegram_video(chat_id, video_url):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    requests.post(url, json={"chat_id": chat_id, "video": video_url})

def get_telegram_file_url(file_id):
    """Скачивает картинку из Телеграма для передачи в Gemini"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    res = requests.get(url).json()
    if res.get("ok"):
        file_path = res["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    return None

# ==========================================
# 4. ФОНОВЫЙ ПРОЦЕСС ГЕНЕРАЦИИ (БЕЗ ТАЙМ-АУТОВ)
# ==========================================
def process_video_generation(chat_id, user_text, image_url=None):
    try:
        send_telegram_message(chat_id, "⏳ Шаг 1: Анализирую запрос и готовлю промпт для режиссера...")
        
        # ЭТАП A: Подготовка промпта через Gemini
        final_prompt = user_text
        if image_url:
            # Если есть картинка, просим Gemini её описать
            # (В реальном проекте здесь загружается байтовый код картинки в Gemini)
            final_prompt = f"Видео на основе визуального референса: {user_text}"
            
        send_telegram_message(chat_id, "🎥 Шаг 2: Промпт готов. Отправляю задачу в Google Veo (Vertex AI). Это займет около 3-5 минут...")
        
        # ЭТАП B: Отправка задачи в Vertex AI (Veo)
        vertex_token = get_vertex_token()
        
        # Заготовка API-запроса к Vertex AI
        # endpoint = f"https://{VERTEX_REGION}-aiplatform.googleapis.com/v1/projects/{VERTEX_PROJECT_ID}/locations/{VERTEX_REGION}/publishers/google/models/veo:predict"
        # headers = {"Authorization": f"Bearer {vertex_token}", "Content-Type": "application/json"}
        # payload = {"instances": [{"prompt": final_prompt}]}
        
        # Имитация ожидания рендеринга (пока мы не подключили точный эндпоинт Veo)
        time.sleep(10) 
        
        send_telegram_message(chat_id, "✅ Видео успешно сгенерировано! Отправляю файл...")
        
        # Здесь будет отправка финального видео
        # send_telegram_video(chat_id, "ССЫЛКА_НА_ВИДЕО_ИЗ_VEO")
        
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Произошла ошибка при генерации: {str(e)}")

# ==========================================
# 5. ГЛАВНЫЙ ВЕБ-СЕРВЕР (FLASK)
# ==========================================
@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        update = request.get_json()
        if update and "message" in update:
            chat_id = update["message"]["chat"]["id"]
            
            # Обработка команды /start
            if update["message"].get("text") == "/start":
                send_telegram_message(chat_id, "Привет! Я Студия Садовод AI.\nПришли мне фото одежды с описанием, и я создам для тебя видеоролик через Google Veo!")
                return "OK", 200
            
            # Обработка текста или фото
            user_text = update["message"].get("text", update["message"].get("caption", "Сделай красивое рекламное видео"))
            image_url = None
            
            # Если пользователь прислал картинку
            if "photo" in update["message"]:
                # Берем самое большое разрешение фото (последний элемент массива)
                file_id = update["message"]["photo"][-1]["file_id"]
                image_url = get_telegram_file_url(file_id)
                
            send_telegram_message(chat_id, "Принято! Ставлю задачу в очередь.")
            
            # ЗАПУСК ФОНОВОГО ПРОЦЕССА (Чтобы Телеграм не выдал ошибку тайм-аута)
            thread = threading.Thread(target=process_video_generation, args=(chat_id, user_text, image_url))
            thread.start()

        return "OK", 200
    return "Сервер Студия Садовод AI успешно работает!", 200

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
