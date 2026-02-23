
import sys
import os
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import time
import threading
import cartopy.crs as ccrs
import cartopy.io.img_tiles as cimgt

# Add root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from surveyor_lib import Surveyor

# Configuration
HOST = 'localhost' # Change to boat IP if needed
PORT = 8003

class BoatVisualizer:
    def __init__(self):
        self.lats = []
        self.lons = []
        self.heading = 0
        self.speed = 0
        self.running = True
        
        # --- CARTOPY SETUP ---
        # Use Google Tiles (Satellite)
        # Note: Requires internet access.
        self.tiler = cimgt.GoogleTiles(style='satellite')
        
        # Create map with the tiler's projection
        self.fig = plt.figure(figsize=(10, 8))
        self.ax = self.fig.add_subplot(1, 1, 1, projection=self.tiler.crs)
        
        # Set a default extent (Miami) until we get data
        # Extent format: [min_lon, max_lon, min_lat, max_lat]
        self.ax.set_extent([-80.374, -80.373, 25.757, 25.759], crs=ccrs.PlateCarree())
        
        # Add the satellite image at zoom level 20 (Higher Resolution)
        # Zoom 18 was too low for the small 50m grid (~0.6m/px vs 0.15m/px at 20)
        try:
            self.ax.add_image(self.tiler, 20)
            print("Added Satellite Map at Zoom 20")
        except Exception as e:
            print(f"Error adding map image: {e}")
        
        self.ax.set_title('Sea Robotics Surveyor - Satellite View')
        
        # Plot Elements (Must use transform=ccrs.PlateCarree() for Lat/Lon data)
        self.transform = ccrs.PlateCarree()
        
        self.ln, = self.ax.plot([], [], 'c-', linewidth=2, transform=self.transform, label='Path')
        self.head_mk, = self.ax.plot([], [], 'yo', transform=self.transform, label='Boat', 
                                     markeredgecolor='k', markeredgewidth=1, markersize=10, zorder=10)
        
        # Grid Configuration State
        self.grid_bounds = None
        self.config_mtime = 0
        self.wp_lats = []
        self.wp_lons = []
        self.grid_lines = [] # Store grid line artists to clear them if needed
        
        # Initial Grid Load
        self.check_grid_config()
        
        # Connect to Boat
        print(f"Connecting to {HOST}:{PORT}...")
        try:
            self.boat = Surveyor(host=HOST, port=PORT, sensors_to_use=[], record=False)
            self.boat.__enter__()
            print("Connected!")
        except Exception as e:
            print(f"Failed to connect: {e}")
            sys.exit(1)
            
        # Start Data Thread
        self.thread = threading.Thread(target=self.update_data)
        self.thread.daemon = True
        self.thread.start()

    def check_grid_config(self):
        grid_config_path = os.path.join(os.path.dirname(__file__), '..', 'simulators', 'grid_config.json')
        if os.path.exists(grid_config_path):
            try:
                mtime = os.path.getmtime(grid_config_path)
                if mtime > self.config_mtime:
                    print("Config change detected. Reloading...")
                    self.config_mtime = mtime
                    import json
                    with open(grid_config_path, 'r') as f:
                        cfg = json.load(f)
                        tl = cfg['top_left']
                        br = cfg['bottom_right']
                        rows = cfg['rows']
                        cols = cfg['cols']
                        
                        # Waypoints
                        self.wp_lats = []
                        self.wp_lons = []
                        if 'waypoints' in cfg:
                            wps = cfg['waypoints']
                            self.wp_lats = [w[0] for w in wps]
                            self.wp_lons = [w[1] for w in wps]
                        
                        self.grid_bounds = (tl, br)
                        
                        # Update Waypoints Plot
                        if hasattr(self, 'wp_mk'):
                            self.wp_mk.set_data(self.wp_lons, self.wp_lats)
                        else:
                             self.wp_mk, = self.ax.plot(self.wp_lons, self.wp_lats, 'yx', 
                                                       transform=self.transform, 
                                                       label='Waypoints', 
                                                       markeredgewidth=2, markersize=8, zorder=9)

                        # Draw Fountains & Obstacles
                        if 'fountains' in cfg:
                            fonts = cfg['fountains']
                            # Extract lats/lons
                            f_lats = [f[0] for f in fonts]
                            f_lons = [f[1] for f in fonts]
                            
                            # Remove old fountains
                            if hasattr(self, 'font_mk'):
                                self.font_mk.remove()
                            
                            # Plot Fountains (Orange Triangles)
                            self.font_mk, = self.ax.plot(f_lons, f_lats, 'orange', marker='^', linestyle='None',
                                                   transform=self.transform, label='Fountains', 
                                                   markeredgecolor='k', markersize=10, zorder=8)
                                                   
                            # Plot Radii (Circles)
                            # Remove old circles
                            if hasattr(self, 'obs_circles'):
                                for c in self.obs_circles: c.remove()
                            self.obs_circles = []
                            
                            if 'obstacle_radius' in cfg:
                                rad_m = cfg['obstacle_radius']
                                # Approx deg radius (using avg lat)
                                # 1 deg lat = 111132m
                                rad_deg = rad_m / 111132.0 
                                
                                import matplotlib.patches as mpatches
                                
                                for f in fonts:
                                    # Note: Circle in PlateCarree is an ellipse at high latitudes, 
                                    # but at 25deg it's close enough for viz.
                                    # Correct approach: Tissot.
                                    # Simple approach: Circle with transform.
                                    circ = mpatches.Circle((f[1], f[0]), radius=rad_deg, 
                                                          transform=self.transform,
                                                          color='red', alpha=0.2, zorder=5)
                                    self.ax.add_patch(circ)
                                    self.obs_circles.append(circ)

                        # Draw Blocked Cells (Red Squares)
                        if 'blocked_cells' in cfg:
                            b_cells = cfg['blocked_cells']
                            if hasattr(self, 'blocked_mk'): self.blocked_mk.remove()
                            
                            b_lats = [b[0] for b in b_cells]
                            b_lons = [b[1] for b in b_cells]
                            self.blocked_mk, = self.ax.plot(b_lons, b_lats, 'rs', alpha=0.3,
                                                      transform=self.transform, label='Blocked', 
                                                      markersize=15, zorder=4)

                        # Draw Grid Lines
                        # Remove old lines
                        for line in self.grid_lines:
                            line.remove()
                        self.grid_lines = []
                        
                        # Horizontal Lines
                        lat_step = (tl[0] - br[0]) / rows
                        for r in range(rows + 1):
                            lat = tl[0] - (r * lat_step)
                            ln, = self.ax.plot([tl[1], br[1]], [lat, lat], 'w--', 
                                         transform=self.transform, alpha=0.5, linewidth=1)
                            self.grid_lines.append(ln)
                            
                        # Vertical Lines
                        lon_step = (br[1] - tl[1]) / cols
                        for c in range(cols + 1):
                            lon = tl[1] + (c * lon_step)
                            ln, = self.ax.plot([lon, lon], [br[0], tl[0]], 'w--', 
                                         transform=self.transform, alpha=0.5, linewidth=1)
                            self.grid_lines.append(ln)
                            
                        # Set Extent to Grid Area + Padding
                        # Increase padding to ensure start position (outside grid) is visible
                        pad_lat = (tl[0] - br[0]) * 0.5 
                        pad_lon = (br[1] - tl[1]) * 0.5
                        ext = [tl[1] - pad_lon, br[1] + pad_lon, br[0] - pad_lat, tl[0] + pad_lat]
                        self.ax.set_extent(ext, crs=ccrs.PlateCarree())
                        print(f"Updated Map Extent: {ext}")
                        
            except Exception as e:
                print(f"Reload error: {e}")

    def update_data(self):
        while self.running:
            state = self.boat.get_state()
            lat = state.get('Latitude')
            lon = state.get('Longitude')
            if lat and lon and lat != 0.0:
                self.lats.append(lat)
                self.lons.append(lon)
                self.heading = state.get('Heading (degrees Magnetic)', 0)
                
            time.sleep(0.1)

    def update_plot(self, frame):
        self.check_grid_config()
        
        if not self.lats:
            return self.ln, self.head_mk
            
        self.ln.set_data(self.lons, self.lats)
        
        if self.lons:
            self.head_mk.set_data([self.lons[-1]], [self.lats[-1]])
            
        # Return all animated artists
        artists = [self.ln, self.head_mk]
        if hasattr(self, 'wp_mk'):
            artists.append(self.wp_mk)
            
        return tuple(artists)

def main():
    viz = BoatVisualizer()
    # Blit must be False for Cartopy usually, or careful management needed
    # Cartopy redrawing background can be tricky with Blit.
    # Let's try blit=False for safety to ensure map renders.
    ani = FuncAnimation(viz.fig, viz.update_plot, interval=200, blit=False)
    plt.show()

if __name__ == "__main__":
    main()
