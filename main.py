from flask import Flask, request, jsonify, url_for
import os
import json
import uuid
import time
import requests
import google.generativeai as genai
import PIL.Image

app = Flask(__name__)

# Папка для публичных картинок (нужна для Luma AI)
os.makedirs('static', exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LUMA_API_KEY = os.environ.get("LUMA_API_KEY")
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
        <p>Luma AI генерирует ролик. Это займет около 3-5 минут.</p>
        <div id="renderStatus" style="font-weight:bold; color:#10B981; margin-top:20px;">Инициализация...</div>
    </div>
    
    <script>
        Telegram.WebApp.ready();
        Telegram.WebApp.expand();
        // Получаем ID пользователя для отправки видео в личку!
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
                
                // Запускаем поллинг (каждые 10 секунд спрашиваем сервер, готово ли видео)
                const jobId = data.job_id;
                document.getElementById('renderStatus').innerText = "Задача отправлена в Luma. Рендерим 0%...";
                
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
                            document.getElementById('renderStatus').innerText = "❌ Ошибка генерации видео в Luma.";
                        } else {
                            document.getElementById('renderStatus').innerText = "Рендеринг в процессе... Пожалуйста, подождите.";
                        }
                    });
                }, 10000); // 10 секунд
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
        
        # 1. Сохраняем фото публично, чтобы Luma могла его скачать
        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = os.path.join('static', filename)
        file.save(filepath)
        # Получаем URL нашего сервера
        host_url = request.url_root.rstrip('/')
        image_url = f"{host_url}/static/{filename}"
        
        # 2. Просим Gemini написать англоязычный видео-промпт
        model = genai.GenerativeModel('gemini-3.8-flash')
        img_for_prompt = PIL.Image.open(filepath)
        prompt_cmd = f"Write a specific, English text-to-video prompt for Luma API based on this image. Scenario: {scenario_title} - {scenario_desc}. Output ONLY the prompt."
        video_prompt = model.generate_content([prompt_cmd, img_for_prompt]).text.strip()
        
        # 3. Отправляем задачу в Luma AI
        headers = {"Authorization": f"Bearer {LUMA_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "prompt": video_prompt,
            "keyframes": {"frame0": {"type": "image", "url": image_url}}
        }
        res = requests.post("https://api.lumalabs.ai/v1/generations", json=payload, headers=headers)
        
        if res.status_code != 200:
            return jsonify({"error": f"Luma API error: {res.text}"}), 500
            
        job_id = res.json().get("id")
        return jsonify({"job_id": job_id})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/check_status/<job_id>', methods=['POST'])
def check_status(job_id):
    chat_id = request.form.get('chat_id')
    headers = {"Authorization": f"Bearer {LUMA_API_KEY}", "Content-Type": "application/json"}
    
    # Спрашиваем Luma о статусе видео
    res = requests.get(f"https://api.lumalabs.ai/v1/generations/{job_id}", headers=headers)
    data = res.json()
    
    state = data.get("state")
    if state == "completed":
        video_url = data.get("assets", {}).get("video")
        # 🔥 ВИДЕО ГОТОВО! Отправляем его напрямую в Телеграм-чат пользователя
        tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
        requests.post(tg_url, data={"chat_id": chat_id, "video": video_url})
        return jsonify({"status": "completed"})
        
    elif state == "failed":
        return jsonify({"status": "failed"})
        
    return jsonify({"status": "processing"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
