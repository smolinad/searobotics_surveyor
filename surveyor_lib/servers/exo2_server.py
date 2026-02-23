import argparse
import http.server
import platform
import re
import socketserver
import sys

import serial
from port_selector import get_serial_port  # Import the port selector function

OS_TYPE = platform.system()


class Exo2Server(http.server.SimpleHTTPRequestHandler):
    serial_port = "COM4"  # Default values
    baud_rate = 9600
    port = 5000
    timeout = 0.1
    serial_connection: serial.Serial | None = None
    host = "0.0.0.0"

    @classmethod
    def initialize_serial(cls):
        """
        Initialize the serial connection with the given parameters.
        """
        print(f"Initializing serial connection on {cls.serial_port}...")
        cls.serial_connection = serial.Serial(
            cls.serial_port,
            cls.baud_rate,
            timeout=cls.timeout,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,
            rtscts=False,
        )

    @property
    def serial(self) -> serial.Serial:
        """Convenience accessor that ensures serial is initialized and open."""
        if (
            Exo2Server.serial_connection is None
            or not Exo2Server.serial_connection.is_open
        ):
            Exo2Server.initialize_serial()
        return Exo2Server.serial_connection

    def send_and_receive_serial_command(self, command: bytes) -> bytes:
        """
        Send a command to the serial port and receive the response.
        """
        try:
            self.serial.write(command)
            data = self.serial.readline().strip()  # Read the command echo
            if (
                not data
                or data.startswith(b"#")
                or bool(
                    re.search(
                        r"[a-zA-Z]", data.decode("utf-8", errors="ignore")
                    )
                )
            ):
                data = self.serial.readline().strip()  # Read the actual data
            return data
        except serial.SerialException as e:
            print(f"Serial communication error: {e}")
            return b"Error in serial communication"

    def send_response_to_client(self, response_code: int, data: bytes) -> None:
        """
        Send a response to the client.
        Args:
            response_code (int): The HTTP response code.
            data (bytes): The data to send in the response body.
        """
        self.send_response(response_code)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        """
        Handle GET requests.
        """
        if self.path == "/data":
            data = self.send_and_receive_serial_command(b"data\r")
            self.send_response_to_client(200, data)
        else:
            self.send_response_to_client(404, b"Not found")

    def do_POST(self):
        """
        Handle POST requests.
        """
        if self.path == "/data":
            content_length = int(self.headers.get("Content-Length", "0"))
            command_received = self.rfile.read(content_length) + b"\r"

            if command_received == b"init\r":
                # Handcrafted init command, not an EXO2 command
                if self.serial.is_open:
                    data = b"Connection Initialized"
                else:
                    data = b"Error opening serial port"
            else:
                data = self.send_and_receive_serial_command(command_received)

            self.send_response_to_client(200, data)
        else:
            self.send_response_to_client(404, b"Not found")


def main():
    """
    Main function to start the server.
    """
    try:
        Exo2Server.initialize_serial()
        with socketserver.TCPServer(
            (Exo2Server.host, Exo2Server.port), Exo2Server
        ) as server:
            print(
                f"Serving at {Exo2Server.host}:{Exo2Server.port}, "
                f"reading from {Exo2Server.serial_port} at {Exo2Server.baud_rate} baud "
                f"with a timeout of {Exo2Server.timeout} seconds."
            )
            server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        if (
            Exo2Server.serial_connection
            and Exo2Server.serial_connection.is_open
        ):
            Exo2Server.serial_connection.close()
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        if (
            Exo2Server.serial_connection
            and Exo2Server.serial_connection.is_open
        ):
            Exo2Server.serial_connection.close()
        sys.exit(1)


if __name__ == "__main__":
    # Add arguments
    parser = argparse.ArgumentParser(
        description="Server script for serial communication."
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host IP (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port number (default: 5000).",
    )
    parser.add_argument(
        "--serial_port",
        type=str,
        default=("COM4" if OS_TYPE == "Windows" else "/dev/ttyUSB0"),
        help="COM port (default: COM4 for Windows, /dev/ttyUSB0 for Linux).",
    )
    parser.add_argument(
        "--baud_rate",
        type=int,
        default=9600,
        help="Baud rate (default: 9600).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.1,
        help="Timeout in seconds (default: 0.1).",
    )
    parser.add_argument(
        "--find_serial_port",
        action="store_true",
        help="Automatically find the serial port (non-Windows only).",
    )

    # Parse the command line arguments
    args = vars(parser.parse_args())

    # Automatically find the serial port if requested
    if args["find_serial_port"] and OS_TYPE != "Windows":
        serial_port = get_serial_port("FTDI")
        if serial_port:
            args["serial_port"] = serial_port
        else:
            print(
                "Error: No serial port found. Using the provided serial port."
            )

    Exo2Server.host = args["host"]
    Exo2Server.port = int(args["port"])
    Exo2Server.serial_port = args["serial_port"]
    Exo2Server.baud_rate = int(args["baud_rate"])
    Exo2Server.timeout = float(args["timeout"])

    main()
