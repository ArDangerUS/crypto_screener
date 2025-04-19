import requests
import time
from binance.um_futures import UMFutures
from tradingview_ta import TA_Handler, Interval, Exchange

INTERVAL = Interval.INTERVAL_1_HOUR
TELEGRAM_TOKEN = ""
TELEGRAM_CHANNEL = ""

client = UMFutures


def get_data(symbol):
    output = TA_Handler(symbol=symbol,
                        exchange="Binance",
                        screener="Crypto",
                        interval=INTERVAL)
    activity = output.get_analysis().summary
    activity["SYMBOL"] = symbol
    return activity


def get_symbols():
    tickers = client.mark_price()
    symbols = []
    for i in tickers:
        ticker = i["symbol"]
        symbols.append(ticker)
    return symbols


def send_message(text):
    res = requests.get(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}sendMessage',
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
            if (data["RECCOMANDATION"] == "STRONG_BUY"):
                longs.append(data["SYMBOL"])
            if (data["RECCOMANDATION"] == "STRONG_SELL"):
                shorts.append(data["SYMBOL"])
            time.sleep(0.01)
        except:
            pass
    print("longs:")
    print(longs)
    print("shorts")
    print(shorts)
    return longs, shorts



