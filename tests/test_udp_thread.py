import json
import logging
import random
import socket
import string
import threading
import time
from unittest import TestCase
from unittest.mock import patch

from threads.udp_thread import UdpThread

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class TestUdpThreadFuzzer(TestCase):

   @staticmethod
   def random_port():
      """Generate a random port number."""
      return random.randint(1024, 65535)

   @staticmethod
   def random_string(length=10):
      """Generates a random string of a given length."""
      return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

   def random_json_data(self):
      """Generates random malformed JSON data."""
      keys = [
         "IP",
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
      if random.random() > 0.5:
         data["IP"] = None
      return data

   @patch('socket.socket')
   def test_invalid_json(self, mock_socket):
      """Test that UdpThread handles invalid/malformed JSON gracefully."""
      logging.info(f"Running test_invalid_json")

      # Create the fuzzer for random UDP packets
      mock_sock = mock_socket.return_value
      mock_sock.recvfrom.return_value = (self.random_string(50).encode(), ('localhost', 12345))
      mock_sock.fileno.return_value = 1

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Send random invalid data to test error handling in processing
      for _ in range(50):
         malformed_data = self.random_string(20).encode()  # Random bytes that aren't valid JSON
         mock_sock.recvfrom.return_value = (malformed_data, ('localhost', 12345))
         time.sleep(0.2)  # Wait for a cycle

      # Assert that the log contains the expected error for malformed JSON
      with self.assertLogs(level='ERROR') as cm:
         udp_thread.process_data(malformed_data)
      self.assertIn("Failed to decode JSON", cm.output[-1])

      udp_thread.stop()

   @patch('socket.socket')
   def test_missing_ip_in_json(self, mock_socket):
      """Test that UdpThread gracefully handles missing 'ip' field in JSON."""
      logging.info(f"Running test_missing_ip_in_json")

      mock_sock = mock_socket.return_value
      mock_sock.recvfrom.return_value = (json.dumps(self.random_json_data()).encode(), ('localhost', 12345))
      mock_sock.fileno.return_value = 1

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Send random data with missing 'ip' field
      invalid_json = self.random_json_data()
      invalid_json.pop("IP", None)  # Remove 'ip' to simulate the error
      mock_sock.recvfrom.return_value = (json.dumps(invalid_json).encode(), ('localhost', 12345))
      time.sleep(0.2)  # Wait for a cycle

      # Check logs for handling the missing 'ip' field
      with self.assertLogs(level='WARNING') as cm:
         udp_thread.process_data(json.dumps(invalid_json).encode())
      self.assertIn("Received JSON without 'ip' field", cm.output[-1])
      udp_thread.stop()

   @patch('socket.socket')
   def test_socket_timeout_handling(self, mock_socket):
      """Test UdpThread's behavior when socket times out."""

      mock_sock = mock_socket.return_value
      mock_sock.recvfrom.side_effect = socket.timeout
      mock_sock.fileno.return_value = 1

      udp_thread = UdpThread(ip="127.0.0.1", port=self.random_port(), update_seconds=0.1)

      # Simulate socket timeout and ensure thread continues to function
      time.sleep(1)  # Wait for a few cycles to ensure timeout is handled

      # Assert no exceptions occur during timeout handling
      self.assertEqual(udp_thread.sock, None)

      udp_thread.stop()

   def test_singleton_behavior(self):
      """Test that the UdpThread class adheres to the Singleton pattern."""
      logging.info(f"Running test_singleton_behavior")

      udp_thread_1 = UdpThread(ip="127.0.0.1", port=12345)
      udp_thread_2 = UdpThread(ip="127.0.0.1", port=12345)

      # Ensure both instances are the same
      self.assertIs(udp_thread_1, udp_thread_2)

      udp_thread_1.stop()
      udp_thread_2.stop()

   def test_thread_shutdown(self):
      """Test that UdpThread can be properly shut down."""
      logging.info(f"Running test_thread_shutdown")

      udp_thread = UdpThread(ip="127.0.0.1", port=12345)

      # Start the thread and stop it after a few seconds
      # threading.Thread(target=udp_thread.run, daemon=True).start()

      time.sleep(5)  # Give the thread time to run
      udp_thread.stop()

      self.assertIsNone(udp_thread.sock)


if __name__ == "__main__":
   import unittest

   unittest.main()
