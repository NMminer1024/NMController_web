import socket
import json
import time
import logging
from threads.managed_thread import ManagedThread

# Configure logging for better debugging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class UbpThread(ManagedThread):
    """
    UDP listener thread for receiving and processing NMMiner data.

    This class continuously listens for UDP packets, parses JSON data,
    and maintains a mapping of miner statuses.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def __init__(self, name="UbpThread", ip="0.0.0.0", port=12345, update_seconds=0.5):
        """
        Initializes the UDP listener thread.

        :param name: Name of the thread (default: "UbpThread").
        :param ip: IP address to bind the UDP socket (default: "0.0.0.0").
        :param port: Port to bind the UDP socket (default: 12345).
        :param update_seconds: Interval between updates (default: 0.5 sec).
        """
        super().__init__(name=name, update_seconds=update_seconds)

        # Create and bind the UDP socket
        self.sock.bind((ip, port))
        self.sock.settimeout(5)  # Set a timeout to prevent indefinite blocking

        self.nmminer_map = {}  # Dictionary to store miner data

    def get_miner_map(self):
        """Retrieves the current miner data map."""
        return self.nmminer_map

    def run(self):
        """Main loop of the thread. Listens for UDP messages and processes data."""
        logging.info("[UbpThread] Starting UDP listener...")

        while not self.should_stop():
            if self.needs_update():
                self.receive_data()
            else:
                time.sleep(0.1)  # Prevent excessive CPU usage

    def receive_data(self):
        """Listens for incoming UDP data, parses JSON, and updates nmminer_map."""
        try:
            data, _ = self.sock.recvfrom(1024)  # Receive up to 1024 bytes
            self.process_data(data)
        except socket.timeout:
            logging.debug("[UbpThread] UDP receive timeout (no data received).")  # Changed to debug
        except socket.error as e:
            logging.error(f"[UbpThread] Socket error: {e}", exc_info=True)
        except Exception as e:
            logging.exception(f"[UbpThread] Unexpected error: {e}")

    def process_data(self, data):
        """
        Parses incoming JSON data and updates the miner map.

        :param data: Raw UDP data received from the socket.
        """
        try:
            json_data = json.loads(data.decode('utf-8'))  # Ensure proper decoding
            ip = json_data.get("ip")

            if not ip:
                logging.warning(f"[UbpThread] Received JSON without 'ip' field: {json_data}")
                return

            json_data["UpdateTime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.nmminer_map[ip] = json_data  # Store miner data by IP
            logging.debug(f"[UbpThread] Updated miner data for IP: {ip}")

        except json.JSONDecodeError as e:
            logging.error(f"[UbpThread] Failed to decode JSON: {data}, Error: {e}", exc_info=True)
        except Exception as e:
            logging.exception(f"[UbpThread] Unexpected error in JSON processing: {e}")

    def stop(self):
        """Stops the thread and closes the socket."""
        super().stop()  # Gracefully stop the thread
        self.sock.close()  # Close socket to free the port


# Usage Example:
if __name__ == "__main__":
    udp_thread = UbpThread(port=12345, update_seconds=1)  # Start listening
    time.sleep(10)  # Let it run for a while
    udp_thread.stop()  # Stop the listener
