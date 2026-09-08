import os
import time
import threading
import requests
import base64
from flask import Flask, request, render_template_string, jsonify
import google.generativeai as genai
import google.auth
import google.auth.transport.requests

app = Flask(__name__)

# ==========================================
# 1. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "us-central1")
RENDER_URL = "https://sadovod-ai.onrender.com"

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ GEMINI
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)
vision_model = genai.GenerativeModel('gemini-1.5-flash')

# ==========================================
# 3. HTML ИНТЕРФЕЙС WEB APP (Мини-приложение)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Студия Садовод AI</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: var(--tg-theme-bg-color, #ffffff); color: var(--tg-theme-text-color, #000000); padding: 20px; text-align: center; }
        h2 { margin-bottom: 20px; }
        .upload-btn { background-color: var(--tg-theme-button-color, #3390ec); color: var(--tg-theme-button-text-color, #ffffff); padding: 12px 20px; border: none; border-radius: 8px; font-size: 16px; width: 100%; cursor: pointer; margin-bottom: 20px; }
        input[type="file"] { display: none; }
        #preview { max-width: 100%; border-radius: 8px; margin-bottom: 20px; display: none; }
        .prompt-btn { background-color: #f0f0f0; color: #333; padding: 15px; border: 1px solid #ccc; border-radius: 8px; font-size: 14px; width: 100%; cursor: pointer; margin-bottom: 10px; text-align: left; }
        .prompt-btn:hover { background-color: #e0e0e0; }
        #loader { display: none; font-size: 16px; color: var(--tg-theme-hint-color, #999999); margin-top: 20px; }
    </style>
</head>
<body>
    <h2>Студия Садовод AI</h2>
    <p id="instruction">Сделайте фото или выберите из галереи</p>
    
    <label class="upload-btn">
        Загрузить фото
        <input type="file" id="imageInput" accept="image/*">
    </label>
    
    <img id="preview" src="" alt="Preview">
    <div id="loader">Анализирую фото (Gemini)... ⏳</div>
    <div id="promptsContainer"></div>

    <script>
        Telegram.WebApp.ready();
        Telegram.WebApp.expand();

        const imageInput = document.getElementById('imageInput');
        const preview = document.getElementById('preview');
        const loader = document.getElementById('loader');
        const promptsContainer = document.getElementById('promptsContainer');
        const instruction = document.getElementById('instruction');

        imageInput.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    preview.src = e.target.result;
                    preview.style.display = 'block';
                    sendImageToGemini(e.target.result.split(',')[1]); 
                }
                reader.readAsDataURL(file);
            }
        });

        function sendImageToGemini(base64data) {
            loader.style.display = 'block';
            promptsContainer.innerHTML = '';
            instruction.style.display = 'none';

            fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: base64data })
            })
            .then(response => response.json())
            .then(data => {
                loader.style.display = 'none';
                if(data.prompts && data.prompts.length > 0) {
                    data.prompts.forEach(promptText => {
                        const btn = document.createElement('button');
                        btn.className = 'prompt-btn';
                        btn.innerText = promptText;
                        btn.onclick = () => startVideoGeneration(promptText);
                        promptsContainer.appendChild(btn);
                    });
                } else {
                    loader.innerText = 'Не удалось получить промпты. Попробуйте еще раз.';
                    loader.style.display = 'block';
                }
            })
            .catch(error => {
                loader.innerText = 'Ошибка соединения с сервером.';
                loader.style.display = 'block';
            });
        }

        function startVideoGeneration(selectedPrompt) {
            const chatId = Telegram.WebApp.initDataUnsafe?.user?.id;
            
            fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: chatId, prompt: selectedPrompt })
            }).then(() => {
                Telegram.WebApp.close();
            });
        }
    </script>
</body>
</html>
"""

# ==========================================
# 4. ФУНКЦИИ TELEGRAM И GOOGLE CLOUD
# ==========================================
def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    requests.post(url, json={"url": f"{RENDER_URL}/webhook"})

def get_vertex_token():
    credentials, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token

def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(url, json=payload)

# ==========================================
# 5. ФОНОВАЯ ГЕНЕРАЦИЯ ВИДЕО (VEO MOCK)
# ==========================================
def process_video_generation(chat_id, prompt):
    try:
        send_telegram_message(chat_id, f"🎥 Принято в работу!\n\nВыбранный промпт:\n_{prompt}_\n\nОтправляю задачу в Google Veo. Ожидайте готовность видео (около 5 минут)...")
        
        # Запрашиваем токен, чтобы проверить, что JSON-файл работает
        vertex_token = get_vertex_token()
        
        # Эмуляция ожидания рендеринга видео
        time.sleep(15) 
        
        send_telegram_message(chat_id, "✅ Видео успешно сгенерировано! \n\n[Здесь в будущем прикрепится реальный MP4 файл от Veo]")
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Произошла ошибка при генерации: {str(e)}")

# ==========================================
# 6. МАРШРУТИЗАЦИЯ FLASK
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return "Сервер Студия Садовод AI успешно работает!", 200

# Раздача HTML интерфейса для Web App
@app.route("/webapp", methods=["GET"])
def webapp():
    return render_template_string(HTML_TEMPLATE)

# Обработка команд от Телеграма
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        
        if text == "/start":
            # Кнопка для открытия Web App
            keyboard = {
                "inline_keyboard": [[
                    {"text": "🎬 Открыть студию", "web_app": {"url": f"{RENDER_URL}/webapp"}}
                ]]
            }
            send_telegram_message(chat_id, "Привет! Нажми кнопку ниже, чтобы загрузить фото и выбрать стиль видео.", reply_markup=keyboard)
    
    return "OK", 200

# API: Получение картинки из Web App и передача в Gemini
@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json()
    img_b64 = data.get("image")
    
    if not img_b64:
        return jsonify({"error": "No image"}), 400
        
    try:
        image_bytes = base64.b64decode(img_b64)
        prompt_instruction = "Опиши одежду на фото и напиши 3 разных, креативных промпта для генерации рекламного видео. Формат ответа строго такой: каждый промпт начинается с новой строки и с цифры '1. ', '2. ', '3. '."
        
        response = vision_model.generate_content([
            {"mime_type": "image/jpeg", "data": image_bytes},
            prompt_instruction
        ])
        
        # Парсим ответ Gemini, вытаскивая только строки, начинающиеся с цифр
        lines = response.text.split('\n')
        prompts = [line.strip() for line in lines if line.strip().startswith(('1.', '2.', '3.'))]
        
        # Если Gemini ответил криво, возвращаем весь текст как один вариант
        if not prompts:
            prompts = [response.text]
            
        return jsonify({"prompts": prompts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Получение выбранного промпта от пользователя и запуск рендера
@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    chat_id = data.get("chat_id")
    prompt = data.get("prompt")
    
    if chat_id and prompt:
        # Запускаем фоновый поток, чтобы не блокировать Web App
        threading.Thread(target=process_video_generation, args=(chat_id, prompt)).start()
        
    return jsonify({"status": "processing"})

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
