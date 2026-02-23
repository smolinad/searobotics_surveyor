"""
This module:
    - Handles several tasks associated with the surveyor object, focusing on the manipulation and analysis of geospatial data,
    particularly GPS coordinates and NMEA messages.
    - Includes functionalities to create and evaluate coordinates for gradient assessment, generate square areas around specific GPS points,
    checks the proximity of coordinates, and extract specific NMEA messages like GPGGA and PSEAA.
    - Computes NMEA checksums, converts decimal degrees to NMEA format, and creates waypoint missions from CSV data.
Also supports saving these missions and related data to CSV files with date-specific filenames,
thereby facilitating the efficient management of navigation and surveying tasks for the surveyor object.
"""

import datetime
import os
from typing import Any, Callable, Dict, List, Tuple

import pynmea2
from geopy.distance import geodesic

from .logger import HELPER_LOGGER
from .waypoint_helper import (
    compute_nmea_checksum,
    create_waypoint_messages_df,
    create_waypoint_mission,
)

Coord = Tuple[float, float]


def are_coordinates_close(
    coord1: Coord,
    coord2: Coord,
    tolerance_meters: float = 2.0,
) -> bool:
    """
    Check if two coordinates are close enough based on a tolerance in meters.

    Parameters:
        coord1: (latitude, longitude).
        coord2: (latitude, longitude).
        tolerance_meters: Maximum allowed distance in meters.

    Returns:
        True if coords are within tolerance_meters, else False.
    """
    distance = geodesic(coord1, coord2).meters
    return distance <= tolerance_meters


def get_message_by_prefix(message: str, prefix: str) -> str | None:
    """Find the first line in message that starts with the given prefix."""
    for msg in message.split("\r\n"):
        if msg and msg.startswith(prefix):
            return msg
    return None


def get_gga(message: str) -> str | None:
    """Extract the GPGGA message line, if present."""
    return get_message_by_prefix(message, "$GPGGA")


def get_attitude_message(message: str) -> str | None:
    """Extract the PSEAA message line, if present."""
    return get_message_by_prefix(message, "$PSEAA")


def get_command_status_message(message: str) -> str | None:
    """Extract the PSEAD message line, if present."""
    return get_message_by_prefix(message, "$PSEAD")


def get_coordinates(gga_message):
    """
    Extract latitude and longitude coordinates from an NMEA GGA message.

    Args:
        gga_message (str): The NMEA GGA message string.

    Returns:
        dict: {"Latitude": float, "Longitude": float} if valid, else {}.
    """
    if not gga_message:
        HELPER_LOGGER.warning("Received an empty or None GGA message.")
        return None

    HELPER_LOGGER.debug("Parsing GGA message: %s", gga_message)

    try:
        # Parse the NMEA GGA message
        gga = pynmea2.parse(gga_message)

        # Extract latitude and longitude if valid
        if gga.latitude != 0.0 and gga.longitude != 0.0:
            HELPER_LOGGER.debug(
                "Successfully parsed coordinates: Latitude = %f, Longitude = %f",
                gga.latitude,
                gga.longitude,
            )
        else:
            HELPER_LOGGER.warning(
                "Parsed GGA message contains invalid coordinates: Latitude = %f, Longitude = %f",
                gga.latitude,
                gga.longitude,
            )
        return {
            "Latitude": gga.latitude,
            "Longitude": gga.longitude,
        }

    except pynmea2.ParseError as e:
        HELPER_LOGGER.error(
            "Failed to parse GGA message: %s, Error: %s",
            gga_message,
            e,
        )
    except (ValueError, TypeError) as e:
        HELPER_LOGGER.error(
            "Error processing GGA message: %s, Error: %s",
            gga_message,
            e,
        )

    # If any exception occurs or the message cannot be parsed, return {}
    HELPER_LOGGER.error("Failed to extract valid coordinates from GGA message")
    return {}


