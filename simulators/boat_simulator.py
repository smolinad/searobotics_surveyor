
import socket
import threading
import time
import math
import sys
import os
import signal
from datetime import datetime

import curses

# Configuration
HOST = '0.0.0.0'
PORT = 8003
UPDATE_RATE = 10  # Hz

# Physics Constants
MAX_SPEED = 2.0  # m/s
TURN_RATE_FACTOR = 4.0  # degrees per tick per thrust_diff (Very tight turns)
ACCELERATION = 0.1
DECELERATION = 0.2  # Stop faster

# ANSI Colors (Kept for compatibility with other tools if needed, though unused in curses)
GREEN = '\033[92m'
BLUE = '\033[94m'
YELLOW = '\033[93m'
RESET = '\033[0m'
CLEAR_SCREEN = '\033[2J\033[H'

def compute_checksum(sentence):
    """Calculates NMEA checksum for a sentence (without $ and *)."""
    calc_cksum = 0
    for s in sentence:
        calc_cksum ^= ord(s)
    return hex(calc_cksum)[2:].upper().zfill(2)

def create_nmea(content):
    """Wraps content in NMEA format $...*CS\r\n"""
    checksum = compute_checksum(content)
    return f"${content}*{checksum}\r\n"

class BoatSimulator:
    def __init__(self):
        self.running = True
        
        # Connection Management
        self.clients = []
        self.clients_lock = threading.Lock()
        
        # Logging
        self.logs = []
        self.log_lock = threading.Lock()
        
        # State
        self.lat = 25.758326  # Lake location (User specified)
        self.lon = -80.373864
        self.heading = 0.0
        self.speed = 0.0
        
        # Control inputs
        self.target_thrust = 0
        self.target_diff = 0
        self.control_mode = "Standby"
        
        # Waypoint Navigation State
        self.waypoints = []
        self.current_wp_index = 0
        self.download_mode = False
        self.download_count = 0
        self.mission_throttle = 50
        
        # Socket Setup
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self):
        # Start Threads
        # 1. Physics
        self.sim_thread = threading.Thread(target=self.physics_loop)
        self.sim_thread.daemon = True
        self.sim_thread.start()
        
        # 2. Broadcast
        self.broadcast_thread = threading.Thread(target=self.broadcast_telemetry)
        self.broadcast_thread.daemon = True
        self.broadcast_thread.start()

        # 3. Connection Acceptor
        self.accept_thread = threading.Thread(target=self.accept_loop)
        self.accept_thread.daemon = True
        self.accept_thread.start()
        
        # 4. Main UI Loop (Curses)
        try:
            curses.wrapper(self.ui_loop)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.socket.close()
            print("Simulator Stopped.")

    def log(self, msg):
        """Thread-safe logging to screen buffer"""
        with self.log_lock:
            self.logs.append(msg)
            if len(self.logs) > 50: # Keep last 50 lines
                self.logs.pop(0)

    def print(self, *args):
        """Override print to log"""
        msg = " ".join(str(a) for a in args)
        self.log(msg)

    def accept_loop(self):
        try:
            self.socket.bind((HOST, PORT))
            self.socket.listen(5)
            self.log(f"Listening on {HOST}:{PORT}")
        except Exception as e:
            self.log(f"Bind Failed: {e}")
            return

        while self.running:
            try:
                conn, addr = self.socket.accept()
                with self.clients_lock:
                    self.clients.append((conn, addr))
                self.log(f"{BLUE}New connection from {addr}{RESET}")
                
                t = threading.Thread(target=self.handle_client, args=(conn, addr))
                t.daemon = True
                t.start()
            except:
                break
                
    def ui_loop(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)
        stdscr.nodelay(1)
        stdscr.timeout(100)
        
        # Colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
        
        while self.running:
            self.draw_ui()
            ch = stdscr.getch()
            if ch == ord('q'):
                self.running = False
            
    def draw_ui(self):
        if not hasattr(self, 'stdscr'): return
        scr = self.stdscr
        try:
            scr.clear()
            h, w = scr.getmaxyx()
            
            # --- HEADER ---
            title = " SEA ROBOTICS SURVEYOR SIMULATOR "
            scr.addstr(0, max(0, (w-len(title))//2), title, curses.A_BOLD | curses.color_pair(3))
            
            # --- STATUS DASHBOARD (Top) ---
            # Row 2: Status | Mode | Clients
            status_color = curses.color_pair(1) if self.clients else curses.color_pair(4)
            scr.addstr(2, 2, "Status: ")
            scr.addstr(f"{len(self.clients)} Clients", status_color)
            
            scr.addstr(2, 25, "Mode: ")
            scr.addstr(f"{self.control_mode}", curses.color_pair(2))
            
            # Row 3: Thrust | Diff | Speed
            scr.addstr(3, 2, f"Thru: {self.target_thrust}%")
            scr.addstr(3, 25, f"Diff: {self.target_diff}%")
            scr.addstr(3, 45, f"Speed: {self.speed:.2f} m/s")
            
            # Row 4: Position | Heading
            scr.addstr(4, 2, f"Pos:  {self.lat:.6f}, {self.lon:.6f}")
            scr.addstr(4, 45, f"Head:  {self.heading:.1f}")
            
            # Row 5: Visual
            dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
            idx = int((self.heading + 22.5) / 45.0) % 8
            scr.addstr(4, 60, f"[{dirs[idx]}]", curses.A_BOLD)
            
            scr.addstr(5, 0, "-" * w)
            
            # --- SCROLLING LOGS (Bottom) ---
            log_start_y = 6
            max_log_lines = h - log_start_y - 1
            
            with self.log_lock:
                # Get last N logs that fit
                to_draw = self.logs[-max_log_lines:]
                for i, msg in enumerate(to_draw):
                    # Clean ANSI codes for curses 
                    # (Simple approach: strip common codes or just print raw if no simple way)
                    # For now, simplistic stripping
                    clean_msg = msg.replace(GREEN, "").replace(BLUE, "").replace(YELLOW, "").replace(RESET, "")
                    scr.addstr(log_start_y + i, 2, f"> {clean_msg[:w-4]}")
                    
            scr.refresh()
        except:
            pass

    # ... keep existing methods ... (handle_client, parse_command, physics_loop, broadcast_telemetry)
    # BUT remove print() calls inside them? 
    # Solution: I defined a `print` method on the class that redirects to logs. 
    # But I need to change `print(...)` to `self.print(...)` or `self.log(...)` inside the methods.
    # OR: Redirect stdout? No, explicit is better. I will update methods to use self.log

    def handle_client(self, conn, addr):
        buffer = ""
        while self.running:
            try:
                data = conn.recv(1024).decode('utf-8', errors='ignore')
                if not data:
                    break
                
                buffer += data
                while "\n" in buffer:
                    msg, buffer = buffer.split("\n", 1)
                    self.parse_command(msg.strip())
            except Exception:
                break
        
        self.remove_client(conn, addr)

    def remove_client(self, conn, addr):
        with self.clients_lock:
            try:
                conn.close()
            except:
                pass
            if (conn, addr) in self.clients:
                self.clients.remove((conn, addr))
        self.log(f"Client {addr} disconnected")

    def parse_command(self, msg):
        # Remove checksum if present
        if "*" in msg:
            msg = msg.split("*")[0]
        
        parts = msg.replace("$", "").split(",")
        cmd = parts[0]
        
        if cmd == "PSEAC":
            # Command: Control Mode
            if len(parts) >= 2:
                mode = parts[1]
                
                if mode == "F":
                    num_lines = int(parts[2])
                    if num_lines > 0:
                        self.download_mode = True
                        self.download_count = 0
                        self.download_total = num_lines
                        self.waypoints = [] 
                        self.log(f"Started Waypoint Download ({num_lines} lines)")
                    else:
                        self.download_mode = False
                        self.log(f"Ended Waypoint Download. Total: {len(self.waypoints)}")
                        
                elif mode == "T": 
                    self.control_mode = "Thruster"
                    try:
                        self.target_thrust = int(parts[3])
                        self.target_diff = int(parts[4])
                    except:
                        pass
                elif mode == "L": 
                    self.control_mode = "Standby"
                    self.target_thrust = 0
                    self.target_diff = 0
                elif mode == "R": 
                    self.control_mode = "Station Keep"
                elif mode == "S": 
                    try:
                        self.lat = float(parts[2])
                        self.lon = float(parts[3])
                        if len(parts) > 4:
                            self.heading = float(parts[4])
                        
                        # Reset Dynamics for Clean Start
                        self.speed = 0.0
                        self.target_thrust = 0
                        self.target_diff = 0
                        
                        self.log(f"Teleported to {self.lat}, {self.lon}, {self.heading}° (State Reset)")
                    except Exception as e:
                        self.log(f"Teleport failed: {e}")

                elif mode == "W": 
                    self.control_mode = "Waypoint"
                    self.current_wp_index = 0
                    self.log(f"Switched to Waypoint Mode")
                    
        elif cmd == "OIWPL":
            if self.download_mode:
                try:
                    lat_str = parts[1]
                    lat_hemi = parts[2]
                    lon_str = parts[3]
                    lon_hemi = parts[4]
                    
                    lat_deg = float(lat_str[:2])
                    lat_min = float(lat_str[2:])
                    lat = lat_deg + (lat_min / 60.0)
                    if lat_hemi == 'S': lat = -lat
                    
                    lon_deg = float(lon_str[:3])
                    lon_min = float(lon_str[3:])
                    lon = lon_deg + (lon_min / 60.0)
                    if lon_hemi == 'W': lon = -lon
                    
                    self.waypoints.append((lat, lon))
                    self.download_count += 1
                except Exception as e:
                    self.log(f"Error parsing OIWPL: {e}")
                    
        elif cmd == "PSEAR":
            try:
                self.mission_throttle = int(parts[3])
                self.log(f"Mission Throttle set to {self.mission_throttle}%")
            except:
                pass

    def physics_loop(self):
        dt = 0.1
        while self.running:
            # Control Logic
            if self.control_mode == "Waypoint":
                if self.waypoints and self.current_wp_index < len(self.waypoints):
                    target = self.waypoints[self.current_wp_index]
                    
                    meters_per_lat = 111132
                    meters_per_lon = 111132 * math.cos(math.radians(self.lat))
                    
                    d_lat_m = (target[0] - self.lat) * meters_per_lat
                    d_lon_m = (target[1] - self.lon) * meters_per_lon
                    
                    dist = math.sqrt(d_lat_m**2 + d_lon_m**2)
                    
                    target_bearing = math.degrees(math.atan2(d_lon_m, d_lat_m))
                    if target_bearing < 0: target_bearing += 360
                    
                    err = target_bearing - self.heading
                    while err > 180: err -= 360
                    while err < -180: err += 360
                    
                    # 3. Acceptance Radius (e.g., 2.5 meters)
                    # Tightened to ensure boat enters the cell properly
                    if dist < 2.5:
                        self.log(f"Reached Waypoint {self.current_wp_index+1}/{len(self.waypoints)}")
                        self.current_wp_index += 1
                        if self.current_wp_index >= len(self.waypoints):
                            self.log(f"Mission Complete!")
                            self.control_mode = "Standby"
                            self.target_thrust = 0
                            self.target_diff = 0
                    else:
                        steering = max(-50, min(50, err * 0.3))
                        thrust_cmd = self.mission_throttle
                        if self.current_wp_index == len(self.waypoints) - 1:
                            if dist < 10.0:
                                factor = max(0.2, dist / 10.0)
                                thrust_cmd = int(self.mission_throttle * factor)
                                
                        self.target_thrust = thrust_cmd
                        self.target_diff = int(steering)
                else:
                    self.target_thrust = 0
                    self.target_diff = 0
            
            elif self.control_mode == "Standby":
                self.target_thrust = 0
                self.target_diff = 0

            # Physics Update
            target_speed = (self.target_thrust / 100.0) * MAX_SPEED
            if self.speed < target_speed:
                self.speed += ACCELERATION * dt
            elif self.speed > target_speed:
                self.speed -= DECELERATION * dt
            
            turn = (self.target_diff / 100.0) * TURN_RATE_FACTOR * (1.0 + abs(self.speed))
            self.heading = (self.heading + turn) % 360
            
            dist_moved = self.speed * dt
            rad = math.radians(self.heading)
            d_lat = (dist_moved * math.cos(rad)) / 111111.0
            d_lon = (dist_moved * math.sin(rad)) / (111111.0 * math.cos(math.radians(self.lat)))
            
            self.lat += d_lat
            self.lon += d_lon
            
            # Remove direct update_display call
            # self.update_display()
            time.sleep(dt)

    # Remove old broadcast_telemetry? No, need to keep it.
    def broadcast_telemetry(self):
        while self.running:
            # 1. GPGGA
            now = datetime.utcnow()
            ts = now.strftime("%H%M%S.00")
            
            lat_deg = int(abs(self.lat))
            lat_min = (abs(self.lat) - lat_deg) * 60
            lat_str = f"{lat_deg:02d}{lat_min:08.5f}"
            lat_dir = 'N' if self.lat >= 0 else 'S'
            
            lon_deg = int(abs(self.lon))
            lon_min = (abs(self.lon) - lon_deg) * 60
            lon_str = f"{lon_deg:03d}{lon_min:08.5f}"
            lon_dir = 'E' if self.lon >= 0 else 'W'
            
            gpgga = f"GPGGA,{ts},{lat_str},{lat_dir},{lon_str},{lon_dir},1,08,1.0,0.0,M,0.0,M,,"
            nmea_gpgga = create_nmea(gpgga).encode()

            # 2. PSEAA
            pseaa = f"PSEAA,0.0,0.0,{self.heading:.1f},0.0,25.0,0.0,0.0,0.0,0.0"
            nmea_pseaa = create_nmea(pseaa).encode()
                
            # 3. PSEAD
            mode_char = "L"
            if self.control_mode == "Thruster": mode_char = "T"
            elif self.control_mode == "Station Keep": mode_char = "R"
            
            psead = f"PSEAD,{mode_char},{self.heading:.1f},{self.target_thrust},{self.target_diff}"
            nmea_psead = create_nmea(psead).encode()
            
            with self.clients_lock:
                to_remove = []
                for conn, addr in self.clients:
                    try:
                        conn.sendall(nmea_gpgga)
                        conn.sendall(nmea_pseaa)
                        conn.sendall(nmea_psead)
                    except:
                        to_remove.append((conn, addr))
                
                for item in to_remove:
                    self.remove_client(item[0], item[1])

            time.sleep(1.0 / UPDATE_RATE)

if __name__ == "__main__":
    sim = BoatSimulator()
    sim.start()
