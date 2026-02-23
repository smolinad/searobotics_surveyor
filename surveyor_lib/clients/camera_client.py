import argparse
import sys
import threading
import time

import cv2

from .base_client import BaseClient


class CameraClient(BaseClient):
    """
    CameraClient class represents a client to receive video stream from a Camera server.

    Args:
        server_ip (str): IP address of the server (default is "192.168.0.20").
        server_port (str): Port number of the server (default is "5001").
    """

    def __init__(
        self,
        server_ip="192.168.0.20",
        server_port="5001",
    ):
        """
        Initializes a CameraClient object.

        Attributes:
            server_ip (str): IP address of the server.
            server_port (str): Port number of the server.
            server_url (str): URL of the video feed provided by the server.
            cap (cv2.VideoCapture): VideoCapture object to capture frames from the server.
        Private Attributes, do not access or touch during execution!
            _current_frame (numpy.ndarray): The current frame captured from the video stream.
            _frame_thread (threading.Thread): Thread that continuously updates the current frame.
        """
        super().__init__(server_ip, server_port)
        self.server_url += "/video_feed"
        self.cap = cv2.VideoCapture(self.server_url)

        self._current_frame = None

        if self.cap.isOpened():
            self._frame_thread = threading.Thread(target=self._image_updater)
            self._frame_thread.daemon = True  # Daemonize the thread so it will exit when the main program exits
            self._frame_thread.start()
            time.sleep(0.1)  # Give some time to update current images
            print("Camera connected. Receiving stream!")
        else:
            print(
                f"""Error: Unable to open video stream.
                      Check your camera configuration.
                      Ensure picamera_server.py or picamera_server_flask.py are running on the Pi.
                      You should see the video at {self.server_url}"""
            )

    def get_data(self):
        """
        Retrieves the most recent frame from the video stream.

        Returns:
            tuple: A tuple containing a boolean value indicating whether the frame is read successfully
                   and the frame itself.
        """
        return (
            self._current_frame is not None,
            self._current_frame,
        )

    def _image_updater(self):
        """
        Continuously updates the current frame from the video stream.
        """
        while True:
            ret, frame = self.cap.read()
            if ret:
                self._current_frame = frame
            time.sleep(
                0.015
            )  # Prevents excessive CPU usage by the thread (~66 FPS)


if __name__ == "__main__":
    # Create an ArgumentParser object
    print(f"Run {sys.argv[0]} -h  for help")
    parser = argparse.ArgumentParser(description="Client script for PiCamera.")

    # Add arguments
    parser.add_argument(
        "--host",
        type=str,
        default="192.168.0.20",
        help="IP address of the host (default: 192.168.0.20).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5001,
        help="Port number (default: 5001).",
    )

    # Parse the command line arguments
    args = vars(parser.parse_args())

    camera_client = CameraClient(args["host"], int(args["port"]))

    # Loop to continuously retrieve and display frames from the video stream
    while True:
        # Read a frame from the video stream
        ret, frame = camera_client.get_data()
        if ret:
            # Display the frame
            cv2.imshow("Video Stream", frame)
        else:
            print("Error: Unable to read frame from video stream")

        # Check for key press to exit
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Release the video stream and close the OpenCV windows
    cv2.destroyAllWindows()
