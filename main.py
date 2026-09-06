from flask import Flask, request, jsonify, url_for
import os
import json
import uuid
import time
import requests
import google.generativeai as genai
import PIL.Image

app = Flask(__name__)

# Папка для публичных картинок
os.makedirs('static', exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DEAPI_KEY = os.environ.get("DEAPI_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Студия Садовод AI</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: sans-serif; background-color: var(--tg-theme-bg-color, #f4f4f5); color: var(--tg-theme-text-color, #000); text-align: center; padding: 15px; margin: 0; }
        .btn { background-color: var(--tg-theme-button-color, #3390ec); color: var(--tg-theme-button-text-color, #fff); border: none; padding: 15px; border-radius: 10px; font-size: 16px; font-weight: bold; width: 100%; margin-top: 15px; cursor: pointer; }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .scenario-card { background: var(--tg-theme-secondary-bg-color, #fff); border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-top: 15px; text-align: left; }
        .scenario-title { font-weight: bold; font-size: 16px; margin-bottom: 5px; color: var(--tg-theme-button-color, #3390ec); }
        #status { margin-top: 15px; font-size: 14px; font-weight: bold; color: #ff9800; }
        #step2, #step3 { display: none; }
    </style>
</head>
<body>
    <div id="step1">
        <h2>📸 Анализ товара</h2>
        <input type="file" id="fileInput" accept="image/*" style="display: none;">
        <button id="mainBtn" class="btn" onclick="document.getElementById('fileInput').click();">📷 Сделать фото / Выбрать</button>
        <div id="status"></div>
    </div>

    <div id="step2">
        <h2>🎬 Выберите сценарий</h2>
        <div id="scenariosContainer"></div>
    </div>

    <div id="step3">
        <h2>🎥 Рендеринг видео...</h2>
        <p>deAPI генерирует ролик. Это займет несколько минут.</p>
        <div id="renderStatus" style="font-weight:bold; color:#10B981; margin-top:20px;">Инициализация...</div>
    </div>
    
    <script>
        Telegram.WebApp.ready();
        Telegram.WebApp.expand();
        const chatId = Telegram.WebApp.initDataUnsafe?.user?.id || "";
        
        let uploadedImage = null;
        let scenariosData = [];

        const fileInput = document.getElementById('fileInput');
        const mainBtn = document.getElementById('mainBtn');
        const statusDiv = document.getElementById('status');

        fileInput.addEventListener('change', function() {
            if (this.files.length === 0) return;
            uploadedImage = this.files[0];
            const formData = new FormData();
            formData.append('image', uploadedImage);

            mainBtn.disabled = true;
            statusDiv.innerText = "⏳ Gemini анализирует товар...";

            fetch('/get_scenarios', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.error) { Telegram.WebApp.showAlert(data.error); return; }
                scenariosData = data.scenarios;
                document.getElementById('step1').style.display = "none";
                document.getElementById('step2').style.display = "block";
                
                const container = document.getElementById('scenariosContainer');
                container.innerHTML = "";
                scenariosData.forEach((scen, index) => {
                    const card = document.createElement('div');
                    card.className = "scenario-card";
                    card.innerHTML = `
                        <div class="scenario-title">${scen.title}</div>
                        <div style="font-size: 14px;">${scen.description}</div>
                        <button class="btn" style="padding: 10px;" onclick="startVideo(${index})">🎥 Создать видео!</button>
                    `;
                    container.appendChild(card);
                });
            });
        });

        window.startVideo = function(index) {
            if (!chatId) { Telegram.WebApp.showAlert("Ошибка: не могу определить ваш Telegram ID."); return; }
            
            document.getElementById('step2').style.display = "none";
            document.getElementById('step3').style.display = "block";
            
            const scenario = scenariosData[index];
            const formData = new FormData();
            formData.append('image', uploadedImage);
            formData.append('scenario_title', scenario.title);
            formData.append('scenario_desc', scenario.description);
            formData.append('chat_id', chatId);

            fetch('/start_generation', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if(data.error) { document.getElementById('renderStatus').innerText = "Ошибка: " + data.error; return; }
                
                const jobId = data.job_id;
                document.getElementById('renderStatus').innerText = "Задача отправлена. Рендерим...";
                
                const interval = setInterval(() => {
                    const fd = new FormData();
                    fd.append('chat_id', chatId);
                    
                    fetch('/check_status/' + jobId, { method: 'POST', body: fd })
                    .then(r => r.json())
                    .then(statusData => {
                        if(statusData.status === "completed") {
                            clearInterval(interval);
                            document.getElementById('renderStatus').innerText = "✅ ВИДЕО ГОТОВО! Проверьте чат с ботом!";
                            Telegram.WebApp.showAlert("Видео успешно отправлено вам в личные сообщения!");
                        } else if (statusData.status === "failed") {
                            clearInterval(interval);
                            document.getElementById('renderStatus').innerText = "❌ Ошибка генерации видео.";
                        } else {
                            document.getElementById('renderStatus').innerText = "Рендеринг в процессе... Пожалуйста, подождите.";
                        }
                    });
                }, 10000); // Опрашиваем каждые 10 секунд
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return HTML

@app.route('/get_scenarios', methods=['POST'])
def get_scenarios():
    try:
        img = PIL.Image.open(request.files['image'].stream)
        model = genai.GenerativeModel('gemini-3.8-flash')
        prompt = """Analyze the product. Create 3 short, creative scenarios for a promo video.
        Respond ONLY with a JSON array containing 3 objects with keys: "title" and "description" (in Russian). Do not use markdown blocks."""
        response = model.generate_content([prompt, img])
        text = response.text.replace('```json', '').replace('```', '').strip()
        return jsonify({"scenarios": json.loads(text)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/start_generation', methods=['POST'])
def start_generation():
    try:
        file = request.files['image']
        scenario_title = request.form.get('scenario_title')
        scenario_desc = request.form.get('scenario_desc')
        
        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = os.path.join('static', filename)
        file.save(filepath)
        host_url = request.url_root.rstrip('/')
        image_url = f"{host_url}/static/{filename}"
        
        model = genai.GenerativeModel('gemini-3.8-flash')
        img_for_prompt = PIL.Image.open(filepath)
        prompt_cmd = f"Write a specific, English text-to-video prompt for an AI generator based on this image. Scenario: {scenario_title} - {scenario_desc}. Output ONLY the prompt."
        video_prompt = model.generate_content([prompt_cmd, img_for_prompt]).text.strip()
        
        # Интеграция с deAPI.ai (новый корректный URL)
        url = "https://api.deapi.ai/api/v2/videos/animations" 
        headers = {
            "Authorization": f"Bearer {DEAPI_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "minimax-h3-33b-turbo-int8", # Флагманская модель MiniMax
            "image_url": image_url,
            "prompt": video_prompt
        }
        res = requests.post(url, json=payload, headers=headers)
        
        if res.status_code != 200:
            # Предохранитель от HTML-ответов сторонних серверов
            try:
                error_details = res.json()
            except:
                error_details = f"Сбой маршрутизации (Код {res.status_code}). Провайдер вернул веб-страницу вместо данных."
            return jsonify({"error": f"API error: {error_details}"}), 500
            
        job_id = res.json().get("job_id") or res.json().get("id") or res.json().get("request_id")
        return jsonify({"job_id": job_id})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/check_status/<job_id>', methods=['POST'])
def check_status(job_id):
    chat_id = request.form.get('chat_id')
    headers = {"Authorization": f"Bearer {DEAPI_KEY}", "Content-Type": "application/json"}
    
    # Новый URL для поллинга (проверки статуса)
    url = f"https://api.deapi.ai/api/v2/jobs/{job_id}"
    res = requests.get(url, headers=headers)
    
    if res.status_code != 200:
        return jsonify({"status": "processing"})
        
    data = res.json()
    status = data.get("status", "").upper()
    
    # Универсальный парсинг статуса готовности для агрегатора
    if status in ["COMPLETED", "SUCCEEDED", "DONE"] or "video_url" in data or "result_url" in data:
        video_url = data.get("video_url") or data.get("result_url") or data.get("url")
        
        if video_url:
            tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
            requests.post(tg_url, data={"chat_id": chat_id, "video": video_url})
            return jsonify({"status": "completed"})
            
    if status in ["FAILED", "CANCELLED", "ERROR"]:
        return jsonify({"status": "failed"})
        
    return jsonify({"status": "processing"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
