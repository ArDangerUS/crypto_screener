import requests
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL")

def send_message(text):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    params = {
        'chat_id': TELEGRAM_CHANNEL,
        'text': text
    }
    response = requests.get(url, params=params)
    return response.json()


# Отправка тестового сообщения
response = send_message("Это тестовое сообщение")
print(response)
