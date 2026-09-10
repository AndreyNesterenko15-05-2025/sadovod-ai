import os
import time
import threading
import requests
import base64
from flask import Flask, request, render_template_string, jsonify
import google.auth
import google.auth.transport.requests

app = Flask(__name__)

# ==========================================
# 1. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
VERTEX_PROJECT_ID = os.environ.get("VERTEX_PROJECT_ID")
VERTEX_REGION = os.environ.get("VERTEX_REGION", "us-central1")
RENDER_URL = "https://sadovod-ai.onrender.com"

# ==========================================
# 2. ФУНКЦИИ TELEGRAM И GOOGLE CLOUD
# ==========================================
def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    requests.post(url, json={"url": f"{RENDER_URL}/webhook"})

def get_vertex_token():
    """Получает свежий токен из файла google-credentials.json"""
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
# 3. HTML ИНТЕРФЕЙС WEB APP
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
        .upload-btn { background-color: var(--tg-theme-button-color, #3390ec); color: var(--tg-theme-button-text-color, #ffffff); padding: 12px 20px; border: none; border-radius: 8px; font-size: 16px; width: 100%; cursor: pointer; margin-bottom: 20px; display: inline-block;}
        input[type="file"] { display: none; }
        #preview { max-width: 100%; border-radius: 8px; margin-bottom: 20px; display: none; }
        .prompt-btn { background-color: #f0f0f0; color: #333; padding: 15px; border: 1px solid #ccc; border-radius: 8px; font-size: 14px; width: 100%; cursor: pointer; margin-bottom: 10px; text-align: left; }
        .prompt-btn:hover { background-color: #e0e0e0; }
        #loader { display: none; font-size: 16px; color: var(--tg-theme-hint-color, #999999); margin-top: 20px; }
        #error-box { display: none; color: #ff3b30; margin-top: 15px; font-weight: bold; }
    </style>
</head>
<body>
    <h2>Студия Садовод AI</h2>
    <p id="instruction">Выберите файл или сделайте фото</p>
    
    <label class="upload-btn">
        📷 Галерея / Камера
        <input type="file" id="imageInput" accept="image/*">
    </label>
    
    <img id="preview" src="" alt="Preview">
    <div id="loader">Обработка формата... ⏳</div>
    <div id="error-box"></div>
    <div id="promptsContainer"></div>

    <script>
        Telegram.WebApp.ready();
        Telegram.WebApp.expand();

        const imageInput = document.getElementById('imageInput');
        const preview = document.getElementById('preview');
        const loader = document.getElementById('loader');
        const promptsContainer = document.getElementById('promptsContainer');
        const instruction = document.getElementById('instruction');
        const errorBox = document.getElementById('error-box');

        imageInput.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file) {
                instruction.style.display = 'none';
                errorBox.style.display = 'none';
                promptsContainer.innerHTML = '';
                loader.innerText = 'Оптимизация файла... ⏳';
                loader.style.display = 'block';
                
                const originalMimeType = file.type || 'image/jpeg';
                
                const reader = new FileReader();
                reader.onload = function(e) {
                    const img = new Image();
                    img.onload = function() {
                        const canvas = document.createElement('canvas');
                        const MAX_SIZE = 1024;
                        let width = img.width;
                        let height = img.height;

                        if (width > height) {
                            if (width > MAX_SIZE) { height *= MAX_SIZE / width; width = MAX_SIZE; }
                        } else {
                            if (height > MAX_SIZE) { width *= MAX_SIZE / height; height = MAX_SIZE; }
                        }
                        canvas.width = width;
                        canvas.height = height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0, width, height);

                        let exportMime = originalMimeType;
                        if (exportMime !== 'image/webp' && exportMime !== 'image/jpeg' && exportMime !== 'image/png') {
                            exportMime = 'image/jpeg'; 
                        }
                        
                        const compressedDataUrl = canvas.toDataURL(exportMime, 0.8);
                        const actualMimeSent = compressedDataUrl.substring(5, compressedDataUrl.indexOf(';'));
                        const base64data = compressedDataUrl.split(',')[1];
                        
                        preview.src = compressedDataUrl;
                        preview.style.display = 'block';

                        sendImageToVertex(base64data, actualMimeSent);
                    }
                    img.src = e.target.result;
                }
                reader.readAsDataURL(file);
            }
        });

        function sendImageToVertex(base64data, mimeType) {
            loader.innerText = 'Анализирую фото (Vertex AI)... ⏳';

            fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: base64data, mime_type: mimeType })
            })
            .then(response => response.json())
            .then(data => {
                loader.style.display = 'none';
                if (data.error) {
                    errorBox.innerText = 'Ошибка: ' + data.error;
                    errorBox.style.display = 'block';
                } else if(data.prompts && data.prompts.length > 0) {
                    data.prompts.forEach(promptText => {
                        const btn = document.createElement('button');
                        btn.className = 'prompt-btn';
                        btn.innerText = promptText;
                        btn.onclick = () => startVideoGeneration(promptText);
                        promptsContainer.appendChild(btn);
                    });
                }
            })
            .catch(error => {
                loader.style.display = 'none';
                errorBox.innerText = 'Сбой сети. Сервер недоступен.';
                errorBox.style.display = 'block';
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
# 4. ФОНОВАЯ ГЕНЕРАЦИЯ ВИДЕО (VEO MOCK)
# ==========================================
def process_video_generation(chat_id, prompt):
    try:
        send_telegram_message(chat_id, f"🎥 Принято в работу!\n\nВыбранный промпт:\n_{prompt}_\n\nОтправляю задачу в Google Veo. Ожидайте готовность видео (около 5 минут)...")
        vertex_token = get_vertex_token()
        time.sleep(15) 
        send_telegram_message(chat_id, "✅ Видео успешно сгенерировано! \n\n[Здесь в будущем прикрепится реальный MP4 файл от Veo]")
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Произошла ошибка при генерации: {str(e)}")

# ==========================================
# 5. МАРШРУТИЗАЦИЯ FLASK
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return "Сервер Студия Садовод AI успешно работает через Vertex AI!", 200

@app.route("/webapp", methods=["GET"])
def webapp():
    return render_template_string(HTML_TEMPLATE)

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        
        if text == "/start":
            keyboard = {
                "inline_keyboard": [[
                    {"text": "🎬 Открыть студию", "web_app": {"url": f"{RENDER_URL}/webapp"}}
                ]]
            }
            send_telegram_message(chat_id, "Привет! Нажми кнопку ниже, чтобы загрузить фото и выбрать стиль видео.", reply_markup=keyboard)
    
    return "OK", 200

# API: Прямой запрос к Vertex AI (без AI Studio)
@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json()
    img_b64 = data.get("image")
    mime_type = data.get("mime_type", "image/jpeg") 
    
    if not img_b64:
        return jsonify({"error": "Фотография не дошла до сервера."}), 400
        
    try:
        prompt_instruction = "Опиши одежду на фото и напиши 3 разных, креативных промпта для генерации рекламного видео. Формат ответа строго такой: каждый промпт начинается с новой строки и с цифры '1. ', '2. ', '3. '."
        
        # 1. Получаем корпоративный токен
        vertex_token = get_vertex_token()
        
        # 2. Формируем прямой REST API запрос к актуальной модели gemini-3.8-flash
url = f"https://{VERTEX_REGION}-aiplatform.googleapis.com/v1/projects/{VERTEX_PROJECT_ID}/locations/{VERTEX_REGION}/publishers/google/models/gemini-3.8-flash-001:generateContent"        
        headers = {
            "Authorization": f"Bearer {vertex_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"inlineData": {"mimeType": mime_type, "data": img_b64}},
                        {"text": prompt_instruction}
                    ]
                }
            ]
        }
        
        # 3. Отправляем запрос
        response = requests.post(url, headers=headers, json=payload)
        response_data = response.json()
        
        if response.status_code != 200:
            return jsonify({"error": f"Ошибка Vertex AI: {response_data.get('error', {}).get('message', 'Неизвестная ошибка')}"}), 500
            
        # 4. Аккуратный парсинг ответа
        try:
            gemini_text = response_data['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            return jsonify({"error": "Неожиданный формат ответа от Google."}), 500
            
        # 5. Разбивка на 3 варианта
        lines = gemini_text.split('\n')
        prompts = [line.strip() for line in lines if line.strip().startswith(('1.', '2.', '3.'))]
        
        if not prompts:
            prompts = [gemini_text]
            
        return jsonify({"prompts": prompts})
        
    except Exception as e:
        print(f"Vertex API Error: {str(e)}") 
        return jsonify({"error": f"Сбой на сервере: {str(e)}"}), 500

@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    chat_id = data.get("chat_id")
    prompt = data.get("prompt")
    
    if chat_id and prompt:
        threading.Thread(target=process_video_generation, args=(chat_id, prompt)).start()
        
    return jsonify({"status": "processing"})

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
