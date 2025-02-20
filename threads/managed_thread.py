import threading
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class ManagedThread:
    """A base class for managing threads with periodic updates and controlled stopping."""

    def __init__(self, name="ManagedThread", update_seconds=0):
        """
        Initializes a managed thread.

        :param name: Name of the thread.
        :param update_seconds: Time interval for periodic updates.
        """
        self.last_update = time.time() - update_seconds - 1  # Forces an immediate update
        self.update_seconds = update_seconds
        self._stop_event = threading.Event()  # Event to signal the thread to stop
        self.thread = threading.Thread(target=self._run_wrapper, name=name, daemon=True)
        self.thread.start()

    def _run_wrapper(self):
        """Internal method that wraps the run method and ensures proper thread management."""
        try:
            self.run()  # This should be implemented in the subclass
        except Exception as e:
            logging.error(f"[{self.get_thread_name()}] Thread encountered an error: {e}", exc_info=True)

    def run(self):
        """This method should be implemented in subclasses."""
        raise NotImplementedError("Subclasses must implement the 'run' method.")

    def stop(self):
        """Gracefully stops the thread and ensures it exits properly."""
        logging.info(f"[{self.get_thread_name()}] Shutting down thread...")
        self._stop_event.set()
        self.thread.join(timeout=5)  # Wait for the thread to finish (max 5 sec)
        if self.thread.is_alive():
            logging.warning(f"[{self.get_thread_name()}] Thread did not stop within timeout.")

    def should_stop(self):
        """Check if the stop event is set."""
        return self._stop_event.is_set()

    def get_thread_name(self):
        """Get the name of the current thread."""
        return self.thread.name

    def needs_update(self):
        """Check if the update interval has passed and reset the last update time."""
        current_time = time.time()
        if (current_time - self.last_update) >= self.update_seconds:
            self.last_update = current_time  # Reset last update time
            return True
        return False


class MyThread(ManagedThread):
    """Example subclass implementing the run method."""

    def run(self):
        """
        Runs the custom thread logic.

        The thread periodically checks for updates and performs an action.
        """
        while not self.should_stop():
            try:
                if self.needs_update():  # Only update when needed
                    logging.info(f"[{self.get_thread_name()}] Custom thread is running...")
                time.sleep(0.1)  # Efficient sleep to prevent high CPU usage
            except Exception as e:
                logging.error(f"[{self.get_thread_name()}] Error in run loop: {e}", exc_info=True)


# Usage Example:
if __name__ == "__main__":
   my_thread = MyThread(name="MyCustomThread", update_seconds=2)  # Start with update every 2 sec
   time.sleep(6)  # Let it run for a while
   my_thread.stop()  # Stop the thread
