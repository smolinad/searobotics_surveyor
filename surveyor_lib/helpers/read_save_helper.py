import csv
import datetime
import os
import time
from typing import Any, Dict, Iterable, Mapping, Sequence

import pandas as pd

from .logger import HELPER_LOGGER

DEFAULT_OUT_DIR_PATH = os.path.abspath(
    os.path.join(__file__, "../../../../out/")
)


def append_to_csv(
    data: Iterable[Any],
    cols: Iterable[str] | Sequence[str] | None = None,
    post_fix: str = "",
    dir_path: str | None = None,
) -> None:
    """
    Append data to a CSV file with a specific date in the filename.

    Args:
        data: Iterable of values to be appended to the CSV file (one row).
        cols: Column names for the CSV file. Defaults to ["latitude", "longitude"].
        post_fix: Suffix to be added to the filename. Defaults to "".
        dir_path: Directory path where the CSV file will be stored.
            If None, uses the default directory.
    """
    cols = list(cols) if cols is not None else ["latitude", "longitude"]
    dir_path = dir_path or DEFAULT_OUT_DIR_PATH

    today_date = datetime.date.today().strftime("%Y%m%d")

    HELPER_LOGGER.debug(f"out folder at {dir_path}")
    os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, f"{today_date}{post_fix}.csv")

    # Create file and write header if it doesn't exist
    if not os.path.isfile(file_path):
        with open(file_path, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(cols)

    # Append the row
    with open(file_path, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(list(data))


def save(
    data: Dict[str, Any] | None,
    post_fix: str = "",
    dir_path: str | None = None,
) -> None:
    """
    Process GPS coordinates and Exo2 sensor data, append them to a CSV file after validation.

    Parameters:
        data: Dictionary containing GPS coordinates and Exo2 sensor data.
        post_fix: A suffix to append to the CSV file name. Default is "".
        dir_path: Directory path where the CSV file will be stored. If None, uses the default directory.
    """
    if data:
        append_to_csv(
            data.values(), data.keys(), post_fix=post_fix, dir_path=dir_path
        )
    else:
        HELPER_LOGGER.error("No values to be appended to the CSV")


def process_gga_and_save_data(
    surveyor_connection: Any,
    data_keys: Sequence[str] | None = ("state", "exo2"),
    post_fix: str = "",
    delay: float = 1.0,
    dir_path: str | None = None,
) -> Mapping[str, Any]:
    """
    Retrieve and process data from Surveyor, then append it to a CSV file.

    Args:
        surveyor_connection: The Surveyor connection object providing access to data.
        data_keys: List of keys to retrieve specific data from the surveyor connection.
                   Only 'state' and 'exo2' are supported. Defaults to ("state", "exo2").
        post_fix: A suffix to append to the CSV file name. Default is "".
        delay: Minimum time delay (in seconds) between consecutive saves to prevent duplicates.
        dir_path: Directory path where the CSV file will be stored. If None, uses the default directory.

    Returns:
        surveyor_data: Dictionary with the data acquired by the boat (see Surveyor.get_data).
    """
    allowed_keys = {"state", "exo2"}
    if data_keys is not None:
        filtered_keys = [key for key in data_keys if key in allowed_keys]
    else:
        filtered_keys = list(allowed_keys)

    if not filtered_keys:
        raise ValueError(
            "No valid data keys provided. Allowed: 'state', 'exo2'."
        )

    surveyor_data = surveyor_connection.get_data(filtered_keys)

    # Enforce minimum delay between saves
    elapsed = time.time() - process_gga_and_save_data.last_save_time
    if elapsed < delay:
        time.sleep(delay - elapsed)

    process_gga_and_save_data.last_save_time = time.time()

    save(data=surveyor_data, post_fix=post_fix, dir_path=dir_path)
    return surveyor_data


process_gga_and_save_data.last_save_time = time.time()


def read_csv_into_tuples(filepath: str) -> list[tuple[Any, Any]]:
    """
    Reads a CSV file into a list of (latitude, longitude) tuples.

    Parameters:
        filepath: The path to the CSV file.

    Returns:
        list of tuples: Each tuple represents a row from the CSV file.
    """
    df = pd.read_csv(filepath)

    try:
        df = df[["Latitude", "Longitude"]]
    except KeyError:
        try:
            df = df[["latitude", "longitude"]]
        except KeyError:
            HELPER_LOGGER.warning(
                "Assuming first column to be Latitude and second to be Longitude"
            )
            df = df.iloc[:, :2]

    return [tuple(row) for row in df.values]
