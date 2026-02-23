import argparse
import io
import sys

import cv2
import picamera2
from flask import Flask, Response
from PIL import Image

app = Flask(__name__)


def get_video_source_fnc(
    source: str = "picamera", width: int = 640, height: int = 480
):
    """
    Returns a function to read frames from a video source.

    Args:
        source (str): Type of video source. 'picamera' or 'usb'.
        width (int): Width of the video frames.
        height (int): Height of the video frames.

    Returns:
        callable: A function `read_frame() -> tuple[bool, np.ndarray]`.
    """

    if source == "picamera":
        try:
            video_capture = picamera2.Picamera2()
            camera_config = video_capture.create_preview_configuration(
                main={
                    "size": (width, height),
                    "format": "BGR888",
                }
            )
            video_capture.configure(camera_config)
            video_capture.start()
            print("PiCamera found")

            def read_frame():
                return True, video_capture.capture_array()

            return read_frame

        except Exception as e:
            print(f"PiCamera not found or failed to initialize: {e}")
            sys.exit(1)

    elif source == "usb":
        for i in range(10):
            video_capture = cv2.VideoCapture(i)
            if not video_capture.isOpened():
                continue

            print(f"Webcam found at index {i}")
            video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            def read_frame():
                success, frame = video_capture.read()
                if not success:
                    return False, None
                # Convert BGR (OpenCV) to RGB for PIL
                return True, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            return read_frame

        print("No webcam found")
        sys.exit(1)
    else:
        print(f"Unsupported video source: {source}")
        sys.exit(1)


def generate_frames():
    """
    Generates video frames from the selected video source.

    Yields:
        bytes: JPEG-encoded image frames.
    """

    while True:
        success, frame = video_capture_src()

        if not success or frame is None:
            print("Image not found, closing video capture...")
            break

        print("Sending image...", end="\r")

        image = Image.fromarray(frame)
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format="JPEG")
        img_bytes = img_byte_arr.getvalue()

        yield (
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            + img_bytes
            + b"\r\n"
        )


@app.route("/")
def index():
    """Displays a message indicating that the stream is online."""
    return "Camera stream online!"


@app.route("/video_feed")
def video_feed():
    """
    Route for accessing the video feed.

    Returns:
        Response: Multipart MJPEG stream.
    """
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


def main(host: str, port: int):
    # threaded=True is useful when a client holds the /video_feed stream
    app.run(debug=False, host=host, port=port, threaded=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Camera Server Script using Flask"
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
        default=5001,
        help="Port number (default: 5001).",
    )
    parser.add_argument(
        "--camera_source_type",
        type=str,
        default="picamera",
        help="Camera source type (default: picamera, options: picamera, usb).",
    )
    parser.add_argument(
        "--image_width",
        type=int,
        default=800,
        help="Image width (default: 800).",
    )
    parser.add_argument(
        "--image_height",
        type=int,
        default=600,
        help="Image height (default: 600).",
    )

    args = vars(parser.parse_args())

    # Make this global so generate_frames() can call it
    video_capture_src = get_video_source_fnc(
        args["camera_source_type"],
        args["image_width"],
        args["image_height"],
    )

    main(args["host"], args["port"])
