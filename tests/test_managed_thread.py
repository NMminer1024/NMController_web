import logging
import time
import unittest
from unittest.mock import patch

from threads.managed_thread import OperationFailedError, UpdateFailedError, ManagedThread, ThreadError, ThreadState


class MockManagedThread(ManagedThread):
   """A mock subclass of ManagedThread for testing purposes."""

   def run(self):
      """Override the run method to simulate behavior."""
      iteration_limit = 5
      iterations = 0
      while not self.should_stop() and iterations < iteration_limit:
         if self.needs_update():
            self.perform_update()  # Ensure this is called
         time.sleep(0.1)
         iterations += 1

   def perform_update(self):
      """Mock implementation of perform_update."""
      logging.info(f"[{self.get_thread_name()}] Mock update performed.")


class TestManagedThread(unittest.TestCase):
   """Test suite for ManagedThread class."""

   @patch("threading.Thread.start")
   def test_initialization(self, mock_thread_start):
      """Test that the thread is initialized properly."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)

      # Verify thread has started and state is 'running'
      mock_thread_start.assert_called_once()
      self.assertEqual(thread.get_state(), ThreadState.RUNNING)
      self.assertFalse(thread.should_stop())

   def test_get_thread_name(self):
      """Test get_thread_name() returns the correct thread name."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)
      self.assertEqual(thread.get_thread_name(), "TestThread")

   @patch("logging.error")
   def test_run_exception_handling(self, mock_log_error):
      """Test that run() correctly logs an error when an exception occurs."""

      class FailingThread(MockManagedThread):
         def run(self):
            raise RuntimeError("Test exception")

      thread = FailingThread(name="FailingThread", update_seconds=1)

      mock_log_error.assert_called_once_with(
         "[FailingThread] Thread encountered an error: Test exception", exc_info=True
      )

   def test_should_stop(self):
      """Test that should_stop() returns True after stopping the thread."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)
      self.assertFalse(thread.should_stop())  # Initially, it should be False
      thread.stop()
      self.assertTrue(thread.should_stop())  # After stopping, it should be True

   @patch("threading.Thread.join", return_value=None)  # Mock join to prevent blocking
   def test_stop_while_paused(self, mock_join):
      """Test that a thread can be stopped while paused."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)
      thread.pause()
      thread.stop()
      self.assertEqual(thread.get_state(), ThreadState.STOPPED)

   def test_multiple_pauses(self):
      """Test pausing multiple times doesn't cause issues."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)
      thread.pause()
      self.assertTrue(thread.is_paused())
      thread.pause()  # Call pause again
      self.assertTrue(thread.is_paused())  # Still paused
      thread.resume()
      self.assertFalse(thread.is_paused())  # Should resume correctly

   @patch("threading.Thread.start")
   def test_restart_while_paused(self, mock_thread_start):
      """Test restarting a thread while it's paused."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)
      thread.pause()
      self.assertEqual(thread.get_state(), ThreadState.PAUSED)

      thread.restart()
      self.assertEqual(thread.get_state(), ThreadState.RUNNING)

   @patch("time.sleep", return_value=None)  # Mock sleep to prevent actual waiting
   def test_pause_resume(self, mock_sleep):
      """Test pausing and resuming the thread."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)

      thread.pause()
      self.assertEqual(thread.get_state(), ThreadState.PAUSED)
      self.assertTrue(thread.is_paused())

      thread.resume()
      self.assertEqual(thread.get_state(), ThreadState.RUNNING)
      self.assertFalse(thread.is_paused())

   def test_multiple_resumes(self):
      """Test resuming multiple times doesn't cause issues."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)
      thread.pause()
      thread.resume()
      self.assertFalse(thread.is_paused())
      thread.resume()  # Call resume again
      self.assertFalse(thread.is_paused())  # Still running

   @patch("time.sleep", return_value=None)  # Mock sleep to prevent actual waiting
   @patch("threading.Thread.start")
   @patch("threading.Thread.join", return_value=None)  # Ensure stop doesn't block
   def test_restart(self, mock_join, mock_thread_start, mock_sleep):
      """Test restarting the thread."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)

      # Ensure initial state
      self.assertEqual(thread.get_state(), ThreadState.RUNNING)

      # Restart the thread
      thread.restart()

      # Ensure the new thread was started
      mock_thread_start.assert_called()

      # Ensure the thread is running after restart
      self.assertEqual(thread.get_state(), ThreadState.RUNNING)

   @patch("time.sleep", return_value=None)  # Mock sleep to prevent actual waiting
   @patch("threading.Thread.join", return_value=None)  # Mock join to prevent blocking
   def test_stop(self, mock_join, mock_sleep):
      """Test that the thread stops correctly."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)
      thread.stop()

      # Ensure the stop event was set and the thread is stopped
      self.assertTrue(thread.should_stop())
      self.assertEqual(thread.get_state(), ThreadState.STOPPED)

   @patch("time.sleep", return_value=None)  # Mock sleep to prevent actual waiting
   def test_retry_operation_partial_success(self, mock_sleep):
      """Test retry operation succeeds after initial failures."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)

      attempts = 0

      def mock_failing_then_successful_operation():
         nonlocal attempts
         attempts += 1
         if attempts < 3:
            raise UpdateFailedError("Temporary failure")
         logging.info("Operation succeeded")

      thread.retry_operation(mock_failing_then_successful_operation, retries=5)
      self.assertEqual(attempts, 3)  # Should succeed on the third attempt

   @patch("time.sleep", return_value=None)  # Mock sleep to prevent actual waiting
   def test_retry_operation_success(self, mock_sleep):
      """Test retry operation logic when the operation succeeds."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)

      # Simulate a successful operation on the first try
      def mock_successful_operation():
         logging.info("Operation succeeded")

      # Test the retry operation (should succeed on the first attempt)
      thread.retry_operation(mock_successful_operation)
      logging.info("Retry operation test passed")

   @patch("time.sleep", return_value=None)  # Mock sleep to prevent actual waiting
   def test_retry_operation_failure(self, mock_sleep):
      """Test retry operation logic when the operation fails and retries are exhausted."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)

      # Simulate a failed operation
      def mock_failed_operation():
         raise UpdateFailedError("Operation failed")

      # Test the retry operation (should retry 3 times and then raise a ThreadError)
      with self.assertRaises(ThreadError):
         thread.retry_operation(mock_failed_operation)

   @patch("time.sleep", return_value=None)  # Mock sleep to prevent actual waiting
   def test_update_logic(self, mock_sleep):
      """Test the update logic of the thread."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)

      with patch.object(thread, "perform_update") as mock_perform_update:
         with patch.object(thread, "needs_update", return_value=True):
            thread.run()

         # Ensure perform_update() was called at least once
         mock_perform_update.assert_called()

      thread.stop()

   @patch("time.sleep", return_value=None)  # Mock sleep to prevent actual waiting
   def test_operation_failure_with_retries(self, mock_sleep):
      """Test retry logic with failing operations."""
      thread = MockManagedThread(name="TestThread", update_seconds=1)

      # Simulate a failed operation that exceeds retry attempts
      def mock_failing_operation():
         raise OperationFailedError("Operation failed")

      # Test the retry operation (should fail after max retries)
      with self.assertRaises(ThreadError):
         thread.retry_operation(mock_failing_operation, retries=3)


if __name__ == "__main__":
   unittest.main()
