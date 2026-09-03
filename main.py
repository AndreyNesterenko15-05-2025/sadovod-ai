from flask import Flask

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Садовод AI</title>
    <!-- Подключаем библиотеку Telegram -->
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { 
            font-family: sans-serif; 
            background-color: var(--tg-theme-bg-color, #f4f4f5); 
            color: var(--tg-theme-text-color, #000); 
            text-align: center; 
            padding: 20px; 
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
        }
    </style>
</head>
<body>
    <h2>📸 Загрузка товара</h2>
    <p>Тестовый интерфейс Mini App успешно запущен!</p>
    <button class="btn" onclick="Telegram.WebApp.showAlert('Здесь будет открываться камера или галерея телефона!')">Выбрать фото</button>
    
    <script>
        Telegram.WebApp.ready();
        Telegram.WebApp.expand();
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return HTML

if __name__ == '__main__':
    # Render требует привязки именно к порту 10000, в отличие от Replit
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
