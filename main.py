import os
import threading
import requests
import base64
import re
import uuid
from flask import Flask, request, render_template_string, jsonify
import google.auth
import google.auth.transport.requests

app = Flask(__name__)

# ==========================================
# 1. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
VERTEX_PROJECT_ID = (os.environ.get("VERTEX_PROJECT_ID") or "").strip()
# Сохранено для будущей отдельной конфигурации Veo; НЕ управляет Gemini.
VERTEX_REGION = os.environ.get("VERTEX_REGION", "us-central1")
GEMINI_MODEL = (os.environ.get("GEMINI_MODEL") or "gemini-3.8-flash").strip()
GEMINI_LOCATION = (os.environ.get("GEMINI_LOCATION") or "global").strip().lower()
HOTFIX_VERSION = "vertex-routing-2026-09-10"
RENDER_URL = "https://sadovod-ai.onrender.com"

# ==========================================
# 2. ФУНКЦИИ TELEGRAM И GOOGLE CLOUD
# ==========================================
def set_webhook():
    if not BOT_TOKEN:
        print("[Telegram] BOT_TOKEN не настроен; webhook не зарегистрирован.", flush=True)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    try:
        response = requests.post(
            url, json={"url": f"{RENDER_URL}/webhook"}, timeout=(10, 20)
        )
        result = response.json()
        print(
            f"[Telegram] webhook HTTP={response.status_code} "
            f"ok={isinstance(result, dict) and result.get('ok') is True}",
            flush=True,
        )
    except Exception as exc:
        # Не логируем URL Telegram: он содержит BOT_TOKEN.
        print(f"[Telegram] webhook error={type(exc).__name__}", flush=True)

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
    requests.post(url, json=payload, timeout=(10, 20))


def build_gemini_url():
    """REST endpoint: global, multi-region us/eu, или поддерживаемый моделью регион.

    Официальная схема маршрутизации проверена 2026-09-10:
    https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations
    """
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", VERTEX_PROJECT_ID):
        raise ValueError("Проверьте VERTEX_PROJECT_ID в Render: нужен Google Cloud Project ID.")
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", GEMINI_MODEL):
        raise ValueError("GEMINI_MODEL должен содержать только короткий идентификатор модели.")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", GEMINI_LOCATION):
        raise ValueError("GEMINI_LOCATION содержит недопустимое значение.")
    if GEMINI_MODEL == "gemini-3.8-flash" and GEMINI_LOCATION not in {"global", "us", "eu"}:
        raise ValueError(
            "Для gemini-3.8-flash используйте GEMINI_LOCATION=global, us или eu; "
            "us-central1 не поддерживается согласно документации, проверенной 10.09.2026."
        )
    if GEMINI_LOCATION == "global":
        host = "aiplatform.googleapis.com"
    elif GEMINI_LOCATION in {"us", "eu"}:
        host = f"aiplatform.{GEMINI_LOCATION}.rep.googleapis.com"
    else:
        # Для других моделей: доступность конкретного региона проверяется отдельно.
        host = f"{GEMINI_LOCATION}-aiplatform.googleapis.com"
    return (
        f"https://{host}/v1/projects/{VERTEX_PROJECT_ID}"
        f"/locations/{GEMINI_LOCATION}/publishers/google/models/{GEMINI_MODEL}:generateContent"
    )


