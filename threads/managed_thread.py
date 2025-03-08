import logging
import threading
import time
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)


# Custom exceptions for thread-specific errors
class ThreadError(Exception):
   """Base class for all thread-related errors."""
   pass


class UpdateFailedError(ThreadError):
   """Exception raised when an update fails."""
   pass


class OperationFailedError(ThreadError):
   """Exception raised when a general operation fails."""
   pass


class ThreadState(Enum):
   INITIALING = "initialing"
   STOPPED = "stopped"
   RUNNING = "running"
   PAUSED = "paused"
   RESTARTING = "restarting"


class ManagedThread:
   """A base class for managing threads with periodic updates and controlled stopping."""

   def __init__(self, name="ManagedThread", update_seconds=0, max_retries=3, retry_delay=1, stop_timeout=5):
      self._state_lock = threading.Lock()
      with self._state_lock: self._state = ThreadState.INITIALING
      self.last_update = time.time() - update_seconds - 1  # Forces an immediate update
      self.update_seconds = update_seconds
      self._stop_event = threading.Event()
      self._pause_event = threading.Event()
      self._pause_event.set()
      self.max_retries = max_retries
      self.retry_delay = retry_delay
      self.stop_timeout = stop_timeout
      self.thread = threading.Thread(target=self._run_wrapper, name=name, daemon=True)
      self._set_state(ThreadState.RUNNING)
      self.thread.start()

      logger.debug(f"[{self.get_thread_name()}] Init'd")

   def _set_state(self, new_state):
      with self._state_lock:
         logger.debug(f"[{self.get_thread_name()}] Changing state from {self._state} to {new_state}")
         self._state = new_state

   def get_state(self):
      with self._state_lock:
         return self._state

   def _run_wrapper(self):
      try:
         self.run()
      except Exception as e:
         logger.error(f"[{self.get_thread_name()}] Thread encountered an error: {e}", exc_info=True)
         self._set_state(ThreadState.STOPPED)  # Mark the thread as stopped on failure

   def run(self):
      """Subclasses MUST implement this, this is where all the thread action occurs"""
      raise NotImplementedError("Subclasses must implement the 'run' method.")

   def stop(self):
      """Gracefully stops the thread and ensures it exits properly."""
      logger.debug(f"[{self.get_thread_name()}] Shutting down thread...")
      self._stop_event.set()
      self._pause_event.set()  # Ensure the thread isn't paused while stopping

      # Only join if the thread is actually alive
      if self.thread and self.thread.is_alive():
         self.thread.join(timeout=self.update_seconds)  # Wait for the thread to finish (last update)

         # Give the thread a 1/2 sec to update
         time.sleep(0.5)

         # Thread is alive if the timeout happened
         if self.thread.is_alive():
            logger.warning(f"[{self.get_thread_name()}] Thread did not stop within timeout.")

      self._set_state(ThreadState.STOPPED)

   def pause(self):
      logger.debug(f"[{self.get_thread_name()}] Pausing thread...")
      self._pause_event.clear()
      self._set_state(ThreadState.PAUSED)

   def resume(self):
      logger.debug(f"[{self.get_thread_name()}] Resuming thread...")
      self._pause_event.set()
      self._set_state(ThreadState.RUNNING)

   def restart(self):
      logger.debug(f"[{self.get_thread_name()}] Restarting thread...")
      # Ensure stop() only joins if the thread has been started
      if self.thread.is_alive():
         logger.warning(f"[{self.get_thread_name()}] Old thread is still running. Waiting before restart.")
         self.stop()
      self._stop_event.clear()
      self._set_state(ThreadState.RESTARTING)
      self.thread = threading.Thread(target=self._run_wrapper, name=self.get_thread_name(), daemon=True)
      self.thread.start()
      self._set_state(ThreadState.RUNNING)

   def should_stop(self):
      return self._stop_event.is_set()

   def is_paused(self):
      return not self._pause_event.is_set()

   def get_thread_name(self):
      return self.thread.name

   def needs_update(self):
      current_time = time.time()
      if (current_time - self.last_update) >= self.update_seconds:
         self.last_update = current_time
         return True
      return False

   def retry_operation(self, operation, retries=None, timeout=None):
      retries = retries or self.max_retries
      timeout = timeout or self.retry_delay
      attempt = 0
      while attempt < retries:
         try:
            operation()
            return
         except (UpdateFailedError, OperationFailedError) as e:
            attempt += 1
            logger.error(f"[{self.get_thread_name()}] Error during operation: {e}. Retrying... ({attempt}/{retries})")
            time.sleep(timeout)
      raise ThreadError(f"Operation failed after {retries} retries.")
   