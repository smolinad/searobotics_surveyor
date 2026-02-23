import sys
import os
import time


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from surveyor_lib import Surveyor
from surveyor_lib.helpers.grid_helper import GridMapper

HOST = "localhost"
PORT = 8003


def main():
    import math
    import argparse

    parser = argparse.ArgumentParser(description="Run Grid Navigation Test")

    parser.add_argument(
        "-n", "--size", type=int, default=4, help="Grid size (NxN)"
    )
    args = parser.parse_args()

    top_left = (25.758326, -80.373864)
    bottom_right = (25.757905, -80.373446)

    fountains = [
        (25.758008, -80.373836),
        (25.758075, -80.373650),
        (25.758046, -80.373424),
        (25.757934, -80.373405),
    ]

    n_rows = args.size
    n_cols = args.size
    mapper = GridMapper(top_left, bottom_right, n_rows, n_cols)

    h_m, w_m = mapper.get_grid_dimensions_meters()
    cell_h = h_m / n_rows
    cell_w = w_m / n_cols

    print(f"\nGrid Dimensions: {h_m:.1f}m x {w_m:.1f}m")
    print(f"Cell Size: {cell_h:.2f}m x {cell_w:.2f}m")

    min_dim = 3.0
    if cell_h < min_dim or cell_w < min_dim:
        print(
            f"\nERROR: Grid size N={args.size} results in cells too small for the boat!"
        )
        return

    from geopy.distance import geodesic
    import numpy as np

    def get_bearing(p1, p2):
        lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
        lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
        d_lon = lon2 - lon1
        x = math.sin(d_lon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - (
            math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
        )
        return math.atan2(x, y)

    def offset_point(lat, lon, brng_rad, dist_m):
        d_lat = (dist_m * math.cos(brng_rad)) / 111132
        d_lon = (dist_m * math.sin(brng_rad)) / (
            111132 * math.cos(math.radians(lat))
        )
        return (lat + d_lat, lon + d_lon)

    def apply_obstacle_avoidance(
        waypoints, fountains, mapper, logical_path, safe_radius=3.0
    ):
        """
        Simplified obstacle avoidance: intersects path segments with fountains and adds a single
        detour waypoint around the obstacle. Non-recursive.
        """
        if not waypoints:
            return []

        final_path = [waypoints[0]]

        for i in range(len(waypoints) - 1):
            p_start = waypoints[i]
            p_end = waypoints[i + 1]

            collision_fountain = None
            min_dist_to_segment = float("inf")

            seg_len = geodesic(p_start, p_end).meters
            if seg_len == 0:
                continue

            steps = int(seg_len * 2) + 2

            for f in fountains:
                for s in range(1, steps):
                    ratio = s / steps
                    interp_lat = p_start[0] + (p_end[0] - p_start[0]) * ratio
                    interp_lon = p_start[1] + (p_end[1] - p_start[1]) * ratio
                    p_curr = (interp_lat, interp_lon)

                    dist = geodesic(p_curr, f).meters
                    if dist < safe_radius:
                        if dist < min_dist_to_segment:
                            min_dist_to_segment = dist
                            collision_fountain = f

                            collision_point = p_curr

            if collision_fountain:
                f = collision_fountain

                path_bearing = get_bearing(p_start, p_end)

                detour_bearing = path_bearing + (math.pi / 2)
                detour_dist = safe_radius + 1.5

                brng_path_to_f = get_bearing(collision_point, f)

                escape_bearing = brng_path_to_f + math.pi

                p_detour = offset_point(
                    f[0], f[1], escape_bearing, detour_dist
                )

                if not mapper.is_within_bounds(p_detour[0], p_detour[1]):
                    pass

                final_path.append(p_detour)
                print(
                    f"  Start->End intersects fountain. Added detour at {p_detour}"
                )

            final_path.append(p_end)

        return final_path

    from collections import deque

    def is_blocked(r, c, fountains, mapper, margin=2.0):
        center = mapper.get_cell_center(r, c)
        safe_dist = 5.0 + margin

        for f in fountains:
            d = geodesic(center, f).meters
            if d < safe_dist:
                return True
        return False

    def find_path_bfs(start, goal, blocked, rows, cols):
        if start == goal:
            return [start]

        queue = deque([[start]])
        visited = {start}

        if start in blocked or goal in blocked:
            return None

        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == goal:
                return path

            r, c = node
            neighbors = [
                (r + 1, c),
                (r - 1, c),
                (r, c + 1),
                (r, c - 1),
                (r + 1, c + 1),
                (r - 1, c - 1),
                (r + 1, c - 1),
                (r - 1, c + 1),
            ]

            for nr, nc in neighbors:
                if 0 <= nr < rows and 0 <= nc < cols:
                    if (nr, nc) not in visited and (nr, nc) not in blocked:
                        visited.add((nr, nc))
                        new_path = list(path)
                        new_path.append((nr, nc))
                        queue.append(new_path)
        return None

    blocked_cells = set()
    print("\nChecking Grid for Blocked Cells (Logging only)...")
    for r in range(n_rows):
        for c in range(n_cols):
            if is_blocked(r, c, fountains, mapper):
                print(f"  Warning: Cell ({r}, {c}) contains a fountain.")
    print(
        f"Proceeding with empty blocked_cells to force intersection testing."
    )

    start_node = (0, 0)
    end_node = (n_rows - 1, n_cols - 1)

    print(f"Planning path from {start_node} to {end_node}...")
    logical_path = find_path_bfs(
        start_node, end_node, blocked_cells, n_rows, n_cols
    )

    if not logical_path:
        print(f"CRITICAL ERROR: No valid path found from start to end!")
        return

    print(f"\nGenerated Safe Grid Path: {len(logical_path)} steps")
    print(f"Path: {logical_path}")

    raw_gps_waypoints = mapper.path_to_gps(logical_path)

    print("Checking path for fountain collisions...")
    final_waypoints = apply_obstacle_avoidance(
        raw_gps_waypoints, fountains, mapper, logical_path, safe_radius=5.0
    )

    print(
        f"Optimized Path has {len(final_waypoints)} waypoints (Original: {len(raw_gps_waypoints)})"
    )

    import json

    config = {
        "top_left": top_left,
        "bottom_right": bottom_right,
        "rows": n_rows,
        "cols": n_cols,
        "waypoints": final_waypoints,
        "fountains": fountains,
        "obstacle_radius": 3.0,
        "blocked_cells": [],
    }

    config_path = os.path.join(os.path.dirname(__file__), "grid_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f)
    print(f"\nSaved config to {config_path} for visualizers.")

    h_m, w_m = mapper.get_grid_dimensions_meters()
    print(f"Grid Area Defined: {h_m:.1f}m High x {w_m:.1f}m Wide")

    waypoints = final_waypoints

    print("Real World Waypoints:")
    for i, wp in enumerate(waypoints):
        print(f"  {i}: {wp}")

    print("Connecting to Simulator...")
    boat = Surveyor(host=HOST, port=PORT, sensors_to_use=[], record=False)

    with boat:
        print("Connected!")

        import math

        p0 = waypoints[0]

        if len(waypoints) > 1:
            p1 = waypoints[1]
        else:
            p1 = p0

        offset_dist = 8.0

        deg_per_m_lon = 1.0 / (111132 * math.cos(math.radians(p0[0])))

        start_lat = p0[0]
        start_lon = p0[1] - (offset_dist * deg_per_m_lon)

        start_heading = get_bearing((start_lat, start_lon), p0)
        start_heading_deg = math.degrees(start_heading)
        if start_heading_deg < 0:
            start_heading_deg += 360

        print(
            f"\nTeleporting to Runway Start: ({start_lat:.6f}, {start_lon:.6f}) Facing {start_heading_deg:.1f}°"
        )
        print(f"  (This is {offset_dist}m West of Waypoint 0 Center)")

        boat.send(f"PSEAC,S,{start_lat},{start_lon},{start_heading_deg},")
        time.sleep(3)

        erp = waypoints[0]
        print(f"\nUploading Full Mission... (ERP aligned to Start: {erp})")

        boat.send_waypoints(waypoints, erp, throttle=45)

        print("Starting Autopilot...")
        boat.set_waypoint_mode()

        print("Waiting for Waypoint Mode...")

        for _ in range(50):
            state = boat.get_state()
            if state.get("Control Mode") == "Waypoint":
                print(
                    f"{GREEN}Simulator in Waypoint Mode.{RESET if 'RESET' in locals() else ''}"
                )
                break
            time.sleep(0.1)

        try:
            while True:
                state = boat.get_state()
                mode = state.get("Control Mode", "Unknown")

                if mode == "Standby":
                    print("Mission Complete!")
                    break
                elif mode != "Waypoint":
                    print(f"Mode changed to {mode} unexpectedly.")

                time.sleep(1)
        except KeyboardInterrupt:
            boat.set_standby_mode()


if __name__ == "__main__":
    main()
