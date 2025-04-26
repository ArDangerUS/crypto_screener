import asyncio
import websockets
import json
import requests
import os
import logging
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("binance_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("binance_bot")

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHANNEL")

# Binance URLs
BINANCE_WS_URL_FUTURES = "wss://fstream.binance.com/ws"
BINANCE_WS_URL_SPOT = "wss://stream.binance.com:9443/ws"
BINANCE_API_URL_FUTURES = "https://fapi.binance.com/fapi/v1/ticker/24hr"
BINANCE_API_URL_SPOT = "https://api.binance.com/api/v3/ticker/24hr"

# Settings
MIN_USDT_VOLUME_CHANGE = 100000  # Minimum USDT volume change to track (100K)
MIN_PRICE_CHANGE_PERCENT = 0.5  # Minimum price change percentage to consider as significant
ATTACK_THRESHOLD = 3  # Number of large buys to trigger an attack alert
ATTACK_WINDOW_MINUTES = 10  # Time window to check for attack patterns
RECONNECT_DELAY = 5  # Delay before reconnection attempt in seconds
MAX_RECONNECT_ATTEMPTS = 10  # Maximum number of reconnection attempts
VOLUME_HISTORY_SIZE = 5  # Number of volume snapshots to keep for each symbol

# Trade memory
recent_trades = {}

# Volume history for tracking changes
volume_history = {}

# Rate limiting for API calls
api_call_timestamps = {}
API_CALL_LIMIT = 5  # calls per second
API_CALL_WINDOW = 1  # seconds

# Message counters
message_counter = {"futures": 0, "spot": 0}


def send_telegram_message(text):
    """Send message to Telegram channel"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logger.error(f"Failed to send Telegram message: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False


def can_make_api_call(endpoint):
    """Check if we can make an API call considering rate limits"""
    current_time = time.time()

    # Initialize timestamp list for this endpoint if not exists
    if endpoint not in api_call_timestamps:
        api_call_timestamps[endpoint] = []

    # Filter out old timestamps
    api_call_timestamps[endpoint] = [
        ts for ts in api_call_timestamps[endpoint]
        if current_time - ts < API_CALL_WINDOW
    ]

    # Check if we're under the limit
    if len(api_call_timestamps[endpoint]) < API_CALL_LIMIT:
        api_call_timestamps[endpoint].append(current_time)
        return True

    return False


async def listen_binance(is_futures=True, reconnect_attempt=0):
    """Connect to Binance WebSocket and listen for ticker data"""
    url = BINANCE_WS_URL_FUTURES if is_futures else BINANCE_WS_URL_SPOT
    platform_name = "Futures" if is_futures else "Spot"
    platform_key = "futures" if is_futures else "spot"

    try:
        logger.info(f"Connecting to Binance {platform_name} WebSocket...")
        async with websockets.connect(url) as websocket:
            # Reset reconnect counter on successful connection
            reconnect_attempt = 0

            # Subscribe to ticker stream
            subscribe_request = {
                "method": "SUBSCRIBE",
                "params": ["!ticker@arr"],
                "id": 1
            }

            logger.info(f"Sending subscription request to {platform_name}...")
            await websocket.send(json.dumps(subscribe_request))

            # Get subscription confirmation
            response = await websocket.recv()
            logger.info(f"Subscription response from {platform_name}: {response}")

            # Process messages
            while True:
                try:
                    message = await websocket.recv()
                    message_counter[platform_key] += 1

                    # Log summary every 100 messages
                    if message_counter[platform_key] % 100 == 0:
                        logger.info(f"Received {message_counter[platform_key]} messages from {platform_name}")

                    process_ticker_message(message, is_futures)
                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning(f"{platform_name} WebSocket connection closed: {e}")
                    raise

    except (websockets.exceptions.ConnectionClosed,
            websockets.exceptions.ConnectionError,
            websockets.exceptions.InvalidStatusCode,
            asyncio.exceptions.TimeoutError) as e:
        if reconnect_attempt < MAX_RECONNECT_ATTEMPTS:
            wait_time = RECONNECT_DELAY * (2 ** min(reconnect_attempt, 4))  # Exponential backoff
            logger.warning(
                f"{platform_name} connection error: {e}. Reconnecting in {wait_time}s (attempt {reconnect_attempt + 1}/{MAX_RECONNECT_ATTEMPTS})")
            await asyncio.sleep(wait_time)
            return await listen_binance(is_futures, reconnect_attempt + 1)
        else:
            logger.error(f"Max reconnection attempts reached for {platform_name}. Giving up.")
            send_telegram_message(
                f"⚠️ Бот не может переподключиться к Binance {platform_name} после {MAX_RECONNECT_ATTEMPTS} попыток.")
            return
    except Exception as e:
        logger.error(f"Unexpected error in {platform_name} WebSocket: {e}")
        if reconnect_attempt < MAX_RECONNECT_ATTEMPTS:
            logger.warning(
                f"Reconnecting to {platform_name} in {RECONNECT_DELAY}s (attempt {reconnect_attempt + 1}/{MAX_RECONNECT_ATTEMPTS})")
            await asyncio.sleep(RECONNECT_DELAY)
            return await listen_binance(is_futures, reconnect_attempt + 1)
        else:
            logger.error(f"Max reconnection attempts reached for {platform_name}. Giving up.")
            send_telegram_message(
                f"⚠️ Бот не может переподключиться к Binance {platform_name} после {MAX_RECONNECT_ATTEMPTS} попыток.")
            return


def process_ticker_message(message, is_futures):
    """Process ticker message from Binance WebSocket"""
    try:
        data = json.loads(message)
        platform = "Futures" if is_futures else "Spot"
        platform_key = "futures" if is_futures else "spot"

        # Skip non-list messages
        if not isinstance(data, list):
            if 'result' in data or 'id' in data:
                logger.debug(f"Service message from {platform}: {data}")
            else:
                logger.info(f"Unexpected message format from {platform}: {data}")
            return

        # Skip empty lists
        if len(data) == 0:
            return

        # Process each ticker in the list
        for ticker in data:
            if 's' not in ticker:
                continue

            symbol = ticker['s']

            # Skip non-USDT pairs for simplicity
            if not symbol.endswith('USDT'):
                continue

            # Get current data
            price = float(ticker.get('c', 0))  # Current price
            price_change_percent = float(ticker.get('P', 0))  # 24h price change percent
            volume_24h = float(ticker.get('q', 0))  # 24h trading volume in quote asset (USDT)

            # Initialize symbol history if not exists
            symbol_key = f"{platform_key}_{symbol}"
            if symbol_key not in volume_history:
                volume_history[symbol_key] = []

            # Add current volume to history
            volume_history[symbol_key].append(volume_24h)

            # Keep only the last N volume readings
            if len(volume_history[symbol_key]) > VOLUME_HISTORY_SIZE:
                volume_history[symbol_key].pop(0)

            # Skip if we don't have enough history
            if len(volume_history[symbol_key]) < 2:
                continue

            # Calculate volume change
            previous_volume = volume_history[symbol_key][-2]
            current_volume = volume_history[symbol_key][-1]
            volume_change = current_volume - previous_volume

            # Check if volume increased significantly
            if volume_change >= MIN_USDT_VOLUME_CHANGE:
                logger.info(f"Significant volume increase for {symbol} on {platform}: +{volume_change:.2f} USDT")

                # Check if price also increased (potential buy pressure)
                if price_change_percent >= MIN_PRICE_CHANGE_PERCENT:
                    logger.info(f"Price also increased for {symbol}: {price_change_percent}%")

                    # Send alert
                    message_text = (
                        f"🎰 #{symbol} покупают 🔫\n"
                        f"Увеличение объема: +{volume_change / 1_000:.2f}K USDT\n"
                        f"P: {price:.6f} ⬆️ (+{price_change_percent:.2f}%)\n"
                        f"Объем за 24ч: {volume_24h / 1_000_000:.2f}M USDT\n"
                        f"<i>{platform}</i>"
                    )
                    send_telegram_message(message_text)

                    # Update attack detection
                    now = datetime.utcnow()
                    if symbol not in recent_trades:
                        recent_trades[symbol] = []
                    recent_trades[symbol].append(now)

                    # Keep only recent events
                    recent_trades[symbol] = [
                        t for t in recent_trades[symbol]
                        if now - t <= timedelta(minutes=ATTACK_WINDOW_MINUTES)
                    ]

                    # Check for attack pattern
                    if len(recent_trades[symbol]) >= ATTACK_THRESHOLD:
                        attack_message = (
                            f"🚨 <b>АТАКА на монету #{symbol}!</b>\n"
                            f"{len(recent_trades[symbol])} волн покупок за {ATTACK_WINDOW_MINUTES} минут!\n"
                            f"<i>{platform}</i>"
                        )
                        send_telegram_message(attack_message)
                        logger.info(f"Attack alert sent for {symbol}")

                        # Clear list to avoid spam
                        recent_trades[symbol] = []

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e} - Message: {message[:100]}...")
    except Exception as e:
        logger.error(f"Error processing ticker message: {e}")


async def keep_alive():
    """Send periodic messages to confirm bot is running"""
    while True:
        try:
            # Send stats every hour
            await asyncio.sleep(3600)  # 1 hour

            # Count active pairs
            futures_count = sum(1 for k in volume_history if k.startswith("futures_"))
            spot_count = sum(1 for k in volume_history if k.startswith("spot_"))

            stats_message = (
                f"📊 Статистика работы бота:\n"
                f"Получено сообщений Futures: {message_counter['futures']}\n"
                f"Получено сообщений Spot: {message_counter['spot']}\n"
                f"Отслеживаемые пары Futures: {futures_count}\n"
                f"Отслеживаемые пары Spot: {spot_count}\n"
                f"Порог увеличения объема: {MIN_USDT_VOLUME_CHANGE / 1000:.0f}K USDT\n"
                f"Порог изменения цены: {MIN_PRICE_CHANGE_PERCENT}%"
            )
            send_telegram_message(stats_message)
            logger.info("Stats message sent")
        except Exception as e:
            logger.error(f"Error in keep_alive: {e}")


async def main():
    """Main function to run the bot"""
    try:
        # Check if environment variables are set
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.critical("Environment variables TELEGRAM_TOKEN or TELEGRAM_CHANNEL are not set")
            print("Error: Please set TELEGRAM_TOKEN and TELEGRAM_CHANNEL environment variables")
            return

        # Notify about bot startup
        startup_message = (
            f"✅ Бот запущен и работает!\n"
            f"Режим: Отслеживание тикеров (ticker stream)\n"
            f"Порог увеличения объема: {MIN_USDT_VOLUME_CHANGE / 1000:.0f}K USDT\n"
            f"Порог изменения цены: {MIN_PRICE_CHANGE_PERCENT}%"
        )
        logger.info("Bot starting...")
        if send_telegram_message(startup_message):
            logger.info("Startup notification sent")
        else:
            logger.warning("Failed to send startup notification")

        # Start all tasks
        await asyncio.gather(
            listen_binance(is_futures=True),
            listen_binance(is_futures=False),
            keep_alive()
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error in main: {e}")
        send_telegram_message(f"❌ Критическая ошибка, бот остановлен: {str(e)}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        print(f"Fatal error: {e}")