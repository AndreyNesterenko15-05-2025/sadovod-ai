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
        const chatId =
