from typing import Callable

import pandas as pd

from .logger import HELPER_LOGGER


def compute_nmea_checksum(message: str) -> str:
    """
    Compute the checksum for an NMEA message.

    Args:
        message (str): The NMEA message string.

    Returns:
        str: The computed checksum in hexadecimal format.
    """
    checksum = 0
    for char in message:
        checksum ^= ord(char)
    return "{:02X}".format(checksum)


def convert_lat_to_nmea_degrees_minutes(decimal_degree: float) -> str:
    """
    Convert a decimal degree latitude value to NMEA format (degrees and minutes).

    Args:
        decimal_degree (float): The decimal degree latitude value.

    Returns:
        str: The latitude in NMEA format (degrees and minutes).
    """
    degrees = int(abs(decimal_degree))  # Degrees
    minutes_decimal = (abs(decimal_degree) - degrees) * 60  # Minutes
    return "{:02d}{:.4f}".format(degrees, minutes_decimal)


def convert_lon_to_nmea_degrees_minutes(decimal_degree: float) -> str:
    """
    Convert a decimal degree longitude value to NMEA format (degrees and minutes).

    Args:
        decimal_degree (float): The decimal degree longitude value.

    Returns:
        str: The longitude in NMEA format (degrees and minutes).
    """
    degrees = int(abs(decimal_degree))
    minutes_decimal = (abs(decimal_degree) - degrees) * 60
    return "{:03d}{:.4f}".format(degrees, minutes_decimal)


def get_hemisphere_lat(value: float) -> str:
    """
    Get the hemisphere ('N' or 'S') for a given latitude value.

    Args:
        value (float): The latitude value.

    Returns:
        str: The hemisphere ('N' or 'S') for the given latitude value.
    """
    return "N" if value >= 0 else "S"


def get_hemisphere_lon(value: float) -> str:
    """
    Get the hemisphere ('E' or 'W') for a given longitude value.

    Args:
        value (float): The longitude value.

    Returns:
        str: The hemisphere ('E' or 'W') for the given longitude value.
    """
    return "E" if value >= 0 else "W"


def create_nmea_message(
    message: str,
    checksum_func: Callable[[str], str] = compute_nmea_checksum,
) -> str:
    """
    Create a full NMEA message with checksum.

    Args:
        message (str): The NMEA message string.
        checksum_func (callable, optional): The function to compute the checksum. Defaults to compute_nmea_checksum.

    Returns:
        str: The full NMEA message with checksum.
    """
    checksum = checksum_func(message)
    return f"${message}*{checksum}\r\n"
    # return "${}\*{}\\r\\n".format(message, checksum)


def create_waypoint_message(
    latitude_minutes,
    latitude_hemisphere,
    longitude_minutes,
    longitude_hemisphere,
    number,
):
    """
    Create an NMEA waypoint message.

    Args:
        latitude_minutes (str): The latitude in degrees and minutes format.
        latitude_hemisphere (str): The latitude hemisphere ('N' or 'S').
        longitude_minutes (str): The longitude in degrees and minutes format.
        longitude_hemisphere (str): The longitude hemisphere ('E' or 'W').
        number (int): The waypoint number.

    Returns:
        str: The NMEA waypoint message.
    """
    return f"OIWPL,{latitude_minutes},{latitude_hemisphere},{longitude_minutes},{longitude_hemisphere},{number}"
    # return "OIWPL,{},{},".format(latitude_minutes, latitude_hemisphere) + "{},{},".format(longitude_minutes, longitude_hemisphere) + str(number)


def create_waypoint_messages_df(filename, erp_filename):
    """
    Create a DataFrame with proper waypoint messages to be sent to the surveyor from a CSV file.

    Args:
        filename: the name of the CSV file containing waypoint data
        erp_filename: the name of the CSV file containing emergency recovery point

    Returns:
        pandas.DataFrame: a DataFrame containing NMEA waypoint messages
    """
    try:
        # Load the CSV into a pandas DataFrame
        df = pd.read_csv(filename)
    except Exception as e:
        HELPER_LOGGER.error(f"Error loading waypoint CSV file: {e}")
        return pd.DataFrame()

    if df.empty:
        HELPER_LOGGER.error("The waypoints DataFrame is empty")
        return df

    try:
        # Load the ERP CSV into a pandas DataFrame
        erp_df = pd.read_csv(erp_filename)

        # Only take the first row for the ERP as pandas DataFrame
        erp_df = erp_df.iloc[0:1]

    except Exception as e:
        HELPER_LOGGER.error(f"Error loading ERP CSV file: {e}")
        return pd.DataFrame()

    # Append ERP to the beginning of the DataFrame
    df = pd.concat([erp_df, df], ignore_index=True)

    # Convert latitude and longitude to desired format
    df["latitude_minutes"] = df["latitude"].apply(
        lambda x: convert_lat_to_nmea_degrees_minutes(float(x))
    )
    df["longitude_minutes"] = df["longitude"].apply(
        lambda x: convert_lon_to_nmea_degrees_minutes(float(x))
    )

    # Get hemisphere for latitude and longitude
    df["latitude_hemisphere"] = df["latitude"].apply(get_hemisphere_lat)
    df["longitude_hemisphere"] = df["longitude"].apply(get_hemisphere_lon)

    # Adjust the nmea_waypoints column for the emergency recovery point and the sequential waypoints
    df["nmea_waypoints"] = df.apply(
        lambda row: create_waypoint_message(
            row["latitude_minutes"],
            row["latitude_hemisphere"],
            row["longitude_minutes"],
            row["longitude_hemisphere"],
            row.name,
        ),
        axis=1,
    )

    # Create full NMEA message with checksum
    df["nmea_message"] = df["nmea_waypoints"].apply(
        lambda waypoint: create_nmea_message(waypoint)
    )
    return df


