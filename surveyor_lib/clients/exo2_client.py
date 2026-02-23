import argparse
import sys

import requests

from .base_client import BaseClient

PARAMS_DICT = {
    1: "Temperature (C)",  # In degrees
    2: "Temperature (F)",
    3: "Temperature (K)",
    4: "Conductivity (mS/cm)",
    5: "Conductivity (uS/cm)",  # u mircro S/cm
    6: "Specific Conductance (mS/cm)",
    7: "Specific Conductance (uS/cm)",
    10: "TDS (g/L)",
    12: "Salinity (PPT)",
    17: "pH (mV)",
    18: "pH",
    19: "ORP (mV)",
    20: "Pressure (psia)",
    21: "Pressure (psig)",
    22: "Depth (m)",
    23: "Depth (ft)",
    28: "Battery (V)",
    37: "Turbidity (NTU)",
    47: "NH3 (Ammonia) (mg/L)",
    48: "NH4 (Ammonium) (mg/L)",
    51: "Date (DDMMYY)",
    52: "Date (MMDDYY)",
    53: "Date (YYMMDD)",
    54: "Time (HHMMSS)",
    95: "TDS (kg/L)",
    101: "NO3 (Nitrate) (mV)",
    106: "NO3 (Nitrate) (mg/L)",
    108: "NH4 (Ammonium) (mV)",
    110: "TDS (mg/L)",
    112: "Chloride (mg/L)",
    145: "Chloride (mV)",
    190: "TSS (mg/L)",
    191: "TSS (g/L)",
    193: "Chlorophyll (ug/L)",
    194: "Chlorophyll (RFU)",
    201: "PAR (Channel 1)",
    202: "PAR (Channel 2)",
    204: "Rhodamine (ug/L)",
    211: "ODO (%Sat)",
    212: "ODO (mg/L)",
    214: "ODO (%Sat Local)",
    215: "TAL-PC (cells/mL)",
    216: "BGA-PC (RFU)",
    217: "TAL-PE (cells/mL)",
    218: "BGA-PE (RFU)",
    223: "Turbidity (FNU)",
    224: "Turbidity (Raw)",
    225: "BGA-PC (ug/L)",
    226: "BGA-PE (ug/L)",
    227: "fDOM (RFU)",
    228: "fDOM (QSU)",
    229: "Wiper Position (V)",
    230: "External Power (V)",
    231: "BGA-PC (Raw)",
    232: "BGA-PE (Raw)",
    233: "fDOM (Raw)",
    234: "Chlorophyll (Raw)",
    235: "Potassium (mV)",
    236: "Potassium (mg/L)",
    237: "nLF Conductivity (mS/cm)",
    238: "nLF Conductivity (uS/cm)",
    239: "Wiper Peak Current (mA)",
    240: "Vertical Position (m)",
    241: "Vertical Position (ft)",
    242: "Chlorophyll (cells/mL)",
}


class Exo2Client(BaseClient):
    def __init__(
        self,
        server_ip="192.168.0.68",
        server_port="5000",
    ):
        """
        Initialize the Exo2Client object.

        Args:
            server_ip (str, optional): The IP address of the server. Defaults to "192.168.0.68".
            server_port (str, optional): The port number of the server. Defaults to "5000".
        """
        super().__init__(server_ip, server_port)
        self.server_url += "/data"
        self.initialize_server_serial_connection()
        self.exo2_params = self.get_exo2_params()

    def get_data_from_command(self, command):
        """
        Send a POST request to the server with the specified command and retrieve the data.

        Args:
            command (str): The command string to send to the exo2 sonde.

        Returns:
            str: The data received from the exo2 sensor, or None if an error occurred.
        """
        try:
            response = requests.post(self.server_url, data=command)
            response.raise_for_status()  # Raise an exception for non-2xx status codes
            return response.text
        except requests.RequestException as e:
            print(f"Error sending command to server: {e}")
            return None

    def _get_data(self):
        """
        Send a GET request to the exo2 sensor and retrieve the data.

        Returns:
            str: The data received from the exo2 sensor, or None if an error occurred.
        """
        try:
            response = requests.get(
                self.server_url
            )  # Uses a get request instead of using send_command('data') for performance reasons
            response.raise_for_status()  # Raise an exception for non-2xx status codes
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching data from server: {e}")
            return None

    def get_data(self):
        """
        Get data from the Exo2 sensor.

        Returns:
            list: A list of float values representing the data from the Exo2 sensor.
        """
        exo2_data_str = self._get_data()
        while not exo2_data_str:
            # Keep requesting data until a non-empty string is received
            exo2_data_str = self._get_data()

        # Split the received string on whitespace and convert values to floats

        exo2_data_list = exo2_data_str.split()
        assert len(exo2_data_list) == len(self.exo2_params), (
            "For some reason the params and the data size do not match"
        )
        exo2_data_dict = {
            param_name: float(value)
            for param_name, value in zip(
                self.exo2_params.values(),
                exo2_data_list,
            )
        }
        return exo2_data_dict

    def get_exo2_params(self):
        """
        Get the Exo2 sensor parameters by sending the 'para' command.

        Returns:
            str: The parameters received from the server, or None if an error occurred.
        """
        param_str = None
        while not param_str:
            # Keep requesting data until a non-empty string (other than "#") is received
            param_str = self.get_data_from_command("para")
            try:
                param_list = list(map(int, param_str.split()))
            except:
                print("Received a non-integer list, attempting again...")
                param_str = None

        # Split the received string on whitespace and convert values to ints

        return {key: PARAMS_DICT[key] for key in param_list}

    def initialize_server_serial_connection(self):
        """
        Initializes the serial connection in the server and prints a confirmation string
        """
        print(self.get_data_from_command(b"init"))


def main(args):
    """
    The main function to run and test the Exo2Client.

    Args:
        args (dict): A dictionary of command-line arguments.
    """
    client = Exo2Client(**args)

    while True:
        data = client.get_data()
        if data:
            print(f"Received data: {data}")
            # Example of received data: "101723 141347 77.55 6.79 21.922 0.09 -0.00 14.71 10.364"


if __name__ == "__main__":
    print(f"Run {sys.argv[0]} -h  for help")
    parser = argparse.ArgumentParser(
        description="Client script to connect to a server."
    )

    # Add arguments
    parser.add_argument(
        "--server_ip",
        type=str,
        default="192.168.0.68",
        help="IP address of the server (default: 192.168.0.68).",
    )
    parser.add_argument(
        "--server_port",
        type=int,
        default=5000,
        help="Port number of the server (default: 5000).",
    )

    # Parse the command line arguments
    args = parser.parse_args()

    # Call the main function with the parsed arguments
    main(vars(args))
