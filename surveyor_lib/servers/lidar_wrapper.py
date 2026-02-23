import atexit
import re
import signal
import subprocess
import threading
from pathlib import Path


class LidarWrapper:
    def __init__(self, serial_port="/dev/ttyUSB0", baudrate="1000000"):
        self.serial_port = serial_port
        self.baudrate = baudrate
        script_dir = Path(__file__).parent.resolve()
        self.exec_path = script_dir / "ultra_simple"
        self.vector = [0] * 360
        self._thread = None
        self._proc = None
        self._running = False

        atexit.register(self.stop)

    def _update_loop(self):
        cmd = [
            self.exec_path,
            "--channel",
            "--serial",
            self.serial_port,
            self.baudrate,
        ]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

        for line in self._proc.stdout:
            # print(f"Processing line: {line}")
            if not self._running:
                break
            match = re.search(r"theta:\s*([\d.]+)\s*Dist:\s*([\d.]+)", line)
            if match:
                theta = int(float(match.group(1))) % 360
                dist = float(match.group(2)) / 1000  # Convert to m
                self.vector[theta] = dist

        self._proc.stdout.close()

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(
                target=self._update_loop, daemon=True
            )
            self._thread.start()

    def stop(self):
        print("Stopping LidarWrapper...")
        self._running = False
        if self._proc and self._proc.poll() is None:  # still running
            self._proc.send_signal(signal.SIGINT)
            try:
                print("Terminating process...")
                self._proc.terminate()  # send SIGTERM
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Process did not terminate in time, killing...")
                self._proc.kill()  # force kill if not exiting
                self._proc.wait()
        if self._thread:
            self._thread.join(timeout=1)
        print("LidarWrapper Stopped...")

    def get_scan_data(self):
        return self.vector.copy()


if __name__ == "__main__":
    import matplotlib.animation as animation
    import matplotlib.pyplot as plt
    import numpy as np

    # Initialize the Lidar
    lidar = LidarWrapper(serial_port="/dev/ttyUSB0", baudrate="1000000")
    lidar.start()  # Assume this starts the subprocess that fills the vector

    fig = plt.figure()
    ax = plt.subplot(111, polar=True)
    scatter = ax.scatter([], [], s=10)

    ax.set_ylim(0, 4)  # Adjust max range based on your lidar

    def update(_):
        data = lidar.get_scan_data()
        # print(f"Data received: {data[:10]}...")
        theta = np.deg2rad(np.arange(360))
        r = np.array(data)
        scatter.set_offsets(np.column_stack((theta, r)))
        return (scatter,)

    ani = animation.FuncAnimation(fig, update, blit=True, interval=100)

    plt.title("Live 360° Lidar Scan")
    try:
        plt.show()
    except KeyboardInterrupt:
        print("Exiting...")