def create_waypoint_messages_df_from_list(waypoints, erp):
    """
    Create a DataFrame with waypoint messages from lists of coordinates.

    Args:
        waypoints: a list of (latitude, longitude) tuples
        erp: a single (latitude, longitude) tuple
    Returns:
        pandas.DataFrame: a pandas DataFrame containing NMEA waypoint messages
    """
    if not waypoints:
        HELPER_LOGGER.error("Waypoints list is empty.")
        return pd.DataFrame()

    # Ensure erp is a single tuple, wrap into list of one row
    if not isinstance(erp, (list, tuple)) or len(erp) != 2:
        HELPER_LOGGER.error(
            "ERP must be a (latitude, longitude) tuple, got %r", erp
        )
        return pd.DataFrame()

    try:
        waypoints_df = pd.DataFrame(
            waypoints, columns=["latitude", "longitude"]
        )
        erp_df = pd.DataFrame([erp], columns=["latitude", "longitude"])
    except Exception as e:
        HELPER_LOGGER.error("Error creating DataFrames from inputs: %s", e)
        return pd.DataFrame()

    if waypoints_df.empty:
        HELPER_LOGGER.error("The waypoints DataFrame is empty.")
        return pd.DataFrame()
    if erp_df.empty:
        HELPER_LOGGER.error("The ERP DataFrame is empty.")
        return pd.DataFrame()

    # Append ERP to the beginning of the DataFrame
    df = pd.concat([erp_df, waypoints_df], ignore_index=True)

    # Convert latitude and longitude to desired format
    df["latitude_minutes"] = df["latitude"].apply(
        lambda x: convert_lat_to_nmea_degrees_minutes(float(x))
    )
    df["longitude_minutes"] = df["longitude"].apply(
        lambda x: convert_lon_to_nmea_degrees_minutes(float(x))
    )

    # Get hemisphere for latitude and longitude
    df["latitude_hemisphere"] = df["latitude"].apply(get_hemisphere_lat)
    df["longitude_hemisphere"] = df["longitude"].apply(get_hemisphere_lon)

    # Adjust the nmea_waypoints column for the emergency recovery point and the sequential waypoints
    df["nmea_waypoints"] = df.apply(
        lambda row: create_waypoint_message(
            row["latitude_minutes"],
            row["latitude_hemisphere"],
            row["longitude_minutes"],
            row["longitude_hemisphere"],
            row.name,
        ),
        axis=1,
    )

    # Create full NMEA message with checksum
    df["nmea_message"] = df["nmea_waypoints"].apply(
        lambda waypoint: create_nmea_message(waypoint)
    )

    return df


def create_waypoint_mission(df, throttle=20):
    """
    Generate a waypoint mission from a DataFrame.

    Args:
        df (pandas.DataFrame): The DataFrame containing the waypoint data. It must contain the column 'nmea_message'
        obtained by having waypoints in CSV files and passing them to create_waypoint_messages_df function or having a list of coordinates
        and passing them to create_waypoint_messages_df_from_list function.
        throttle (int, optional): The throttle value for the PSEAR command. Defaults to 20.
        pause_time (int, optional): The pause time value for the PSEAR command. Defaults to 0.

    Returns:
        str: The waypoint mission string.
    """
    # Start with the PSEAR command
    psear_cmd = "PSEAR,0,000,{},0,000".format(throttle)
    psear_cmd_with_checksum = (
        f"{psear_cmd}*{compute_nmea_checksum(psear_cmd)}\r\n"
    )

    # Generate OIWPL commands from the DataFrame
    oiwpl_cmds = df["nmea_message"].tolist()

    # Concatenate all the commands to form the mission
    mission = psear_cmd_with_checksum + "".join(oiwpl_cmds)

    return mission