def google_error_message(status_code):
    """Без сырого Google error.message, путей проекта и учетных данных."""
    messages = {
        400: "Google отклонил параметры запроса или ограничения доступа к модели.",
        401: "Google отклонил серверные учетные данные. Проверьте авторизацию Google Cloud.",
        403: "Нет разрешения Google Cloud. Проверьте API, IAM сервисного аккаунта и billing.",
        404: "Модель не найдена по указанному адресу или недоступна этому проекту. Проверьте модель, location и доступ проекта.",
        429: "Google временно ограничил запросы: квота или нехватка доступной мощности. Повторите позднее.",
        500: "Внутренняя ошибка Google. Повторите позднее.",
        503: "Google временно недоступен. Повторите позднее.",
        504: "Google не успел завершить запрос. Повторите позднее.",
    }
    return messages.get(status_code, "Запрос к Google завершился ошибкой.")


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
        *, *::before, *::after { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: var(--tg-theme-bg-color, #ffffff); color: var(--tg-theme-text-color, #000000); padding: 20px; text-align: center; }
        h2 { margin-bottom: 20px; }
        .upload-btn { background-color: var(--tg-theme-button-color, #3390ec); color: var(--tg-theme-button-text-color, #ffffff); padding: 12px 20px; border: none; border-radius: 8px; font-size: 16px; width: 100%; cursor: pointer; margin-bottom: 20px; display: inline-block;}
        input[type="file"] { display: none; }
        #preview { max-width: 100%; border-radius: 8px; margin-bottom: 20px; display: none; }
        .prompt-btn { background-color: #f0f0f0; color: #333; padding: 15px; border: 1px solid #ccc; border-radius: 8px; font-size: 14px; width: 100%; cursor: pointer; margin-bottom: 10px; text-align: left; }
        .prompt-btn:hover { background-color: #e0e0e0; }
        #loader { display: none; font-size: 16px; color: var(--tg-theme-hint-color, #999999); margin-top: 20px; }
        #error-box { overflow-wrap: anywhere; display: none; color: #ff3b30; margin-top: 15px; font-weight: bold; }
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
    """Честная демонстрационная заглушка; Veo и создание MP4 ещё не реализованы."""
    try:
        send_telegram_message(
            chat_id,
            "🧪 Демонстрационный режим. Сценарий выбран:\n\n"
            + str(prompt)[:2500]
            + "\n\nГенерация через Veo пока не подключена. "
              "Видеофайл не создавался. Этот тест проверяет анализ фото и выбор сценария."
        )
    except Exception as exc:
        print(f"[Telegram demo] error={type(exc).__name__}", flush=True)

# ==========================================
# 5. МАРШРУТИЗАЦИЯ FLASK
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return f"Студия Садовод AI: HTTP-сервер работает. Версия {HOTFIX_VERSION}. Это не проверка доступности Google.", 200

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
    request_id = uuid.uuid4().hex[:12]

    def fail(message, http_status, code, provider_status=None):
        body = {"error": message, "code": code, "request_id": request_id}
        if provider_status is not None:
            body["provider_http_status"] = provider_status
        print(
            f"[analyze] request_id={request_id} code={code} "
            f"provider_http_status={provider_status}", flush=True
        )
        return jsonify(body), http_status

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Ожидается JSON с фотографией.", 400, "INVALID_JSON")
    img_b64 = data.get("image")
    mime_type = data.get("mime_type", "image/jpeg")
    if not isinstance(img_b64, str) or not img_b64:
        return fail("Фотография не дошла до сервера.", 400, "IMAGE_REQUIRED")
    if not isinstance(mime_type, str) or mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        return fail("Выберите изображение JPEG, PNG или WebP.", 415, "UNSUPPORTED_IMAGE_TYPE")
    # Это базовый технический фильтр, не полноценная проверка изображения.
    if len(img_b64) > 14_000_000:
        return fail("Изображение слишком большое.", 413, "IMAGE_TOO_LARGE")
    try:
        base64.b64decode(img_b64, validate=True)
    except (ValueError, TypeError):
        return fail("Повреждены данные фотографии. Выберите файл повторно.", 400, "INVALID_BASE64")

    try:
        url = build_gemini_url()
    except ValueError as exc:
        return fail(str(exc), 503, "VERTEX_CONFIG_ERROR")

    try:
        vertex_token = get_vertex_token()
    except Exception as exc:
        # Не выводим str(exc): исключение может содержать детали credentials.
        print(f"[Google auth] request_id={request_id} error={type(exc).__name__}", flush=True)
        return fail("Не удалось получить серверный токен Google. Проверьте credentials и права сервисного аккаунта.", 503, "GOOGLE_AUTH_FAILED")

    prompt_instruction = (
        "Опиши товар на фото: это может быть одежда, обувь, посуда или вещь для дома. "
        "Напиши 3 разных креативных промпта для рекламного видео. "
        "Не придумывай бренд, материал, цену или комплектацию, которых нельзя установить по фото. "
        "Ответ на русском. Формат: каждый промпт начинается с новой строки "
        "и с цифры '1. ', '2. ', '3. '."
    )
    headers = {
        "Authorization": f"Bearer {vertex_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inlineData": {"mimeType": mime_type, "data": img_b64}},
                {"text": prompt_instruction},
            ],
        }],
    }
    print(
        f"[analyze] version={HOTFIX_VERSION} request_id={request_id} "
        f"model={GEMINI_MODEL} location={GEMINI_LOCATION}", flush=True
    )
    try:
        # Нет автоматического повторения и переключения моделей: один запрос.
        response = requests.post(url, headers=headers, json=payload, timeout=(10, 120))
    except requests.exceptions.Timeout:
        return fail("Истекло время ожидания Google. Повторите позднее.", 504, "GOOGLE_TIMEOUT")
    except requests.exceptions.RequestException:
        return fail("Не удалось соединиться с Google. Повторите позднее.", 502, "GOOGLE_NETWORK_ERROR")

    # Сохраняем HTTP-код Google, но не отправляем пользователю сырой текст ошибки.
    if response.status_code != 200:
        public_http = 503 if response.status_code == 429 or response.status_code >= 500 else 502
        message = f"Google API: HTTP {response.status_code}. {google_error_message(response.status_code)} Код обращения: {request_id}."
        return fail(message, public_http, f"GOOGLE_HTTP_{response.status_code}", response.status_code)
    try:
        response_data = response.json()
        candidates = response_data.get("candidates") or []
        candidate = candidates[0] if candidates else {}
        parts = (candidate.get("content") or {}).get("parts") or []
        texts = [part.get("text", "") for part in parts
                 if isinstance(part, dict) and not part.get("thought")
                 and isinstance(part.get("text"), str)]
        gemini_text = "\n".join(texts).strip()
    except (ValueError, TypeError, AttributeError, IndexError):
        return fail("Google вернул неожиданный формат ответа.", 502, "GOOGLE_RESPONSE_INVALID")
    if not gemini_text:
        return fail("Google не вернул текст сценариев; возможна фильтрация запроса. Выберите другое допустимое фото.", 502, "GOOGLE_EMPTY_RESPONSE")

    lines = gemini_text.split('\n')
    prompts = [line.strip() for line in lines if line.strip().startswith(('1.', '2.', '3.'))]
    if not prompts:
        prompts = [gemini_text]
    return jsonify({"prompts": prompts, "request_id": request_id})

@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    chat_id = data.get("chat_id")
    prompt = data.get("prompt")
    
    if chat_id and prompt:
        threading.Thread(target=process_video_generation, args=(chat_id, prompt)).start()
        
    return jsonify({"status": "demo_only", "video_generated": False})

if __name__ == "__main__":
    print(f"[startup] {HOTFIX_VERSION} model={GEMINI_MODEL} location={GEMINI_LOCATION}", flush=True)
    set_webhook()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
