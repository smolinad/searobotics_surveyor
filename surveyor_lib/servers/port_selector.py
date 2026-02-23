import subprocess
from typing import List, Optional

attached_line = "now attached to"


def get_dmesg_ttyusb_lines() -> List[str]:
    """Return dmesg lines mentioning ttyUSB, newest first."""
    try:
        result = subprocess.run(
            ["dmesg"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running dmesg: {e}")
        return []

    # Filter lines containing 'ttyUSB'
    lines = [line for line in result.stdout.splitlines() if "ttyUSB" in line]

    # Return lines from last to first (newest first)
    return lines[::-1]


def get_serial_port(keyword: str) -> Optional[str]:
    """
    Get the serial port from dmesg output that contains the specified keyword.

    Args:
        keyword (str): The keyword to search for in the dmesg output.

    Returns:
        str | None: The serial port path (e.g. '/dev/ttyUSB0') if found, otherwise None.
    """
    print("Searching for serial port in dmesg output...")
    lines = get_dmesg_ttyusb_lines()
    if not lines:
        print("No ttyUSB lines found in dmesg output.")
        return None

    for line in lines:
        if keyword.lower() in line.lower() and attached_line in line:
            # Extract the serial port from the line
            for part in line.split():
                if part.startswith("ttyUSB"):
                    serial_port = f"/dev/{part}"
                    print(f"Found serial port: {serial_port}")
                    return serial_port

    print(f"No serial port found with keyword '{keyword}' in dmesg output.")
    return None


if __name__ == "__main__":
    for line in get_dmesg_ttyusb_lines():
        print(line)
    port = get_serial_port(
        "cp210x"
    )  # Example usage, searching for cp210x devices
    print(f"Selected port: {port}")  # May be 'None' if not found
