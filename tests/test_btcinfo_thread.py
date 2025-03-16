import unittest
from unittest.mock import patch, MagicMock
import time

from threads.btcinfo_thread import BtcInfoThread, BTC_PRICE_API_SOURCES
from threads.managed_thread import ThreadState


class TestBtcInfoThread(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Runs once before all test cases."""
        BtcInfoThread.reset_instance()

    def setUp(self):
        """Runs before each test case."""
        self.btc_thread = BtcInfoThread(update_seconds=1)  # Initialize thread
        self.btc_thread.cache = {
            "btc_price_source": "TestSource",
            "btc_price": 45000.00,
            "block_reward": 6.25,
            "block_reward_value": 281250.00
        }

    def tearDown(self):
        """Runs after each test case to stop the thread safely."""
        self.btc_thread.stop()
        BtcInfoThread.reset_instance()

    @staticmethod
    def mock_btc_price_api_response(price):
        mock_response = MagicMock()
        mock_response.json.return_value = {"last": str(price)}
        mock_response.raise_for_status = MagicMock()
        return mock_response


    def test_singleton_instance(self):
        """Ensure only one instance of BtcInfoThread exists."""
        btc_thread_2 = BtcInfoThread(update_seconds=1)
        self.assertIs(self.btc_thread, btc_thread_2)

    def test_running_state(self):
        """Test that the thread transitions to RUNNING after starting."""
        time.sleep(1)  # Give time for the thread to update state
        self.assertEqual(self.btc_thread.get_state(), ThreadState.RUNNING)

    @patch("requests.get")
    def test_get_btc_block_reward_value(self, mock_get):
        """Test fetching Bitcoin block reward value with a mocked API response."""

        # Mock blockchain.info block height response
        mock_response = MagicMock()
        mock_response.text = "840000"  # Simulating 4 halvings (210000 * 4)
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.object(BtcInfoThread, "get_btc_price", return_value=("MockSource", 50000.00)):
            self.btc_thread.get_btc_block_reward_value()

        self.assertEqual(self.btc_thread.block_reward, 3.125)  # 50 / (2^4)
        self.assertEqual(self.btc_thread.block_reward_value, 156250.00)
        self.assertEqual(self.btc_thread.btc_price_source, "MockSource")
        self.assertEqual(self.btc_thread.btc_price, 50000.00)

    @patch("requests.get")
    def test_get_btc_price(self, mock_get):
        """Test Bitcoin price fetching from multiple sources with mock API responses."""
        test_source = BTC_PRICE_API_SOURCES[0]  # Use the first source

        # Mock response from the first BTC price API
        mock_get.return_value = self.mock_btc_price_api_response(48000.00)

        source_name, price = BtcInfoThread.get_btc_price()
        self.assertEqual(source_name, test_source["name"])
        self.assertEqual(price, 48000.00)

    @patch("requests.get", side_effect=Exception("API failure"))
    def test_get_btc_price_all_fail(self, mock_get):
        """Test Bitcoin price fetching when all APIs fail."""
        source_name, price = BtcInfoThread.get_btc_price()
        self.assertEqual(source_name, "")
        self.assertEqual(price, 0.0)

    @patch("requests.get", side_effect=Exception("Network Error"))
    def test_restore_from_cache_on_failure(self, mock_get):
        """Ensure cached data is used when API requests fail."""
        self.btc_thread.get_btc_block_reward_value()  # Simulate API failure
        self.assertEqual(self.btc_thread.btc_price_source, "TestSource")
        self.assertEqual(self.btc_thread.btc_price, 45000.00)
        self.assertEqual(self.btc_thread.block_reward, 6.25)
        self.assertEqual(self.btc_thread.block_reward_value, 281250.00)

    def test_thread_start_and_stop(self):
        """Ensure the thread can start and stop cleanly."""
        self.assertEqual(self.btc_thread.get_state(), ThreadState.RUNNING)
        time.sleep(2)  # Let the thread run briefly
        self.assertEqual(self.btc_thread.get_state(), ThreadState.RUNNING)

        self.btc_thread.pause()
        self.assertEqual(self.btc_thread.get_state(), ThreadState.PAUSED)

        self.btc_thread.stop()
        time.sleep(0.5)
        self.assertEqual(self.btc_thread.get_state(), ThreadState.STOPPED)

    def test_singleton_behavior(self):
        """Test that only one instance of BtcInfoThread exists."""
        another_instance = BtcInfoThread()
        self.assertIs(self.btc_thread, another_instance)

    def test_running_state_restart(self):
        """Ensure the thread transitions to RUNNING after start."""
        self.btc_thread.stop()
        time.sleep(0.5)
        self.assertEqual(self.btc_thread.get_state(), ThreadState.STOPPED)
        self.btc_thread.restart()
        time.sleep(0.5)
        self.assertEqual(self.btc_thread.get_state(), ThreadState.RUNNING)

    def test_stopping_and_stopped_state(self):
        """Ensure the thread transitions to STOPPING and then STOPPED."""
        time.sleep(0.5)
        self.btc_thread.stop()
        time.sleep(0.5)
        self.assertEqual(self.btc_thread.get_state(), ThreadState.STOPPED)

    @patch("requests.get")
    def test_block_reward_calculation(self, mock_get):
        """Test correct block reward calculation based on block height."""
        mock_get.return_value.text = "840000"  # Simulate block height
        mock_get.return_value.raise_for_status = MagicMock()

        self.btc_thread.get_btc_block_reward_value()
        self.assertEqual(self.btc_thread.block_reward, 3.125, "Block reward should be correct after halvings")

    @patch("requests.get")
    def test_block_reward_future_halvings(self, mock_get):
        """Test block reward calculation for an extreme future block height."""
        # Simulating block height far in the future, specifically Halving #10
        # https://dantesisofo.com/bitcoin-block-rewards-for-each-halving/
        future_block_height = 2100000

        # Mock the API response
        mock_response = MagicMock()
        mock_response.text = str(future_block_height)  # Simulated API block height
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        self.btc_thread.get_btc_block_reward_value()

        # Calculate expected reward: 50 / (2^(2,100,000 / 210,000))
        expected_halvings = future_block_height // 210000
        expected_reward = 50 / (2 ** expected_halvings)

        # The reward should never be negative, and should approach zero but not be exactly zero
        self.assertGreaterEqual(expected_reward, 0, "Block reward should never be negative")
        self.assertLess(expected_reward, 0.04882813, "Block reward should be near zero after many halvings")

        self.assertAlmostEqual(self.btc_thread.block_reward, expected_reward, places=8,
                               msg="Block reward calculation should be correct for extreme halvings")

    @patch("requests.get")
    def test_api_backoff_mechanism(self, mock_get):
        """Test that failing APIs are temporarily skipped."""
        mock_get.side_effect = Exception("API failed")

        _, price = self.btc_thread.get_btc_price()
        self.assertEqual(price, 0.0, "Price should be 0.0 if all APIs fail")
        self.assertEqual(len(BtcInfoThread._backoff_tracker), len(BTC_PRICE_API_SOURCES), "Backoff tracker should contain failed APIs")

    @patch("requests.get")
    def test_cache_restoration_on_failure(self, mock_get):
        """Ensure cached values are used when API fetch fails."""
        # Set up cached values
        self.btc_thread.cache = {
            "btc_price_source": "Backup",
            "btc_price": 45000.0,
            "block_reward": 6.25,
            "block_reward_value": 281250.0
        }

        mock_get.side_effect = Exception("API failure")  # Simulate failure

        self.btc_thread.get_btc_block_reward_value()
        self.assertEqual(self.btc_thread.btc_price_source, "Backup")
        self.assertEqual(self.btc_thread.btc_price, 45000.0)
        self.assertEqual(self.btc_thread.block_reward, 6.25, "Should restore BTC price from cache")
        self.assertEqual(self.btc_thread.block_reward_value, 281250.0, "Should restore block reward from cache")

if __name__ == "__main__":
    unittest.main()
