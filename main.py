from flask import Flask, request, jsonify
import os
import google.generativeai as genai
import PIL.Image

app = Flask(__name__)

# Достаем ключи из сейфа Render
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
            padding: 20px; 
            margin: 0;
        }
        .btn { 
            background-color: var(--tg-theme-button-color, #3390ec); 
            color: var(--tg-theme-button-text-color, #fff); 
            border: none; 
            padding: 15px 20px; 
            border-radius: 10px; 
            font-size: 16px; 
            font-weight: bold; 
            width: 100%; 
            margin-top: 20px; 
            cursor: pointer; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        #status {
            margin-top: 15px;
            font-size: 14px;
            font-weight: bold;
            color: #ff9800;
        }
        #result {
            margin-top: 20px;
            text-align: left;
            background: var(--tg-theme-secondary-bg-color, #fff);
            padding: 15px;
            border-radius: 10px;
            display: none;
            white-space: pre-wrap;
            font-size: 14px;
            border: 1px solid #ddd;
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <h2>📸 Анализ товара</h2>
    <p>Сфотографируйте товар или выберите из галереи, чтобы нейросеть предложила сценарии для рекламного видео.</p>
    
    <!-- Наш пуленепробиваемый элемент для вызова системной камеры/галереи -->
    <input type="file" id="fileInput" accept="image/*" style="display: none;">
    
    <!-- Видимая красивая кнопка -->
    <button id="mainBtn" class="btn" onclick="document.getElementById('fileInput').click();">📷 Сделать фото / Выбрать</button>
    
    <div id="status"></div>
    <div id="result"></div>
    
    <script>
        // Инициализация Telegram
        Telegram.WebApp.ready();
        Telegram.WebApp.expand();
        
        const fileInput = document.getElementById('fileInput');
        const mainBtn = document.getElementById('mainBtn');
        const statusDiv = document.getElementById('status');
        const resultDiv = document.getElementById('result');

        // Как только пользователь выбрал файл
        fileInput.addEventListener('change', function() {
            if (fileInput.files.length === 0) return;
            
            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append('image', file);

            // Меняем интерфейс
            mainBtn.disabled = true;
            mainBtn.innerText = "⏳ Идёт анализ фото...";
            statusDiv.innerText = "Нейросеть думает (это займет 5-10 сек)...";
            resultDiv.style.display = "none";

            // Отправляем фото на наш Python-сервер
            fetch('/analyze', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                mainBtn.disabled = false;
                mainBtn.innerText = "📷 Выбрать другое фото";
                statusDiv.innerText = "";
                
                if (data.error) {
                    Telegram.WebApp.showAlert("Ошибка: " + data.error);
                } else {
                    resultDiv.style.display = "block";
                    resultDiv.innerText = data.text;
                }
            })
            .catch(error => {
                mainBtn.disabled = false;
                mainBtn.innerText = "📷 Сделать фото / Выбрать";
                statusDiv.innerText = "Произошла ошибка связи с сервером.";
                Telegram.WebApp.showAlert("Ошибка при отправке.");
            });
            
            // Очищаем input
            fileInput.value = "";
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return HTML

@app.route('/analyze', methods=['POST'])
def analyze():
    # Проверяем, есть ли ключ
    if not GEMINI_API_KEY:
        return jsonify({"error": "Ключ Gemini не найден на сервере!"}), 500
        
    if 'image' not in request.files:
        return jsonify({"error": "Фотография не получена сервером"}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "Пустой файл"}), 400
        
    try:
        # Для Gemini лучше передавать картинку через библиотеку PIL
        img = PIL.Image.open(file.stream)
        
        # Выбираем быструю и умную модель
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Наш промпт
        prompt = "Ты эксперт по продажам на маркетплейсах (Wildberries, Ozon). Посмотри на это фото и скажи, что это за товар. Предложи 3 креативных и продающих сценария для короткого рекламного видеоролика этого товара. Форматируй текст красиво, используй эмодзи."
        
        # Просим сгенерировать ответ
        response = model.generate_content([prompt, img])
        
        return jsonify({"text": response.text})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
