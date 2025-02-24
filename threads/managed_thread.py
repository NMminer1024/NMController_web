import threading
import time
import logging
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


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


# Enum for thread states for better readability and control
class ThreadState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    RESTARTING = "restarting"


class ManagedThread:
    """A base class for managing threads with periodic updates and controlled stopping."""

    def __init__(self, name="ManagedThread", update_seconds=0, max_retries=3, retry_delay=1, stop_timeout=5):
        self.last_update = time.time() - update_seconds - 1  # Forces an immediate update
        self.update_seconds = update_seconds
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._state = ThreadState.STOPPED
        self._state_lock = threading.Lock()
        self.thread = threading.Thread(target=self._run_wrapper, name=name, daemon=True)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.stop_timeout = stop_timeout
        self.thread.start()
        self._set_state(ThreadState.RUNNING)

    def _run_wrapper(self):
        try:
            self.run()
        except Exception as e:
            logging.error(f"[{self.get_thread_name()}] Thread encountered an error: {e}", exc_info=True)

    def run(self):
        raise NotImplementedError("Subclasses must implement the 'run' method.")

    def stop(self):
        logging.info(f"[{self.get_thread_name()}] Shutting down thread...")
        self._stop_event.set()
        self._pause_event.set()
        self.thread.join(timeout=self.stop_timeout)
        if self.thread.is_alive():
            logging.warning(f"[{self.get_thread_name()}] Thread did not stop within timeout.")
        self._set_state(ThreadState.STOPPED)

    def pause(self):
        logging.info(f"[{self.get_thread_name()}] Pausing thread...")
        self._pause_event.clear()
        self._set_state(ThreadState.PAUSED)

    def resume(self):
        logging.info(f"[{self.get_thread_name()}] Resuming thread...")
        self._pause_event.set()
        self._set_state(ThreadState.RUNNING)

    def restart(self):
        logging.info(f"[{self.get_thread_name()}] Restarting thread...")
        self.stop()
        if self.thread.is_alive():
            logging.warning(f"[{self.get_thread_name()}] Old thread is still running. Waiting before restart.")
            self.thread.join(timeout=self.stop_timeout)
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
                logging.error(f"[{self.get_thread_name()}] Error during operation: {e}. Retrying... ({attempt}/{retries})")
                time.sleep(timeout)
        raise ThreadError(f"Operation failed after {retries} retries.")

    def _set_state(self, new_state):
        with self._state_lock:
            logging.info(f"[{self.get_thread_name()}] Changing state from {self._state} to {new_state}")
            self._state = new_state

    def get_state(self):
        with self._state_lock:
            return self._state


class MyThread(ManagedThread):
    """Example subclass implementing the run method."""

    def run(self):
        while not self.should_stop():
            try:
                if not self.is_paused():
                    self.retry_operation(self.perform_update)
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"[{self.get_thread_name()}] Error in run loop: {e}", exc_info=True)

    def perform_update(self):
        if self.needs_update():
            if time.time() % 2 < 1:
                logging.debug(f"[{self.get_thread_name()}] Update attempt failed. Will retry.")
                raise UpdateFailedError("Failed to update.")
            self.last_update = time.time()
            logging.info(f"[{self.get_thread_name()}] Custom thread is running...")


# Usage Example:
if __name__ == "__main__":
    my_thread = MyThread(name="MyCustomThread", update_seconds=2)
    time.sleep(6)
    my_thread.pause()
    time.sleep(3)
    my_thread.resume()
    time.sleep(2)
    my_thread.restart()
    time.sleep(6)
    my_thread.stop()
