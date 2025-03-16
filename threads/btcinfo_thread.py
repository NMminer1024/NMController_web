import threading
import time
import requests
import logging
from threads.managed_thread import ManagedThread, ThreadState

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

LATEST_BLOCK_HEIGHT_URL = "https://blockchain.info/q/getblockcount"

#
# List of free BTC data sources evaluated and ranked by reputation and reliability
#
BTC_PRICE_API_SOURCES = [
    # Bitstamp: Long-standing reputation as a trusted exchange and API provider.
    # Known for its reliability and accuracy.
    {
        "name": "Bitstamp",
        "url": "https://www.bitstamp.net/api/v2/ticker/btcusd/",
        "parser": lambda price_data: round(float(price_data["last"]), 2)
    },
    # Kraken: Highly reputable exchange with a reliable API, known for security
    # and comprehensive market data.
    {
        "name": "Kraken",
        "url": "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
        "parser": lambda price_data: round(float(price_data["result"]["XXBTZUSD"]["c"][0]), 2)
    },
    # Coingecko: Excellent reputation as a free, reliable, and fast source for
    # cryptocurrency prices. Widely used and trusted.
    {
        "name": "Coingecko",
        "url": "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
        "parser": lambda price_data: round(price_data["bitcoin"]["usd"], 2)
    },
    # OKX: A well-known global exchange with strong liquidity and a robust API,
    # though slightly less established than Kraken or Bitstamp.
    {
        "name": "OKX",
        "url": "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
        "parser": lambda price_data: round(float(price_data["data"][0]["last"]), 2)
    },
    # Huobi: A large exchange with a good reputation, but more complex data structures.
    # Slightly less reliable than the top-ranked options.
    {
        "name": "Huobi",
        "url": "https://api.huobi.pro/market/detail/merged?symbol=btcusdt",
        "parser": lambda price_data: round(float(price_data["tick"]["close"]), 2)
    },
    # ByBit: Known mainly for derivatives trading, but slightly less reputable for spot
    # trading data compared to Kraken or Bitstamp.
    {
        "name": "ByBit",
        "url": "https://api.bybit.com/v2/public/tickers?symbol=BTCUSD",
        "parser": lambda price_data: round(float(price_data["result"][0]["last_price"]), 2)
    },
    # MEXC: A newer exchange with a growing user base, but less established than the others.
    # Still reliable but lower on the reputation scale.
    {
        "name": "MEXC",
        "url": "https://api.mexc.com/api/v3/ticker/price?symbol=BTCUSDT",
        "parser": lambda price_data: round(float(price_data["price"]), 2)
    },
    # Binance: One of the largest and most popular cryptocurrency exchanges globally, offering
    # a reliable API for market data.
    {
        "name": "Binance",
        "url": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "parser": lambda price_data: round(float(price_data["price"]), 2)
    },
    # CryptoCompare: Provides cryptocurrency market data, including prices for Bitcoin. Known
    # for its accuracy and reliability.
    {
        "name": "CryptoCompare",
        "url": "https://min-api.cryptocompare.com/data/price?fsym=BTC&tsyms=USD",
        "parser": lambda price_data: round(price_data["USD"], 2)
    },
    # Gemini: A trusted exchange API providing accurate and real-time cryptocurrency prices,
    # including Bitcoin.
    {
        "name": "Gemini",
        "url": "https://api.gemini.com/v1/pubticker/btcusd",
        "parser": lambda price_data: round(float(price_data["last"]), 2)
    },
    # Blockchain.com: Offers Bitcoin price data as well as blockchain-related data.
    # Reliable and accurate.
    {
        "name": "Blockchain.com",
        "url": "https://blockchain.info/ticker",
        "parser": lambda price_data: round(price_data["USD"]["last"], 2)
    },
    # CoinPaprika: Offers cryptocurrency market data, including Bitcoin prices.
    # Solid alternative for price tracking.
    {
        "name": "CoinPaprika",
        "url": "https://api.coinpaprika.com/v1/tickers/btc-bitcoin",
        "parser": lambda price_data: round(price_data["quotes"]["USD"]["price"], 2)
    },
]

# Backoff Mechanism to avoid hammering unsuccessful APIs
MAX_BACKOFF = 600  # 10 minutes
backoff_time_calc = lambda name : min(
                    time.time() + (BtcInfoThread._backoff_tracker.get(name, 1) * 2),
                    time.time() + MAX_BACKOFF
                )


