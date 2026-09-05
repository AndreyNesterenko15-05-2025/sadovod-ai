from flask import Flask, request, jsonify
import os
import json
import google.generativeai as genai
import PIL.Image

app = Flask(__name__)

# Достаем ключ от Gemini из сейфа Render
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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
        body { 
            font-family: sans-serif; 
            background-color: var(--tg-theme-bg-color, #f4f4f5); 
            color: var(--tg-theme-text-color, #000); 
            text-align: center; 
            padding: 15px; 
            margin: 0;
        }
        .btn { 
            background-color: var(--tg-theme-button-color, #3390ec); 
            color: var(--tg-theme-button-text-color, #fff); 
            border: none; 
            padding: 15px; 
            border-radius: 10px; 
            font-size: 16px; 
            font-weight: bold; 
            width: 100%; 
            margin-top: 15px; 
            cursor: pointer; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .scenario-card { 
            background: var(--tg-theme-secondary-bg-color, #fff); 
            border: 1px solid #ddd; 
            padding: 15px; 
            border-radius: 10px; 
            margin-top: 15px; 
            text-align: left; 
        }
        .scenario-title { font-weight: bold; font-size: 16px; margin-bottom: 5px; color: var(--tg-theme-button-color, #3390ec); }
        .scenario-desc { font-size: 14px; margin-bottom: 10px; }
        #status { margin-top: 15px; font-size: 14px; font-weight: bold; color: #ff9800; }
        #step2, #step3 { display: none; }
        .prompt-box { 
            background: #1e1e1e; 
            color: #4ade80; 
            padding: 15px; 
            border-radius: 10px; 
            text-align: left; 
            font-family: monospace; 
            font-size: 13px; 
            white-space: pre-wrap; 
            line-height: 1.4; 
            margin-top: 15px;
        }
    </style>
</head>
<body>
    <div id="step1">
        <h2>📸 Анализ товара</h2>
        <p>Загрузите фото, чтобы ИИ придумал 3 сценария для рекламного видео.</p>
        <input type="file" id="fileInput" accept="image/*" style="display: none;">
        <button id="mainBtn" class="btn" onclick="document.getElementById('fileInput').click();">📷 Сделать фото / Выбрать</button>
        <div id="status"></div>
    </div>

    <div id="step2">
        <h2>🎬 Выберите сценарий</h2>
        <div id="scenariosContainer"></div>
        <button class="btn" style="background-color: #888;" onclick="location.reload();">🔄 Назад к фото</button>
    </div>

    <div id="step3">
        <h2>⚙️ Режиссерский Промпт</h2>
        <p>Идеальный технический промпт на английском для нейросети генерации видео:</p>
        <div id="finalPrompt" class="prompt-box"></div>
        <button id="copyBtn" class="btn" style="background-color: #8b5cf6;" onclick="copyPrompt()">📋 Скопировать промпт</button>
        <button id="genVideoBtn" class="btn" style="background-color: #10B981;" onclick="Telegram.WebApp.showAlert('В MVP: Промпт готов! В полной версии сервер отправит его в Google Veo, а Бот пришлет вам готовое видео прямо в чат для скачивания в галерею!');">🎥 Сгенерировать видео (Демо)</button>
        <button class="btn" style="background-color: #888;" onclick="location.reload();">🔄 Начать заново</button>
    </div>
    
    <script>
        Telegram.WebApp.ready();
        Telegram.WebApp.expand();
        
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
            statusDiv.innerText = "⏳ Нейросеть изучает товар (5-10 сек)...";

            fetch('/get_scenarios', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    Telegram.WebApp.showAlert("Ошибка: " + data.error);
                    mainBtn.disabled = false;
                    statusDiv.innerText = "";
                    return;
                }
                
                scenariosData = data.scenarios;
                document.getElementById('step1').style.display = "none";
                document.getElementById('step2').style.display = "block";
                
                const container = document.getElementById('scenariosContainer');
                container.innerHTML = "";
                
                scenariosData.forEach((scen, index) => {
                    const card = document.createElement('div');
                    card.className = "scenario-card";
                    card.innerHTML = `
                        <div class="scenario-title">Вариант ${index + 1}: ${scen.title}</div>
                        <div class="scenario-desc">${scen.description}</div>
                        <button class="btn" style="margin-top: 5px; padding: 10px;" onclick="generatePrompt(${index})">Выбрать этот вариант</button>
                    `;
                    container.appendChild(card);
                });
            })
            .catch(e => {
                Telegram.WebApp.showAlert("Ошибка связи с сервером.");
                mainBtn.disabled = false;
                statusDiv.innerText = "";
            });
        });

        window.generatePrompt = function(index) {
            const scenario = scenariosData[index];
            document.getElementById('step2').style.display = "none";
            document.getElementById('step1').style.display = "block";
            mainBtn.style.display = "none";
            statusDiv.innerText = "⚙️ Пишу профессиональный промпт на английском...";
            
            const formData = new FormData();
            formData.append('image', uploadedImage);
            formData.append('scenario_title', scenario.title);
            formData.append('scenario_desc', scenario.description);

            fetch('/generate_prompt', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if(data.error) {
                    Telegram.WebApp.showAlert("Ошибка: " + data.error);
                    location.reload();
                    return;
                }
                document.getElementById('step1').style.display = "none";
                document.getElementById('step3').style.display = "block";
                document.getElementById('finalPrompt').innerText = data.prompt;
            })
            .catch(e => {
                Telegram.WebApp.showAlert("Ошибка генерации промпта.");
                location.reload();
            });
        }

        window.copyPrompt = function() {
            const text = document.getElementById('finalPrompt').innerText;
            navigator.clipboard.writeText(text).then(() => {
                Telegram.WebApp.showAlert("✅ Промпт скопирован! Теперь его можно вставить в ИИ-генератор видео.");
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
    if 'image' not in request.files: return jsonify({"error": "Нет фото"}), 400
    
    try:
        img = PIL.Image.open(request.files['image'].stream)
        model = genai.GenerativeModel('gemini-3.8-flash')
        
        prompt = """You are a top-tier e-commerce marketer. Analyze the product in the image. 
        Create exactly 3 short, creative scenarios for a short promotional video (Reels/Shorts).
        Respond ONLY with a valid JSON array containing exactly 3 objects. 
        Do not wrap the JSON in markdown blocks (like ```json).
        Each object must have two string keys: "title" (a catchy title in Russian) and "description" (a brief 1-2 sentence description in Russian)."""
        
        response = model.generate_content([prompt, img])
        text = response.text.strip()
        
        # Очищаем текст от возможных артефактов ИИ
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()
            
        scenarios = json.loads(text)
        return jsonify({"scenarios": scenarios})
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": "Ошибка генерации сценариев. Попробуйте еще раз."}), 500

@app.route('/generate_prompt', methods=['POST'])
def generate_prompt():
    if 'image' not in request.files: return jsonify({"error": "Нет фото"}), 400
        
    try:
        img = PIL.Image.open(request.files['image'].stream)
        scenario_title = request.form.get('scenario_title', '')
        scenario_desc = request.form.get('scenario_desc', '')
        
        model = genai.GenerativeModel('gemini-3.8-flash')
        
        prompt = f"""Act as an expert AI Video Prompt Engineer. 
        I am providing an image of a product. 
        The chosen video scenario is: Title: "{scenario_title}", Description: "{scenario_desc}".
        Write a highly detailed, professional text-to-video prompt IN ENGLISH for a model like Google Veo, Sora, or Runway Gen-3.
        Include specific details about:
        1. The main subject (based on the image).
        2. Camera movement (e.g., slow pan, zoom, tracking shot).
        3. Lighting and atmosphere (e.g., cinematic lighting, studio lighting, natural sunlight).
        4. Action or motion occurring in the scene.
        5. Visual style (e.g., photorealistic, 4k, hyperdetailed).
        
        The output must be ONLY the English prompt text, ready to be copy-pasted. Do not include any intro, outro, or explanations."""
        
        response = model.generate_content([prompt, img])
        return jsonify({"prompt": response.text.strip()})
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": "Ошибка генерации промпта."}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
