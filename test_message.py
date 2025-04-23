import requests

TELEGRAM_TOKEN = "7647749358:AAEMIsjETJV1-hTjzt5KuScksf2vAw4EOKM"
TELEGRAM_CHANNEL = "@crypto_screener391"  # или "-1001234567890"


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
