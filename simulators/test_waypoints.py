
import sys
import os
import time
import math

# Add root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from surveyor_lib import Surveyor

HOST = 'localhost'
PORT = 8003

def main():
    try:
        print("Connecting to Simulator...")
        # record=False avoids creating HDF5 files for this test
        boat = Surveyor(host=HOST, port=PORT, sensors_to_use=[], record=False)
        with boat:
            print("Connected!")
            
            # 1. Define Waypoints (Square around current location)
            # Default start in sim is 25.7617, -80.1918
            start_lat = 25.7617
            start_lon = -80.1918
            scale = 0.0002 # approx 22 meters
            
            waypoints = [
                (start_lat + scale, start_lon),        # North
                (start_lat + scale, start_lon + scale),# East
                (start_lat, start_lon + scale),        # South
                (start_lat, start_lon)                 # West (Back to start)
            ]
            
            erp = (start_lat, start_lon) # Emergency point (required by API)
            
            print(f"\nUploading {len(waypoints)} Waypoints...")
            # send_waypoints(waypoints, erp, throttle)
            # This handles the full Protocol: Start Download -> OIWPL -> PSEAR -> End Download
            boat.send_waypoints(waypoints, erp, throttle=60)
            print("Upload Complete.")
            
            print("\nStarting Mission...")
            boat.set_waypoint_mode()
            
            # Monitor Loop
            print("Monitoring Checkpoints...")
            while True:
                state = boat.get_state()
                mode = state.get('Control Mode', 'Unknown')
                lat = state.get('Latitude', 0)
                lon = state.get('Longitude', 0)
                head = state.get('Heading (degrees Magnetic)', 0)
                
                print(f"Mode: {mode} | Pos: {lat:.6f}, {lon:.6f} | Head: {head:.1f}")
                
                # Check for completion (Simulator switches to Standby when done)
                if mode == "Standby":
                    print(f"\n{os.linesep}Mission Complete! Boat is in Standby.")
                    break
                    
                time.sleep(1)
                
    except Exception as e:
        print(f"Test Failed: {e}")

if __name__ == "__main__":
    main()
