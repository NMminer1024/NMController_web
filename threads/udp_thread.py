import socket
import json
import time
import logging
import select
import threading
from threads.managed_thread import ManagedThread

# Configure logging for better debugging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class UdpThread(ManagedThread):
    """
    Singleton UDP listener thread for receiving and processing NMMiner data.
    This class continuously listens for UDP packets, parses JSON data,
    and maintains a mapping of miner statuses.
    """
    _instance = None
    _lock = threading.Lock()  # Lock to ensure thread safety in instance creation
    sock = None

    def __new__(cls, *args, **kwargs):
        """Ensure only one instance is created."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(UdpThread, cls).__new__(cls)
                cls._instance._initialized = False  # Flag to check initialization
        return cls._instance


    def __init__(self, name="UdpThread", ip="0.0.0.0", port=12345, update_seconds=0.5):
        """Initializes the UDP listener thread."""
        if self._initialized:
            return  # Prevent re-initialization if already initialized
        super().__init__(name=name, update_seconds=update_seconds)

        self.lock = threading.Lock()  # Lock for thread-safe updates
        self.nmminer_map = {}  # Dictionary to store miner data

        # Socket initialization (only once per singleton instance)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5)  # Set timeout for socket operations

        try:
            self.sock.bind((ip, port))
            logging.info(f"{self.get_thread_name()} Listening on {ip}:{port}")
        except socket.error as e:
            logging.error(f"{self.get_thread_name()} Error binding socket to {ip}:{port}. Error: {e}")
            raise
        except Exception as e:
            logging.exception(f"{self.get_thread_name()} Unexpected error while setting up the socket: {e}")
            raise

        self._initialized = True  # Mark as initialized

    def get_miner_map(self):
        """Retrieves the current miner data map."""
        with self.lock:
            return self.nmminer_map.copy()

    def run(self):
        """Main loop of the thread. Listens for UDP messages and processes data."""
        logging.info(f"{self.get_thread_name()} Starting UDP listener...")

        while not self.should_stop():
            try:
                if self.needs_update():
                    self.receive_data()
                else:
                    time.sleep(0.1)  # Prevent excessive CPU usage
            except Exception as e:
                logging.exception(f"{self.get_thread_name()} Unexpected error in run loop: {e}")

    def receive_data(self):
        """Listens for incoming UDP data, parses JSON, and updates nmminer_map."""
        if self.sock is None or self.sock.fileno() == -1:
            logging.debug(f"{self.get_thread_name()} UDP socket has been closed and unable to receive data.")
            return

        ready = select.select([self.sock], [], [], 0.1)  # Check with a timeout
        if ready[0]:
            data, _ = self.sock.recvfrom(1024)  # Receive up to 1024 bytes
            self.process_data(data)
        else:
            logging.debug(f"{self.get_thread_name()} No data received this cycle.")  # Debug-level message when no data is received

    def process_data(self, data):
        """
        Parses incoming JSON data and updates the miner map.

        :param data: Raw UDP data received from the socket.
        """
        try:
            json_data = json.loads(data.decode('utf-8'))  # Ensure proper decoding
            ip = json_data.get("ip")

            if not ip:
                logging.warning(f"{self.get_thread_name()} Received JSON without 'ip' field: {json_data}")
                return

            json_data["UpdateTime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            with self.lock:
                self.nmminer_map[ip] = json_data  # Store miner data by IP

            logging.debug(f"{self.get_thread_name()} Updated miner data for IP: {ip}")

        except json.JSONDecodeError as e:
            logging.error(f"{self.get_thread_name()} Failed to decode JSON: {data}, Error: {e}", exc_info=True)
        except Exception as e:
            logging.exception(f"{self.get_thread_name()} Unexpected error in JSON processing: {e}")

    def stop(self):
        """Stops the thread and closes the socket."""
        super().stop()  # Gracefully stop the thread
        if self.sock:
            self.sock.close()  # Close socket to free the port
            self.sock = None  # Avoid trying to use this closed socket again
            logging.info(f"{self.get_thread_name()} Socket closed and thread stopped.")


# Usage Example:
if __name__ == "__main__":
    udp_thread_1 = UdpThread(port=12345, update_seconds=1)
    udp_thread_2 = UdpThread()  # This should return the same instance

    print(f"Both instances are the same: {udp_thread_1 is udp_thread_2}")  # Should print True

    time.sleep(10)  # Let it run for a while
    udp_thread_1.stop()  # Stop the listener
