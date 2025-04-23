import requests
import time
from binance.um_futures import UMFutures
from tradingview_ta import TA_Handler, Interval, Exchange
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL")

INTERVAL = Interval.INTERVAL_1_MINUTE

client = UMFutures()


def get_data(symbol):
    output = TA_Handler(symbol=symbol,
                        exchange="Binance",
                        screener="Crypto",
                        interval=INTERVAL)
    activity = output.get_analysis().summary
    activity["SYMBOL"] = symbol
    return activity


def get_symbols():
    # Укажите список токенов, которые хотите анализировать
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]
    return symbols


def send_message(text):
    res = requests.get(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                       params=dict(chat_id=TELEGRAM_CHANNEL, text=text))


symbols = get_symbols()
longs = []
shorts = []


def first_data():
    print("Searching data")
    send_message("Searching data")
    for i in symbols:
        try:
            data = get_data(i)
            if data["RECOMMENDATION"] == "STRONG_BUY":
                longs.append(data["SYMBOL"])
            if data["RECOMMENDATION"] == "STRONG_SELL":
                shorts.append(data["SYMBOL"])
            time.sleep(0.01)
        except Exception as e:
            print(f"Error fetching data for {i}: {e}")
    print("longs:")
    print(longs)
    print("shorts")
    print(shorts)
    return longs, shorts


print('Start')
send_message("Start")
first_data()

while True:
    print("NEW ROUND")
    for i in symbols:
        try:
            data = get_data(i)
            if data["RECOMMENDATION"] == "STRONG_BUY" and data['SYMBOL'] not in longs:
                print(data["SYMBOL"], 'Buy')
                text = data["SYMBOL"] + " BUY"
                send_message(text)
                longs.append(data["SYMBOL"])

            if data["RECOMMENDATION"] == "STRONG_SELL" and data['SYMBOL'] not in shorts:
                print(data["SYMBOL"], 'Sell')
                text = data["SYMBOL"] + " SELL"
                send_message(text)
                shorts.append(data["SYMBOL"])
            time.sleep(0.1)
        except Exception as e:
            print(f"Error fetching data for {i}: {e}")
