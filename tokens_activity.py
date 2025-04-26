import asyncio
import websockets
import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# WebSocket URLs
BINANCE_WS_URL_FUTURES = "wss://fstream.binance.com/ws/!aggTrade@arr"
BINANCE_WS_URL_SPOT = "wss://stream.binance.com:9443/ws/!aggTrade@arr"

# REST API для получения данных
BINANCE_API_URL_FUTURES = "https://fapi.binance.com/fapi/v1/ticker/24hr"
BINANCE_API_URL_SPOT = "https://api.binance.com/api/v3/ticker/24hr"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHANNEL")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML'
    }
    requests.post(url, data=payload)

def fetch_24h_data(symbol, is_futures=True):
    try:
        url = BINANCE_API_URL_FUTURES if is_futures else BINANCE_API_URL_SPOT
        response = requests.get(url, params={'symbol': symbol})
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Ошибка запроса данных для {symbol}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Ошибка получения данных 24h для {symbol}: {e}")
        return None

async def listen_binance(url, is_futures=True):
    async with websockets.connect(url) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)

            for trade in data:
                symbol = trade['s']
                price = float(trade['p'])
                quantity = float(trade['q'])
                is_buyer_maker = trade['m']

                total_usdt = price * quantity

                if total_usdt > 1_000_000 and not is_buyer_maker:  # покупки
                    ticker_data = fetch_24h_data(symbol, is_futures)
                    if ticker_data:
                        price_change = float(ticker_data['priceChangePercent'])
                        volume_usdt = float(ticker_data['quoteVolume'])
                        last_price = float(ticker_data['lastPrice'])

                        platform = "Binance Futures" if is_futures else "Binance Spot"

                        message_text = (
                            f"🎰 #{symbol} покупают 🔫\n"
                            f"Сумма сделки: {total_usdt/1_000_000:.2f}M USDT\n"
                            f"P: {last_price:.6f} {'⬆️' if price_change > 0 else '⬇️'} ({price_change:.2f}%)\n"
                            f"Объем за 24ч: {volume_usdt/1_000_000:.2f}M USDT\n"
                            f"<i>{platform}</i>"
                        )
                        send_telegram_message(message_text)

async def main():
    await asyncio.gather(
        listen_binance(BINANCE_WS_URL_FUTURES, is_futures=True),
        listen_binance(BINANCE_WS_URL_SPOT, is_futures=False)
    )

if __name__ == "__main__":
    asyncio.run(main())
