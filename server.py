from socket import *
import socket
import threading
import logging
import time
import sys

# Import the game protocol logic
from protocol import PlayerServerProtocol

# Initialize the game protocol handler
fp = PlayerServerProtocol()

# Configure logging for the server
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

class ProcessTheClient(threading.Thread):
    """
    Thread class to handle individual client connections.
    It receives commands, processes them using the PlayerServerProtocol,
    and sends back the response.
    """
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        threading.Thread.__init__(self) # Initialize the Thread superclass

    def run(self):
        """
        Main loop for the client processing thread.
        Receives data, processes it, and sends back responses.
        """
        # logging.warning(f"Starting client processing for {self.address}")
        try:
            while True:
                data_received_buffer = b""
                # Read until the delimiter is found or no more data
                while True:
                    chunk = self.connection.recv(4096)
                    if not chunk: # Client closed connection or no more data
                        break
                    data_received_buffer += chunk
                    if b"\r\n\r\n" in data_received_buffer:
                        break

                if not data_received_buffer: # No data received, client disconnected
                    break

                d = data_received_buffer.decode('utf-8').strip()
                # logging.warning(f"Received from {self.address}: {d}")

                hasil = fp.proses_string(d)
                hasil_bytes = (hasil + "\r\n\r\n").encode('utf-8')

                self.connection.sendall(hasil_bytes)
                # logging.warning(f"Sent to {self.address}: {hasil[:50]}...")

        except Exception as e:
            logging.error(f"Error processing client {self.address}: {e}")
        finally:
            self.connection.close()
            # logging.warning(f"Connection from {self.address} closed.")


class Server(threading.Thread):
    """
    Main server thread that listens for incoming client connections.
    For each new connection, it spawns a new ProcessTheClient thread.
    """
    def __init__(self, ipaddress='0.0.0.0', port=55554):
        self.ipinfo = (ipaddress, port)
        self.the_clients = []
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        threading.Thread.__init__(self)

    def run(self):
        """
        Main server loop. Binds to the specified address and listens for connections.
        """
        logging.warning(f"Server starting on {self.ipinfo}")
        try:
            self.my_socket.bind(self.ipinfo)
            self.my_socket.listen(5)

            while True:
                # logging.warning("Waiting for a connection...")
                self.connection, self.client_address = self.my_socket.accept()
                # logging.warning(f"Connection from {self.client_address}")

                clt = ProcessTheClient(self.connection, self.client_address)
                clt.start()
                self.the_clients.append(clt)

        except KeyboardInterrupt:
            logging.warning("Server is shutting down...")
        except Exception as e:
            logging.error(f"Server error: {e}")
        finally:
            self.my_socket.close()
            logging.warning("Server socket closed.")


def main():
    """Main function to start the server."""
    svr = Server(ipaddress='0.0.0.0', port=55554)
    svr.start()

if __name__ == "__main__":
    main()

