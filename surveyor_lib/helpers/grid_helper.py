
from typing import List, Tuple
from geopy.distance import geodesic
import math

class GridMapper:
    """
    Maps a logical NxN grid to a physical GPS rectangular area.
    """
    def __init__(self, top_left: Tuple[float, float], bottom_right: Tuple[float, float], n_rows: int, n_cols: int):
        """
        Args:
            top_left: (lat, lon) of the top-left corner of the safe zone.
            bottom_right: (lat, lon) of the bottom-right corner.
            n_rows: Number of rows in the logical grid.
            n_cols: Number of columns in the logical grid.
        """
        self.top_left = top_left
        self.bottom_right = bottom_right
        self.n_rows = n_rows
        self.n_cols = n_cols
        
        # Calculate cell size in degrees (approximate)
        # Lat determines height, Lon determines width
        self.lat_span = self.top_left[0] - self.bottom_right[0] # Positive if N starts high
        self.lon_span = self.bottom_right[1] - self.top_left[1] # Positive if W starts low
        
        self.lat_step = self.lat_span / self.n_rows
        self.lon_step = self.lon_span / self.n_cols
        
    def get_cell_center(self, row: int, col: int) -> Tuple[float, float]:
        """
        Returns the GPS (lat, lon) center of a specific grid cell (0-indexed).
        Row 0 is Top. Col 0 is Left.
        """
        # Center is start + (index + 0.5) * step
        center_lat = self.top_left[0] - (row + 0.5) * self.lat_step
        center_lon = self.top_left[1] + (col + 0.5) * self.lon_step
        return (center_lat, center_lon)
        
    def path_to_gps(self, grid_path: List[Tuple[int, int]]) -> List[Tuple[float, float]]:
        """
        Converts a list of (row, col) tuples into a list of (lat, lon) waypoints.
        """
        return [self.get_cell_center(r, c) for r, c in grid_path]
    
    def get_grid_dimensions_meters(self) -> Tuple[float, float]:
        """
        Returns the (height_m, width_m) of the entire grid area.
        """
        # Height: Distance along latitude from top-left to bottom-left
        bottom_left = (self.bottom_right[0], self.top_left[1])
        height = geodesic(self.top_left, bottom_left).meters
        
        # Width: Distance along longitude from top-left to top-right
        top_right = (self.top_left[0], self.bottom_right[1])
        width = geodesic(self.top_left, top_right).meters
        
        return (height, width)

    def is_within_bounds(self, lat: float, lon: float) -> bool:
        """
        Checks if a GPS point is strictly within the allowed grid area.
        """
        # Lat should be between Bottom (smaller) and Top (larger)
        min_lat = min(self.top_left[0], self.bottom_right[0])
        max_lat = max(self.top_left[0], self.bottom_right[0])
        
        # Lon should be between Left (smaller/more negative) and Right (larger)
        min_lon = min(self.top_left[1], self.bottom_right[1])
        max_lon = max(self.top_left[1], self.bottom_right[1])
        
        return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

    def gps_to_cell(self, lat: float, lon: float) -> Tuple[int, int]:
        """
        Returns the (row, col) index for a given GPS coordinate.
        Returns (-1, -1) if out of bounds.
        """
        if not self.is_within_bounds(lat, lon):
            return (-1, -1)
            
        # Top-Left is (0,0)
        # Lat decreases as Row increases? Yes (North -> South)
        # Lat = Top - (Row + 0.5) * Step
        # Row + 0.5 = (Top - Lat) / Step
        # Row = ((Top - Lat) / Step) - 0.5 -> round/floor?
        # Actually range is [Top, Top-Step) = Row 0
        # So Row = floor((Top - Lat) / Step)
        
        # Use abs just in case steps end up negative
        lat_diff = self.top_left[0] - lat
        row = int(lat_diff / self.lat_step)
        
        # Lon increases as Col increases? Yes (West -> East)
        lon_diff = lon - self.top_left[1]
        col = int(lon_diff / self.lon_step)
        
        # Clamp just in case floating point puts it at N
        row = max(0, min(row, self.n_rows - 1))
        col = max(0, min(col, self.n_cols - 1))
        
        return (row, col)