def process_proprietary_message(
    proprietary_message: str,
    value_names: List[str],
    process_fun: Callable[[str], Any],
) -> Dict[str, Any]:
    """
    Process a proprietary message and convert it into a dictionary.

    Args:
        proprietary_message: The proprietary message to be parsed.
        value_names: Names to map to each parsed value.
        process_fun: Function applied to each raw string value.

    Returns:
        dict: name -> processed value.
    """
    if not proprietary_message:
        HELPER_LOGGER.warning("Received empty or None proprietary message.")
        return {}

    HELPER_LOGGER.debug(
        "Receiving proprietary message: %s", proprietary_message
    )

    try:
        # Remove header and checksum
        message_parts = proprietary_message.split(",")[1:]
        last_element = message_parts.pop(-1).split("*")[0]
        message_parts.append(last_element)
    except Exception as e:
        HELPER_LOGGER.error("Error processing proprietary message: %s", e)
        return {}

    try:
        message_parts = [process_fun(element) for element in message_parts]
    except Exception as e:
        HELPER_LOGGER.error(
            "Error converting message parts with process_fun: %s", e
        )
        return {}

    return dict(zip(value_names, message_parts))


def get_attitude(attitude_message: str) -> Dict[str, float]:
    """
    Parses an attitude message string and returns a dictionary of corresponding attitude values.


    Parameters:
        attitude_message (str): A comma-separated string representing attitude data. It may contain
                                 values like pitch, roll, heading, etc. The string should include the
                                 protocol header ('$PESAA') and a checksum (e.g., '*7F') at the end,
                                 which will be discarded.

    Returns:
        dict: A dictionary where the keys are attitude names (e.g., 'Pitch', 'Roll', 'Heading') and
              the values are the corresponding numerical values parsed from the attitude message. If
              the input message is invalid or empty, an empty dictionary is returned.

    Example:
        If attitude_message is '$PESAA,12.34,56.78,-90.12,34.56,18.0,0.5,-0.2,0.8,1.5*7F',
        the function will return:
        {
            'Pitch': 12.34,
            'Roll': 56.78,
            'Heading': -90.12,
            'Heave': 34.56,
            'Temp': 18.0,
            'Acc_x': 0.5,
            'Acc_y': -0.2,
            'Acc_z': 0.8,
            'Yaw_rate': 1.5
        }
    """
    result = process_proprietary_message(
        attitude_message,
        get_attitude.value_names,
        get_attitude.process_fun,
    )
    return result


get_attitude.value_names = [
    "Pitch (degrees)",
    "Roll (degrees)",
    "Heading (degrees Magnetic)",
    "Heave",
    "Temperature in electronics box (degrees C)",
    "Acceleration x, forward (G)",
    "Acceleration y, starboard (G)",
    "Acceleration z, down (G)",
    "Yaw rate [degrees/s]",
]
get_attitude.process_fun = lambda x: (float(x) if x else 0.0)


def get_command_status(command_message: str) -> Dict[str, Any]:
    """
    Parses a command status message and returns a dictionary of corresponding status values.

    Args:
        command_message (str): A string representing the command status message. It should be a comma-separated
                                message with each part corresponding to a specific value, and may contain a
                                checksum at the end which will be discarded.

    Returns:
        dict: A dictionary where the keys are the command status names (e.g., 'Control Mode', 'Heading')
              and the values are the corresponding parsed values from the message. If the input message
              is invalid or empty, an empty dictionary is returned.

    Example:
        If command_message is '$PSEAA,1.5,T,2.5,0.5*7A', the function will return:
        {
            'Control Mode': 1.5,
            'Heading, degrees Magnetic': 'Thruster',
            'Thrust': 2.5,
            'Thrust difference': 0.5
        }

    Notes:
        - The function uses the `process_fun` lambda for processing numeric values and decoding command symbols.
        - The `command_dictionary` is used to map symbols (e.g., 'T', 'C', 'G') to human-readable descriptions.

    """
    result = process_proprietary_message(
        command_message,
        get_command_status.value_names,
        get_command_status.process_fun,
    )
    return result


