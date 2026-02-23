import sys
import os
import curses
import time
import math
import threading

# Add root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from surveyor_lib import Surveyor

# Configuration
HOST = '127.0.0.1' 
PORT = 8003

class CursesVisualizer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.running = True
        self.state = {}
        self.path = []
        self.logs = []
        self.log_lock = threading.Lock()
        
        # Curses Setup
        curses.curs_set(0)
        self.stdscr.nodelay(1)
        self.stdscr.timeout(100)
        
        # Connect to Boat
        try:
            self.boat = Surveyor(host=HOST, port=PORT, sensors_to_use=[], record=False)
            self.boat.__enter__()
            self.log("Connected to Boat!")
        except Exception as e:
            self.log(f"Connection Failed: {e}")
            self.boat = None
            
        # Start Update Thread
        if self.boat:
            self.thread = threading.Thread(target=self.update_loop)
            self.thread.daemon = True
            self.thread.start()
            
    def log(self, msg):
        with self.log_lock:
            self.logs.append(msg)
            if len(self.logs) > 10:
                self.logs.pop(0)


    def update_loop(self):
        while self.running:
            try:
                self.state = self.boat.get_state()
                lat = self.state.get('Latitude', 0.0)
                lon = self.state.get('Longitude', 0.0)
                
                # Store path if valid
                if lat != 0.0 and lon != 0.0:
                    self.path.append((lat, lon))
            except Exception as e:
                self.log(f"Error getting state: {e}")
            time.sleep(0.1)

    def draw(self):
        self.stdscr.clear()
        h, w = self.stdscr.getmaxyx()
        
        # Split screen: Left (Telemetry 30 chars), Right (Map)
        split_col = 35
        
        # --- LEFT PANEL: TELEMETRY ---
        self.stdscr.addstr(0, 0, "DATA", curses.A_BOLD)
        self.stdscr.addstr(1, 0, "-" * (split_col-2))
        
        state = self.state
        row = 2
        self.stdscr.addstr(row, 0, f"Mode: {state.get('Control Mode', 'Unk')}"); row += 1
        self.stdscr.addstr(row, 0, f"Thru: {state.get('Thrust (% Thrust)', 0)}%"); row += 1
        self.stdscr.addstr(row, 0, f"Diff: {state.get('Thrust difference (% Thrust)', 0)}%"); row += 1
        row += 1
        self.stdscr.addstr(row, 0, f"Head: {state.get('Heading (degrees Magnetic)', 0):.1f}"); row += 1
        self.stdscr.addstr(row, 0, f"Lat:  {state.get('Latitude', 0):.6f}"); row += 1
        self.stdscr.addstr(row, 0, f"Lon:  {state.get('Longitude', 0):.6f}"); row += 1
        
        row += 2
        self.stdscr.addstr(row, 0, "-" * (split_col-2)); row += 1
        self.stdscr.addstr(row, 0, "LOGS:", curses.A_BOLD); row += 1
        
        with self.log_lock:
            for log in self.logs:
                if row < h - 1:
                    # Truncate log to fit
                    self.stdscr.addstr(row, 0, f"> {log[:split_col-4]}")
                    row += 1

        # --- RIGHT PANEL: ASCII MAP (Stable Scale) ---
        map_w = w - split_col - 1
        map_h = h - 2
        start_x = split_col
        
        self.stdscr.addstr(0, start_x, "LIVE MAP (Minimum 50m Scale)", curses.A_BOLD)
        
        if len(self.path) > 0:
            lats = [p[0] for p in self.path]
            lons = [p[1] for p in self.path]
            
            # 1. Determine bounding box of path
            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)
            
            # center of path
            c_lat = (min_lat + max_lat) / 2.0
            c_lon = (min_lon + max_lon) / 2.0
            
            # 2. Enforce minimum scale (approx 50 meters)
            # 1 deg lat ~ 111,000m -> 50m ~ 0.00045 deg
            MIN_DEG = 0.00045
            lat_rng = max(max_lat - min_lat, MIN_DEG)
            lon_rng = max(max_lon - min_lon, MIN_DEG)
            
            # 3. Apply Aspect Ratio Correction for Terminal
            # We want uniform scale in METERS.
            # 1 deg Lat ~= 111,132 m
            # 1 deg Lon ~= 111,132 * cos(lat) m
            
            meters_per_deg_lat = 111132
            meters_per_deg_lon = 111132 * math.cos(math.radians(c_lat))
            
            # Convert range to meters
            rng_m_lat = lat_rng * meters_per_deg_lat
            rng_m_lon = lon_rng * meters_per_deg_lon
            
            # Screen aspect (approx 2.0 because chars are tall)
            # We want: (map_w_chars * char_w_m) / (map_h_chars * char_h_m) = rng_m_lon / rng_m_lat
            CHAR_ASPECT = 0.5 # Width / Height of a character
            
            # To maintain aspect, we must correct for the char shape.
            # We need: scale_h_visual = scale_w_visual
            # visual_height = chars_h * 1
            # visual_width = chars_w * CHAR_ASPECT
            
            # We need standard scaling:
            # chars_h = height_m * S
            # chars_w = width_m * S * (1/CHAR_ASPECT)  <- because chars are narrow, we need MORE of them for same width
            
            # So:
            # scale_h = S
            # scale_w = S / CHAR_ASPECT
            
            # derived S based on fitting:
            S_h = map_h / rng_m_lat
            S_w = map_w / rng_m_lon * CHAR_ASPECT
            
            S = min(S_h, S_w) # Fit inside
            
            # Back-calculate ranges to center
            visible_m_lat = map_h / S
            visible_m_lon = map_w * CHAR_ASPECT / S
            
            lat_rng = visible_m_lat / meters_per_deg_lat
            lon_rng = visible_m_lon / meters_per_deg_lon
                
            # Re-calculate bounds centered
            view_min_lat = c_lat - lat_rng / 2.0
            view_max_lat = c_lat + lat_rng / 2.0
            view_min_lon = c_lon - lon_rng / 2.0
            view_max_lon = c_lon + lon_rng / 2.0
            
            # Draw Path
            for lat, lon in self.path:
                # Normalize 0..1 relative to VIEW bounds
                r_lat = (lat - view_min_lat) / lat_rng
                r_lon = (lon - view_min_lon) / lon_rng
                
                if 0 <= r_lat <= 1 and 0 <= r_lon <= 1:
                    # Invert Y (0 at top)
                    py = int((1.0 - r_lat) * (map_h - 1))
                    px = int(r_lon * (map_w - 1))
                    
                    try:
                        self.stdscr.addch(py + 1, start_x + px, '.')
                    except:
                        pass
            
            # Draw Boat
            if self.path:
                last_lat = self.path[-1][0]
                last_lon = self.path[-1][1]
                
                r_lat = (last_lat - view_min_lat) / lat_rng
                r_lon = (last_lon - view_min_lon) / lon_rng
                
                if 0 <= r_lat <= 1 and 0 <= r_lon <= 1:
                    by = int((1.0 - r_lat) * (map_h - 1))
                    bx = int(r_lon * (map_w - 1))
                    
                    heading = state.get('Heading (degrees Magnetic)', 0)
                    dirs = ['^', '>', 'v', '<']
                    h_idx = int((heading + 45) / 90) % 4
                    boat_char = dirs[h_idx]
                    
                    try:
                        self.stdscr.addch(by + 1, start_x + bx, boat_char, curses.A_BOLD | curses.A_REVERSE)
                    except:
                        pass
        else:
            self.stdscr.addstr(map_h // 2, start_x + map_w // 2 - 5, "No GPS Data")

        # Vertical Separator
        for y in range(h):
            self.stdscr.addch(y, split_col - 1, '|')

        self.stdscr.refresh()


    def run(self):
        try:
            while self.running:
                self.draw()
                key = self.stdscr.getch()
                if key == ord('q'):
                    self.running = False
        except KeyboardInterrupt:
            pass

def main():
    def wrapper(stdscr):
        viz = CursesVisualizer(stdscr)
        viz.run()
    curses.wrapper(wrapper)
    
if __name__ == "__main__":
    main()