class BtcInfoThread(ManagedThread):
    """
    A thread that periodically fetches Bitcoin price and block reward information.
    """

    _instance = None
    _lock = threading.Lock()  # Lock to ensure thread safety in instance creation
    _initialized = False

    _last_successful_api = None
    _backoff_tracker = {}

    @classmethod
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BtcInfoThread, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    @classmethod
    def reset_instance(cls):
        """Resets the singleton instance (for testing purposes)."""
        with cls._lock:
            if cls._instance:
                cls._instance.stop()  # Ensure the thread is stopped
                cls._instance = None  # Reset instance


    def __init__(self, name="BTC_Info", update_seconds=1800):
        """
        Initialize the Bitcoin info thread.

        :param name: Thread name.
        :param update_seconds: Interval for fetching data (default: 30 minutes).
        """
        if self._initialized:
            return  # Prevent re-initialization if already initialized

        super().__init__(name=name, update_seconds=update_seconds)

        self.lock = threading.Lock()  # Lock for thread-safe updates

        self._set_state(ThreadState.INITIALIZING)

        self.btc_price_source = ''
        self.btc_price = 0.0
        self.block_reward = 0.0
        self.block_reward_value = 0.00
        self.cache = {
            "btc_price_source": "",
            "btc_price": 0.0,
            "block_reward": 0.0,
            "block_reward_value": 0.0
        }
        self._initialized = True
        self._set_state(ThreadState.RUNNING)


    def run(self):
        """Runs the Bitcoin info update loop."""
        while not self.should_stop():
            if self.needs_update():
                self.get_btc_block_reward_value()
            else:
                # Sleep briefly to avoid high CPU usage
                self.sleep_for(1)

    def get_btc_block_reward_value(self):
        """Fetches the Bitcoin price and calculates the block reward value in USD."""
        try:
            # Get Bitcoin price
            self.btc_price_source, self.btc_price = self.get_btc_price()

            # Get the latest Bitcoin block height
            block_height_response = requests.get(LATEST_BLOCK_HEIGHT_URL, timeout=10)
            block_height_response.raise_for_status()
            latest_block_height = int(block_height_response.text)

            # Calculate current block reward based on halvings
            halvings = latest_block_height // 210000
            initial_reward = 50
            self.block_reward = initial_reward / (2 ** halvings)

            # Calculate block reward value in USD
            self.block_reward_value = round(self.block_reward * self.btc_price, 2)

            # Cache the successful results
            self.cache["btc_price_source"] = self.btc_price_source
            self.cache["btc_price"] = self.btc_price
            self.cache["block_reward"] = self.block_reward
            self.cache["block_reward_value"] = self.block_reward_value

        except requests.RequestException as e:
            logging.error(f"[BtcInfoThread] Error fetching data from blockchain.info: {e}", exc_info=True)
            self.restore_from_cache()
        except ValueError as e:
            logging.error(f"[BtcInfoThread] Unexpected data format from blockchain.info: {e}", exc_info=True)
            self.restore_from_cache()
        except Exception as e:
            # Generic exception catch for anything that isn't already caught
            logging.error(f"[BtcInfoThread] Unexpected error from blockchain.info: {e}", exc_info=True)
            self.restore_from_cache()

        logging.info(f"[BtcInfoThread] BTC Price: ${self.btc_price}, Block Reward: {self.block_reward} BTC, Reward Value: ${self.block_reward_value}")

    def restore_from_cache(self):
        """Restores the cached values if the fetch fails."""
        logging.warning("[BtcInfoThread] Using cached data due to fetch failure.")
        self.btc_price_source = self.cache["btc_price_source"]
        self.btc_price = self.cache["btc_price"]
        self.block_reward = self.cache["block_reward"]
        self.block_reward_value = self.cache["block_reward_value"]

    # @staticmethod
    # def get_btc_price():
    #     """Fetch BTC price in USD from multiple free crypto APIs."""
    #
    #     for source in BTC_PRICE_API_SOURCES:  # Try one of the free crypto APIs to get the Bitcoin price
    #         try:
    #             response = requests.get(source["url"], timeout=10)
    #             response.raise_for_status()
    #             data = response.json()
    #             return source['name'], source["parser"](data)
    #         except (requests.RequestException, KeyError, IndexError, ValueError) as e:
    #             logging.warning(f"[BtcInfoThread] {source['name']} API failed: {e}")
    #         except Exception as e:
    #             # Catch anything else that falls through
    #             logging.error(f"[BtcInfoThread] {source['name']} API failed: {e}")
    #
    #     # Return 0.0 if all APIs fail
    #     return '', 0.0

    @staticmethod
    def get_btc_price():
        sources = sorted(BTC_PRICE_API_SOURCES, key=lambda s: s["name"] != BtcInfoThread._last_successful_api)
        for source in sources:
            # if this api source has a history of failure, back off for a bit
            if source["name"] in BtcInfoThread._backoff_tracker:
                backoff_time = BtcInfoThread._backoff_tracker[source["name"]]
                if time.time() < backoff_time:
                    continue
            try:
                response = requests.get(source["url"], timeout=10)
                response.raise_for_status()
                data = response.json()
                logging.debug(f"[BtcInfoThread] Fetched data from {source['name']} source. {data}")

                # remove this successful api request from the backoff list
                BtcInfoThread._last_successful_api = source["name"]
                if source["name"] in BtcInfoThread._backoff_tracker:
                    del BtcInfoThread._backoff_tracker[source["name"]]

                logging.debug(f"[BtcInfoThread] Fetched data from {source['name']}: {data}")
                return source["name"], source["parser"](data)

            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                logging.warning(f"[BtcInfoThread] {source['name']} API failed: {e}")
                # BtcInfoThread._backoff_tracker[source["name"]] = time.time() + (BtcInfoThread._backoff_tracker.get(source["name"], 1) * 2)
                BtcInfoThread._backoff_tracker[source["name"]] = backoff_time_calc(source["name"])
            except Exception as e:
                logging.error(f"[BtcInfoThread] {source['name']} API failed: {e}")
                # BtcInfoThread._backoff_tracker[source["name"]] = time.time() + (BtcInfoThread._backoff_tracker.get(source["name"], 1) * 2)
                BtcInfoThread._backoff_tracker[source["name"]] = backoff_time_calc(source["name"])

        return '', 0.0

    def sleep_for(self, seconds):
        """Utility method to sleep without blocking thread stopping."""
        for _ in range(seconds):
            if self.should_stop():
                break
            time.sleep(1)


if __name__ == "__main__":
    btc_thread = BtcInfoThread(update_seconds=1)  # Start listening
    time.sleep(10)  # Let it run for a while
    btc_thread.stop()
    btc_thread.join()  # Ensure it exits cleanly
