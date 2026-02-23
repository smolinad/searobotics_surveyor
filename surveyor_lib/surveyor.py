import logging
import os
import socket
import threading
import time
from datetime import datetime

import numpy as np
from geopy.distance import geodesic

from . import clients
from . import helpers as hlp


class Surveyor:
    VALID_CONTROL_MODES = {
        "Waypoint": ["thrust"],
        "Standby": [],
        "Thruster": ["thrust", "thrust_diff", "delay"],
        "Heading": ["thrust", "degrees"],
        "Go To ERP": [],
        "Station Keep": [],
        "Start File Download": ["num_lines"],
        "End File Download": [],
    }

    DEFAULT_SENSORS = ["exo2", "camera", "lidar"]
    DEFAULT_CONFIG = {
        "exo2": {"server_ip": "192.168.0.68", "server_port": 5000},
        "camera": {"server_ip": "192.168.0.20", "server_port": 5001},
        "lidar": {"server_ip": "192.168.0.20", "server_port": 5002},
    }
    SENSOR_CLIENTS = {
        "exo2": clients.Exo2Client,
        "camera": clients.CameraClient,
        "lidar": clients.LidarClient,
    }

    def __init__(
        self,
        host="192.168.0.50",
        port=8003,
        sensors_to_use=None,
        sensors_config=None,
        record=True,
        record_rate=1.0,
        logger_level=logging.INFO,
    ):
        """
        Initialize the Surveyor object with server connection details and sensor configurations.

        Args:
            host (str, optional): The IP address of the main server to connect to. Defaults to '192.168.0.50'.
            port (int, optional): The port number of the main server. Defaults to 8003.
            sensors_to_use (list of str, optional): List of sensor types to initialize (e.g., 'exo2', 'camera' or 'lidar').
                                                    Defaults to None, i.e. using all sensors.
            sensors_config (dict, optional): A dictionary for configuring each sensor. If a sensor's configuration is empty,
                                            it will be populated with default values. Defaults to
                                            None, i.e. taking Sensor Config Defaults.
            record (bool, optional): Whether to record data to HDF5. Defaults to True.
            record_rate (float, optional): Logging rate in Hz (records per second). Defaults to 1.0.
            logger_level (int, optional): Logging level (e.g., logging.INFO). Defaults to logging.INFO.

        Sensor Config Defaults:
            - 'exo2': {'exo2_server_ip': '192.168.0.68', 'exo2_server_port': 5000}
            - 'camera': {'camera_server_ip': '192.168.0.20', 'camera_server_port': 5001}
            - 'lidar': {'lidar_server_ip': '192.168.0.20', 'lidar_server_port': 5002}

        Attributes:
            host (str): IP address of the main server.
            port (int): Port number of the main server.
            exo2 (Exo2Client): Client for interacting with the EXO2 sensor (if 'exo2' is in sensors_to_use).
            camera (CameraClient): Client for interacting with the camera sensor (if 'camera' is in sensors_to_use).
            lidar (LidarClient): Client for interacting with the lidar sensor (if 'lidar' is in sensors_to_use).
        """
        self.host = host
        self.port = port

        self._sensors_to_use = [
            valid_sensor
            for valid_sensor in sensors_to_use
            if valid_sensor in self.DEFAULT_SENSORS
        ]
        self._sensors_config = self._build_sensor_config(sensors_config or {})
        self.sensors = self._init_sensors()

        self._state = {}
        self._parallel_update = True
        self.record = record
        self.record_rate = record_rate
        hlp.HELPER_LOGGER.setLevel(level=logger_level)
        self._logger = hlp.HELPER_LOGGER

    def _build_sensor_config(self, user_config: dict) -> dict:
        """
        Build a sensor configuration dictionary by merging default settings with user overrides.

        Args:
            user_config (dict): Dictionary containing user-specified sensor configuration overrides.

        Returns:
            dict: Final sensor configuration with user overrides applied to defaults.
        """
        config = {}
        for sensor in self._sensors_to_use:
            default = self.DEFAULT_CONFIG[sensor].copy()
            override = user_config.get(sensor, {})
            default.update(override)
            config[sensor] = default
        return config

    def _init_sensors(self) -> dict:
        """
        Initialize sensor client instances based on the configured sensors.

        Returns:
            dict: A dictionary mapping sensor names to their initialized client instances.
        """
        sensors = {}
        for sensor in self._sensors_to_use:
            if sensor in self.SENSOR_CLIENTS:
                client_cls = self.SENSOR_CLIENTS[sensor]
                ip = self._sensors_config[sensor]["server_ip"]
                port = self._sensors_config[sensor]["server_port"]
                sensors[sensor] = client_cls(ip, port)
        return sensors

    def __enter__(self):
        """
        Establish a connection with the remote server.

        Returns:
            Surveyor: The Surveyor object.

        Raises:
            socket.error: If an error occurs while connecting to the remote server.
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.settimeout(
                5
            )  # Set a timeout for the connection                print(f"Initializing sensor: {sensor}")
            self.socket.connect((self.host, self.port))
            self._logger.info("Surveyor connected!")

            self._receive_and_update_thread = threading.Thread(
                target=self._receive_and_update
            )  # Boat's state is received and parsed by an independent thread
            self._receive_and_update_thread.daemon = True
            self._receive_and_update_thread.start()

            while not self.get_state():
                time.sleep(0.1)
            self._logger.info("Update thread online!")

            if self.record:
                self._logger.info("Initializing record thread...")
                self._save_data_continuously()
            else:
                self._logger.info("Not recoding sensors...")

        except socket.error as e:
            self._logger.error(
                f"Error connecting to {self.host}:{self.port} - {e}"
            )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Close the connection with the remote server.
        """
        self._parallel_update = False  # Stop state update (boat IMU)
        if hasattr(self, "_receive_and_update_thread"):
            self._receive_and_update_thread.join()
        if hasattr(self, "_data_logger"):
            self._data_logger.stop()  # Stop HDF5 file logging

        self.socket.close()

    def send(self, msg):
        """
        Send an NMEA message to the remote server.

        Args:
            msg (str): The NMEA message to be sent.

        Raises:
            socket.error: If an error occurs while sending the message.
        """
        msg = hlp.create_nmea_message(msg)
        try:
            self.socket.send(msg.encode())
            time.sleep(0.005)
        except socket.error as e:
            self._logger.error(f"Error sending message - {e}")

    def receive(self, num_bytes=2048):
        """
        Receive data from the remote server.

        Args:
            num_bytes (int, optional): The maximum number of bytes to receive. Default is 4096.

        Returns:
            str: The received data as a string, or an empty string if no data was received.

        Raises:
            ConnectionError: If the connection is closed by the remote server.
            socket.timeout: If the socket times out while receiving data.
            socket.error: If an error occurs while receiving data.
        """

        try:
            data = self.socket.recv(num_bytes)
            if not data:
                raise ConnectionError("Connection closed by the server.")
            return data.decode("utf-8")
        except socket.timeout:
            self._logger.error("Socket timeout.")
            raise
        except socket.error as e:
            self._logger.error(f"Error receiving data - {e}")
            raise

    def _receive_and_update(self):
        while self._parallel_update:
            message = self.receive()
            updated_state = hlp.process_surveyor_message(message)
            self._state.update(updated_state)

    def _save_data_continuously(self):
        """Starts continuous logging of sensor and state data to HDF5 file."""

        # Data saved at ../../out/records/<today's  date>.h5
        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".h5"
        records_dir = os.path.join(hlp.DEFAULT_OUT_DIR_PATH, "records")
        os.makedirs(records_dir, exist_ok=True)

        # Initialize and start HDF5 logger
        filepath = os.path.join(records_dir, filename)

        self._data_logger = hlp.HDF5Logger(
            filepath=filepath,
            data_getter_func=self.get_data,
            interval=1 / self.record_rate,
        )
        self._logger.info(f"Started logging to: {filepath}")
        self._data_logger.start_continuous_logging()

    def set_thruster_mode(self, thrust, thrust_diff, delay=0.05):
        """
        Sets the ASV to thruster mode.

        Args:
            thrust (int): The base thrust value, ranging from -100 to 100.
                Negative values indicate reverse motion.
            thrust_diff (int): Differential thrust for steering, ranging from -100 to 100.
                Negative values indicate counter-clockwise rotation.
            delay (float, optional): Delay in seconds after sending the command.
                Defaults to 0.05.

        Notes:
            - Both `thrust` and `thrust_diff` are clipped to the range [-70, 70] for safety.
            - Each of these methods sends a formatted command string to the motor controller.
        """
        thrust, thrust_diff = np.clip([thrust, thrust_diff], -70, 70)
        thrust, thrust_diff = int(thrust), int(thrust_diff)
        msg = f"PSEAC,T,0,{thrust},{thrust_diff},"
        self.send(msg)
        time.sleep(delay)

    def set_standby_mode(self):
        """Sets the boat to standby mode"""
        msg = "PSEAC,L,0,0,0,"
        self.send(msg)

    def set_station_keep_mode(self):
        """Sets the boat to station keep mode"""
        msg = "PSEAC,R,,,,"
        self.send(msg)

    def set_heading_mode(self, thrust, degrees):
        """
        Sets the ASV to thruster mode.

        Args:
            thrust (int): The base thrust value, ranging from 0 to 100.
            degrees (int): Compass heading direction, ranging from 0 to 360
        Notes:
            - Both `thrust` and `degrees` are clipped to the range [0, 70], [0, 360] for safety.
        """
        thrust, degrees = np.clip([thrust, degrees], [0, 0], [70, 360])
        thrust, degrees = int(thrust), int(degrees)
        msg = f"PSEAC,C,{degrees},{thrust},,"
        self.send(msg)

    def set_waypoint_mode(self):
        """Sets the boat to waypoint mode"""
        msg = "PSEAC,W,0,0,0,"
        self.send(msg)

    def set_erp_mode(self):
        """Sets the boat to emergency recovery point mode"""
        msg = "PSEAC,H,0,0,0,"
        self.send(msg)

    def start_file_download_mode(self, num_lines):
        """
        Sets the ASV to file download mode.

        Args:
            num_lines (int): The number of lines to be sent to the boat.
        """
        if num_lines != int(num_lines):
            self._logger.error(
                "Non integer number of lines. Converting to integer..."
            )
        msg = "PSEAC,F," + str(int(num_lines)) + ",000,000,"
        self.send(msg)
        time.sleep(0.1)

    def end_file_download_mode(self):
        """Finishes the boat's file download mode"""
        msg = "PSEAC,F,000,000,000"
        self.send(msg)
        time.sleep(0.1)

    def set_control_mode(self, mode, **args):
        """
        Set the control mode for the vehicle.

        Args:
            mode (str): The control mode to set.
            **args: Additional arguments required for specific modes.
        """
        if mode not in self.VALID_CONTROL_MODES:
            self._logger.error(f"Invalid control mode: '{mode}'")
            raise ValueError(
                f"Invalid control mode: '{mode}'. "
                f"Valid modes are: {list(self.VALID_CONTROL_MODES.keys())}"
            )

        required_args = self.VALID_CONTROL_MODES[mode]
        missing_args = [arg for arg in required_args if arg not in args]
        if missing_args:
            self._logger.error(
                f"Missing arguments for mode '{mode}': {missing_args}"
            )
            raise KeyError(
                f"Missing arguments for mode '{mode}': {missing_args}"
            )

        try:
            if mode == "Waypoint":
                self.set_waypoint_mode()
            elif mode == "Standby":
                self.set_standby_mode()
            elif mode == "Thruster":
                self.set_thruster_mode(
                    args["thrust"], args["thrust_diff"], args["delay"]
                )
            elif mode == "Heading":
                self.set_heading_mode(args["thrust"], args["degrees"])
            elif mode == "Go To ERP":
                self.set_erp_mode()
            elif mode == "Station Keep":
                self.set_station_keep_mode()
            elif mode == "Start File Download":
                self.start_file_download_mode(args["num_lines"])
            elif mode == "End File Download":
                self.end_file_download_mode()
        except Exception as e:
            self._logger.error(f"Error executing control mode '{mode}': {e}")

    def send_waypoints(self, waypoints, erp, throttle):
        """
        Send a list of waypoints to the surveyor.

        Args:
            waypoints (list): A list of tuples (latitude, longitude) containing the waypoints.
            erp (list): A list with one tuple (latitude, longitude) for the emergency recovery point.
            throttle (float): The throttle value for the PSEAR command.

        Raises:
            ValueError: If the generated DataFrame from waypoints is empty.
            socket.error: If an error occurs while sending the commands.
        """
        # Create a DataFrame from the list of waypoints and ERP message
        df = hlp.create_waypoint_messages_df_from_list(waypoints, erp)
        throttle = int(
            np.clip(throttle, 0, 70)
        )  # Ensure proper throttle format

        if df.empty:
            self._logger.error("Waypoints DataFrame is empty.")
            raise ValueError("DataFrame is empty.")

        # Calculate the total number of lines to send: waypoints + ERP + PSEAR command
        n_lines = len(df) + 1

        # List to store all the commands to be sent
        commands = []

        # Create the PSEAR command with the specified throttle value
        psear_cmd = "PSEAR,0,000,{},0,000".format(throttle)
        psear_cmd_with_checksum = hlp.create_nmea_message(psear_cmd)
        commands.append(psear_cmd_with_checksum)

        # Add OIWPL commands generated from the DataFrame
        oiwpl_cmds = df["nmea_message"].tolist()
        commands.extend(oiwpl_cmds)

        try:
            # Start file download mode with the number of lines to send
            self.start_file_download_mode(n_lines)

            # Send each command to the remote server
            for cmd in commands:
                self.send(cmd)

            # End file download mode
            self.end_file_download_mode()
        except socket.error as e:
            self._logger.error(f"Error sending waypoints - {e}")
            raise

    def go_to_waypoint(
        self,
        waypoint,
        erp,
        throttle,
        tolerance_meters=2.0,
    ):
        """
        Load the next waypoint, send it to the boat and sets the boat to navigate towards it.

        Args:
            waypoint (tuple): The waypoint coordinates to be sent.
            erp (list): A list of ERP coordinates.
            throttle (int): The desired throttle value for the boat.
            tolerance_meters (float): The tolerance distance for the waypoint in meters.
            If the waypoint is within the margin, it will be loaded only once.
        """

        self.send_waypoints([waypoint], erp, throttle)
        dist = geodesic(waypoint, self.get_gps_coordinates()).meters
        self._logger.info(
            f"Heading to waypoint {waypoint} located at {dist:.2f} meters with throttle {throttle}"
        )
        self.set_waypoint_mode()
        while (
            self.get_control_mode() != "Waypoint" and dist > tolerance_meters
        ):
            dist = geodesic(
                waypoint,
                self.get_gps_coordinates(),
            ).meters
            self.set_waypoint_mode()

    def get_state(self):
        return self._state

    def get_control_mode(self):
        """
        Get control mode data from the Surveyor connection object.

        Returns:
            Control mode string.
        """

        return self._state.get("Control Mode", "Unknown")

    def get_gps_coordinates(self):
        """
        Get GPS coordinates from the Surveyor connection object.

        Returns:
            Tuple containing GPS coordinates.
        """

        return (
            self._state.get("Latitude", 0.0),
            self._state.get("Longitude", 0.0),
        )

    def get_exo2_data(self):
        """
        Retrieve data from the EXO2 sensor.

        Returns:
           list: A list of float values representing the data from the Exo2 sensor.
        """

        return self.sensors["exo2"].get_data()

    def get_image(self):
        """
        Retrieve an image from the camera.

        Returns:
            tuple: A tuple containing a boolean value indicating whether the frame is read successfully
                   and the frame itself.
        """
        return self.sensors["camera"].get_data()

    def get_lidar_data(self):
        """
        Retrieve the lidar measurements.

        Returns:
            tuple: A 360 list containing the lidar measurements
            and a list with their corresponding angles [0-360] degrees.
        """
        return self.sensors["lidar"].get_data()

    def get_data(self, keys=None):
        """
        Retrieve data based on specified keys using corresponding getter functions.

        Args:
            keys (list, optional): A list of keys indicating the types of data to retrieve. Defaults to ['state'] + self._sensors_to_use i.e. the state
            and the data from the sensors used.

        Returns:
            dict: A dictionary containing the retrieved data for each specified key.
        """
        # Dictionary mapping keys to corresponding getter functions.
        # Must return either a list of values or a dictionary paired by name : value.
        # In the case it returns a list, data_labels dict has to be updated with a list of names

        keys = keys or (["state"] + self._sensors_to_use)

        getter_functions = {
            "exo2": self.get_exo2_data,  # Dictionary with Exo2 sonde data
            "state": self.get_state,
            "camera": self.get_image,
            "lidar": self.get_lidar_data,
        }
        data_labels = {
            "camera": ["Image ret", "Image"],
            "lidar": ["Distances", "Angles"],
        }

        # Initialize a list to store retrieved data
        data_dict = {}

        # Iterate over specified keys and retrieve data using corresponding getter functions
        for key in keys:
            if key not in getter_functions:
                self._logger.error(f"Invalid key '{key}' in getter_functions.")
                continue
            data = getter_functions[key]()
            if isinstance(data, float):
                data = [data]
            if key in data_labels and not isinstance(data, dict):
                if len(data_labels[key]) != len(data):
                    self._logger.error(
                        f"Mismatch in lengths for key '{key}': {len(data_labels[key])} labels vs {len(data)} data."
                    )
                    continue
                data = dict(zip(data_labels[key], data))
            if isinstance(data, dict):
                data_dict.update(data)
            else:
                data_dict[key] = data

        return data_dict
