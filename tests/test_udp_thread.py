import json
import logging
import random
import socket
import string
import time
from unittest import TestCase
from unittest.mock import patch

from threads.managed_thread import OperationFailedError, ThreadError, ThreadState, ManagedThread
from threads.udp_thread import UdpThread

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s", force=True)


def log_function(func):
   """
   Decorator that logs the start and end of a function call, along with the function name,
   and includes the runtime of the function.
   """

   def wrapper(*args, **kwargs):
      # log that we are starting function
      current_function_name = func.__name__
      logging.info(f"Running {current_function_name}")
      start_time = time.time()

      # call wrapped function
      result = func(*args, **kwargs)

      # log that we finished the function and the execution time
      elapsed_time = time.time() - start_time
      logging.info(f"Done {current_function_name} in {elapsed_time:.4f} seconds")
      return result

   return wrapper


class TestUdpThread(TestCase):
   # Set managed thread class to DEBUG level
   managed_thread_logger = logging.getLogger("threads.managed_thread")
   managed_thread_logger.setLevel(logging.DEBUG)

   def setUp(self):
      # ensure each test has a fresh UdpThread instance
      UdpThread.reset_instance()
      time.sleep(1.0)  # Wait for initialization

   def tearDown(self):
      patch.stopall()  # ensure mocks reset between tests

   @staticmethod
   def random_port():
      """Generate a random port number."""
      return random.randint(1024, 65535)

   @staticmethod
   def random_string(length=10):
      """Generates a random string of a given length."""
      return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

   def random_json_data(self, drop_ip=True):
      """Generates random malformed JSON data."""
      keys = [
         "ip",
         "BoardType",
         "HashRate",
         "Share",
         "NetDiff",
         "PoolDiff",
         "LastDiff",
         "BestDiff",
         "Valid",
         "Progress",
         "Temp",
         "RSSI",
         "FreeHeap",
         "Uptime",
         "Version",
      ]
      data = {key: self.random_string(random.randint(5, 15)) for key in keys}
      # Randomly drop or alter 'ip' key to simulate errors
      if drop_ip and random.random() > 0.5:
         del data["ip"]
      return data

   # Combined helper function to mock socket and select
   def apply_patches_and_mock_socket(self):
      patchers = [
         patch('select.select'),
         patch('socket.socket'),
      ]
      mocks = [patcher.start() for patcher in patchers]
      self.addCleanup(lambda: [patcher.stop() for patcher in patchers])  # Ensure patches are stopped after test

      mock_select, mock_socket = mocks
      mock_sock = mock_socket.return_value
      mock_sock.fileno.return_value = 1
      mock_select.return_value = ([mock_sock], [], [])
      return mock_sock

   @log_function
   def test_invalid_json(self):
      """Test that UdpThread handles invalid/malformed JSON gracefully."""

      mock_sock = self.apply_patches_and_mock_socket()

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Send random invalid data to test error handling in processing
      malformed_data = b''
      for _ in range(50):
         malformed_data = self.random_string(20).encode()  # Random bytes that aren't valid JSON
         mock_sock.recvfrom.return_value = (malformed_data, ('localhost', 12345))
         time.sleep(0.2)  # Wait for a cycle

      # Assert that the log contains the expected error for malformed JSON
      with self.assertLogs(level='ERROR') as cm:
         udp_thread.process_data(malformed_data)
      self.assertIn("UdpThread Failed to decode JSON", cm.output[-1])

      udp_thread.stop()

      # Assert that recvfrom() was called
      self.assertGreater(mock_sock.recvfrom.call_count, 0, "recvfrom() should have been called")

   @log_function
   def test_missing_ip_in_json(self):
      """Test that UdpThread gracefully handles missing 'ip' field in JSON."""

      mock_sock = self.apply_patches_and_mock_socket()
      mock_sock.recvfrom.return_value = (json.dumps(self.random_json_data()).encode(), ('localhost', 12345))

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Send random data with missing 'ip' field
      invalid_json = self.random_json_data()
      invalid_json.pop("ip", None)  # Remove 'ip' to simulate the error
      mock_sock.recvfrom.return_value = (json.dumps(invalid_json).encode(), ('localhost', 12345))
      time.sleep(0.2)  # Wait for a cycle

      # Check logs for handling the missing 'ip' field
      with self.assertLogs(level='WARNING') as cm:
         udp_thread.process_data(json.dumps(invalid_json).encode())
      self.assertIn("Received JSON without 'ip' field", cm.output[-1])

      udp_thread.stop()

      # Assert that recvfrom() was called
      self.assertGreater(mock_sock.recvfrom.call_count, 0, "recvfrom() should have been called")

   @log_function
   def test_socket_timeout_handling(self):
      """Test UdpThread's behavior when socket times out."""

      mock_sock = self.apply_patches_and_mock_socket()
      mock_sock.recvfrom.side_effect = socket.timeout

      with self.assertLogs(level='ERROR') as cm:
         udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)
         time.sleep(1)

      udp_thread.stop()

      # Check if timeout was logged
      log_messages = "\n".join(cm.output)
      self.assertIn("timeouterror", log_messages.lower(), "Expected timeout message not found in logs")

   @log_function
   def test_singleton_behavior(self):
      """Test that the UdpThread class adheres to the Singleton pattern."""

      udp_thread_1 = UdpThread(ip="127.0.0.1", port=12345)
      udp_thread_2 = UdpThread(ip="127.0.0.1", port=12345)

      # Ensure both instances are the same
      self.assertIs(udp_thread_1, udp_thread_2)

      udp_thread_1.stop()
      udp_thread_2.stop()

   @log_function
   def test_thread_shutdown(self):
      """Test that UdpThread can be properly shut down."""

      udp_thread = UdpThread(ip="127.0.0.1", port=12345)

      time.sleep(5)  # Give the thread time to run
      udp_thread.stop()

      self.assertIsNone(udp_thread.sock)
      self.assertEqual(udp_thread.get_state(), ThreadState.STOPPED)

   @log_function
   @patch('socket.socket')
   def test_thread_state_transition(self, mock_socket):
      """Test that UdpThread handles state transitions properly."""

      mock_socket.return_value.fileno.return_value = 1

      udp_thread = UdpThread(ip="127.0.0.1", port=12345)
      time.sleep(1)

      # Assert the thread is running after initialization
      self.assertEqual(udp_thread.get_state(), ThreadState.RUNNING)

      # Pause the thread and check state
      udp_thread.pause()
      self.assertEqual(udp_thread.get_state(), ThreadState.PAUSED)

      # Resume the thread and check state
      udp_thread.resume()
      self.assertEqual(udp_thread.get_state(), ThreadState.RUNNING)

      # Restart the thread and check state
      udp_thread.restart()
      self.assertEqual(udp_thread.get_state(), ThreadState.RUNNING)

      udp_thread.stop()

   @log_function
   @patch('socket.socket')
   def test_retry_operation_on_failure(self, mock_socket):
      """Test that UdpThread retries failed operations."""

      def failing_operation():
         raise OperationFailedError("Simulated operation failure")

      mock_sock = mock_socket.return_value
      mock_sock.recvfrom.return_value = ("Some plain text".encode(), ('localhost', 12345))
      mock_sock.fileno.return_value = 1

      udp_thread = UdpThread(ip="127.0.0.1", port=12345)

      # Test the retry operation with a simulated failure
      with self.assertRaises(ThreadError):
         udp_thread.retry_operation(failing_operation, retries=3, timeout=0.1)

      udp_thread.stop()

   @log_function
   def test_high_data_load(self):
      """Test UdpThread's ability to handle a high load of data packets."""

      mock_sock = self.apply_patches_and_mock_socket()
      mock_sock.recvfrom.return_value = (json.dumps(self.random_json_data()).encode(), ('localhost', 12345))

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Simulate receiving a large number of data packets
      for _ in range(1000):
         mock_sock.recvfrom.return_value = (json.dumps(self.random_json_data()).encode(), ('localhost', 12345))
         time.sleep(0.01)  # Fast cycling

      udp_thread.stop()

   @log_function
   def test_socket_initialization(self):
      """Test that socket initialization works correctly."""

      self.apply_patches_and_mock_socket()

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Assert that socket has been initialized correctly
      self.assertIsNotNone(udp_thread.sock)
      self.assertEqual(udp_thread.sock.fileno(), 1)

      udp_thread.stop()

   @log_function
   def test_socket_error_handling(self):
      """Test UdpThread's handling of socket errors."""

      mock_sock = self.apply_patches_and_mock_socket()
      mock_sock.recvfrom.side_effect = socket.error("Simulated socket error")

      with self.assertLogs(level='ERROR') as cm:
         udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)
         time.sleep(1)

      udp_thread.stop()

      # Check that the error message is logged
      self.assertIn("Simulated socket error", cm.output[-1])

   @log_function
   def test_performance_under_network_latency(self):
      """Test UdpThread's performance under network latency."""

      mock_sock = self.apply_patches_and_mock_socket()
      mock_sock.recvfrom.return_value = (json.dumps(self.random_json_data()).encode(), ('localhost', 12345))

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Simulate latency by adding sleep between receiving data
      for _ in range(100):
         mock_sock.recvfrom.return_value = (json.dumps(self.random_json_data()).encode(), ('localhost', 12345))
         time.sleep(0.05)  # Simulate network latency

      udp_thread.stop()

   @log_function
   def test_ip_resolution_error(self):
      """Test UdpThread's behavior when an IP resolution error occurs."""

      # Simulate DNS resolution error (host not found)
      with self.assertRaises(socket.gaierror):
         UdpThread(ip="nonexistent.host", port=self.random_port(), update_seconds=0.1)

   @log_function
   def test_empty_message_handling(self):
      """Test that empty messages are handled gracefully."""

      self.apply_patches_and_mock_socket()

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Send empty message and check logs
      with self.assertLogs(level='WARNING') as cm:
         udp_thread.process_data(b'')
      self.assertIn("Failed to decode JSON", cm.output[-1])

      udp_thread.stop()

   @log_function
   def test_unexpected_data_type(self):
      """Test that unexpected data types are handled properly."""

      self.apply_patches_and_mock_socket()

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Send unexpected data type (not JSON)
      with self.assertLogs(level='ERROR') as cm:
         udp_thread.process_data(b'Not a JSON message')
      self.assertIn("UdpThread Failed to decode JSON", cm.output[-1])

      udp_thread.stop()

   @log_function
   @patch('socket.socket')
   def test_rapid_state_changes(self, mock_socket):
      """Test UdpThread's ability to handle rapid state changes."""

      mock_sock = mock_socket.return_value
      mock_sock.fileno.return_value = 1

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      for _ in range(100):
         udp_thread.pause()
         udp_thread.resume()

      udp_thread.stop()

   @log_function
   def test_run_method_called(self):
      class TestThread(ManagedThread):
         def __init__(self, *args, **kwargs):
            self.run_called = False
            super().__init__(*args, **kwargs)

         def run(self):
            logging.debug("run() called")
            self.run_called = True  # Set flag when run() is called
            while not self.should_stop():
               time.sleep(0.1)  # Prevent busy-waiting

      # Create and start the thread
      thread = TestThread(name="TestUdpThread", update_seconds=0.1)

      # Allow time for the thread to start and call run()
      time.sleep(3)

      # Check if run() was called
      self.assertTrue(thread.run_called, "run() method was not called.")

      # Stop the thread to clean up
      thread.stop()