get_command_status.value_names = [
    "Control Mode",
    "Heading (degrees Magnetic)",
    "Thrust (% Thrust)",
    "Thrust difference (% Thrust)",
]
get_command_status.command_dictionary = {
    "L": "Standby",
    "T": "Thruster",
    "C": "Heading",
    "G": "Speed",
    "R": "Station Keep",
    "N": "River Nav",
    "W": "Waypoint",
    "I": "Autopilot",
    "3": "Compass Cal",
    "H": "Go To ERP",
    "D": "Depth",
    "S": "Gravity Vector Direction",
    "F": "File Download",
    "!": "Boot Loader",
}


def _get_command_status_process_fun(x):
    if not x:
        return 0.0
    try:
        return float(x)
    except ValueError:
        return get_command_status.command_dictionary.get(x, "Unknown")


get_command_status.process_fun = _get_command_status_process_fun


def get_date() -> Dict[str, int]:
    """Return current date/time in integer YYYYMMDD / HHMMSS format."""
    now = datetime.datetime.now()  # Get the current date and time
    date_str = now.strftime("%Y%m%d")  # Format date as YYYY-MM-DD
    time_str = now.strftime("%H%M%S")  # Format time as HH:MM:SS
    return {
        "Date": int(date_str),
        "Time": int(time_str),
    }


def process_surveyor_message(message):
    """
    Processes a surveyor message and extracts attributes based on line prefixes.
    Args:
        message (str): The surveyor message to be parsed, containing multiple lines.

    Returns:
        dict: A dictionary of attributes extracted from the message.

    """
    attribute_dict = get_date()

    for message_line in message.split("\r\n"):
        if not message_line:
            continue
        prefix = message_line[:6]
        HELPER_LOGGER.debug("Processing message with prefix: %s", prefix)
        fun = process_surveyor_message.prefix_map.get(prefix, lambda _: {})
        attribute_dict.update(fun(message_line))

    HELPER_LOGGER.debug(f"Attributes updated: {attribute_dict}")
    return attribute_dict


process_surveyor_message.prefix_map = {
    "$GPGGA": get_coordinates,
    "$PSEAA": get_attitude,
    "$PSEAD": get_command_status,
}


if __name__ == "__main__":
    # Define file names
    filename = "square_mission"
    erp_filename = "erp_FIUMMC_lake"
    parent_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir)
    )
    print(parent_dir)
    # Open CSV files and create NMEA messages
    df = create_waypoint_messages_df(
        parent_dir + "/out/" + filename + ".csv",
        parent_dir + "/in/" + erp_filename + ".csv",
    )
    mission = create_waypoint_mission(df)

    # Save mission to file
    output_file_path = parent_dir + "/out/" + filename + ".sea"
    with open(output_file_path, "w") as file:
        file.write(mission)

    # Example usage:
    message = "PSEAA,-2.2,0.7,222.6,,47.8,-0.04,-0.01,-1.00,-0.01*7A\r\n"
    print(
        "checksum",
        str(compute_nmea_checksum(message)),
    )  # This should print "7D"

    gga_message = "$GPGGA,115739.00,4158.8441367,N,09147.4416929,W,4,13,0.9,255.747,M,-32.00,M,01,0000*6E\r\n"
    coordinates = get_coordinates(gga_message)
    if coordinates:
        print(f"Latitude: {coordinates['Latitude']}")
        print(f"Longitude: {coordinates['Longitude']}")
    else:
        print("Invalid or incomplete GGA sentence")

    ...
    gga_message = get_gga(message)
    coordinates = get_coordinates(gga_message) if gga_message else {}
    if coordinates:
        print(f"Latitude: {coordinates['Latitude']}")
        print(f"Longitude: {coordinates['Longitude']}")
    else:
        print("Invalid or incomplete GGA sentence")

    # Other debug prints and function calls
