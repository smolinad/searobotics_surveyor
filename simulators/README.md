# Boat Simulator

This directory contains a simulator for the Sea Robotics Surveyor ASV. It mocks the hardware server, allowing you to run and test your application code without the physical boat.

## Files
- `boat_simulator.py`: The mock server (simulates the boat hardware).
- `test_simulation.py`: A client script to verify the connection and boat movement.

## Usage with `uv`

You can run the full simulation stack using **three terminal windows**.

### Terminal 1: Start the Simulator
Run the simulator server. It listens on `localhost:8003`.
```bash
uv run simulators/boat_simulator.py
```

### Terminal 2: Start a Visualizer (Optional)
You can verify the boat's movement using one of the provided visualizers.

**Option A: GUI Plotter (Matplotlib)**
Opens a window showing the boat's path on a 2D map.
```bash
uv run visualizers/gui_plot.py
```

**Option B: Terminal Visualizer (Curses)**
Runs a text-based dashboard in the terminal. Ideal for headless environments.
```bash
uv run visualizers/term_viz.py
```

### Terminal 3: Run Your Code
Run your application code or the provided test script to control the boat.
```bash
uv run simulators/test_simulation.py
```

### Grid Navigation Test (New)
To test the autonomous Grid Navigation system (converting Grid cells to GPS waypoints):
```bash
uv run simulators/test_grid_nav.py
```
This script will:
1. Define a "Lake" area and a logical grid (4x4).
2. Generate GPS waypoints for a zig-zag path.
3. Automatically update `grid_config.json` so the Visualizers know where to look.
4. Send the mission to the simulator.

**Note**: For best results, run the **GUI Plotter** (`visualizers/gui_plot.py`) *before* running this test. It will automatically reload to show the new grid and path.
