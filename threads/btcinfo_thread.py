import time

import requests
import logging
from threads.managed_thread import ManagedThread

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BTC_PRICE_URL = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd'
LATEST_BLOCK_HEIGHT_URL = "https://blockchain.info/q/getblockcount"


class BtcInfoThread(ManagedThread):
    """
    A thread that periodically fetches Bitcoin price and block reward information.
    """

    def __init__(self, name="BTC_Info", update_seconds=1800):
        """
        Initialize the Bitcoin info thread.

        :param name: Thread name.
        :param update_seconds: Interval for fetching data (default: 30 minutes).
        """
        super().__init__(name=name, update_seconds=update_seconds)
        self.btc_price = 0.0
        self.block_reward = 0.0
        self.block_reward_value = 0.00

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
            # Fetch BTC price in USD
            btc_price_response = requests.get(BTC_PRICE_URL, timeout=10)
            btc_price_response.raise_for_status()
            btc_price_data = btc_price_response.json()

            if "bitcoin" in btc_price_data and "usd" in btc_price_data["bitcoin"]:
                self.btc_price = round(btc_price_data["bitcoin"]["usd"], 2)
            else:
                logging.warning("[BtcInfoThread] Unexpected BTC price response format.")
                return

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

            logging.info(f"[BtcInfoThread] BTC Price: ${self.btc_price}, Block Reward: {self.block_reward} BTC, Reward Value: ${self.block_reward_value}")

        except requests.RequestException as e:
            logging.error(f"[BtcInfoThread] Error fetching data: {e}", exc_info=True)
        except ValueError as e:
            logging.error(f"[BtcInfoThread] Unexpected data format: {e}", exc_info=True)

    def sleep_for(self, seconds):
        """Utility method to sleep without blocking thread stopping."""
        for _ in range(seconds):
            if self.should_stop():
                break
            time.sleep(1)


if __name__ == "__main__":
    btc_thread = BtcInfoThread(update_seconds=1)  # Start listening
    time.sleep(10)  # Let it run for a while
    btc_thread.stop()  # Stop the listener
