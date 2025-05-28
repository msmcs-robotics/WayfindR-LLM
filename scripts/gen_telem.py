#!/usr/bin/env python3
"""
Robot Telemetry Simulator
Simulates a robot navigating between office1 and office2, getting stuck, and continuing.
Sends realistic telemetry data to the Robot Guidance System.
"""

import requests
import time
import random
import math
from datetime import datetime
from typing import Dict, Tuple

# Configuration
ROBOT_ID = "robot_alpha"
TELEMETRY_ENDPOINT = "http://127.0.0.1:5000/telemetry"
UPDATE_INTERVAL = 2.0  # seconds between telemetry updates

# Office locations (x, y coordinates)
WAYPOINTS = {
    "office1": {"x": 0.0, "y": 0.0},
    "office2": {"x": 10.0, "y": 8.0},
    "stuck_point": {"x": 5.2, "y": 4.1}  # Where robot gets stuck
}

class RobotSimulator:
    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        self.position = {"x": 0.0, "y": 0.0}
        self.target_waypoint = "office2"
        self.current_waypoint = "office1"
        self.speed = 0.8  # m/s
        self.navigation_status = "navigating"
        self.is_stuck = False
        self.distance_traveled = 0.0
        self.stuck_duration = 0
        self.mission_phase = "to_office2"  # to_office2, stuck, unstuck, to_office1
        self.total_distance = 0.0
        
        print(f"🤖 {self.robot_id} initialized at office1")
        print(f"📍 Starting position: ({self.position['x']:.2f}, {self.position['y']:.2f})")
        print(f"🎯 First target: {self.target_waypoint}")

    def calculate_distance(self, pos1: Dict, pos2: Dict) -> float:
        """Calculate Euclidean distance between two points"""
        dx = pos2["x"] - pos1["x"]
        dy = pos2["y"] - pos1["y"]
        return math.sqrt(dx*dx + dy*dy)

    def move_towards_target(self, target_pos: Dict, dt: float) -> Dict:
        """Move robot towards target position"""
        current_pos = self.position.copy()
        
        # Calculate direction vector
        dx = target_pos["x"] - current_pos["x"]
        dy = target_pos["y"] - current_pos["y"]
        distance_to_target = math.sqrt(dx*dx + dy*dy)
        
        if distance_to_target < 0.1:  # Close enough to target
            return target_pos
        
        # Normalize direction and apply speed
        if distance_to_target > 0:
            dx = dx / distance_to_target
            dy = dy / distance_to_target
        
        # Calculate movement with some randomness
        movement_distance = self.speed * dt
        noise_factor = 0.1  # Add some movement noise
        
        new_x = current_pos["x"] + dx * movement_distance + random.uniform(-noise_factor, noise_factor)
        new_y = current_pos["y"] + dy * movement_distance + random.uniform(-noise_factor, noise_factor)
        
        # Track distance traveled
        actual_movement = math.sqrt((new_x - current_pos["x"])**2 + (new_y - current_pos["y"])**2)
        self.distance_traveled += actual_movement
        self.total_distance += actual_movement
        
        return {"x": new_x, "y": new_y}

    def update_mission_state(self):
        """Update the robot's mission state based on current situation"""
        current_pos = self.position
        
        if self.mission_phase == "to_office2":
            # Check if we've reached the stuck point
            stuck_pos = WAYPOINTS["stuck_point"]
            if self.calculate_distance(current_pos, stuck_pos) < 0.5:
                self.mission_phase = "stuck"
                self.is_stuck = True
                self.navigation_status = "stuck"
                self.speed = 0.0
                self.stuck_duration = 0
                print(f"🔴 {self.robot_id} got stuck at ({current_pos['x']:.2f}, {current_pos['y']:.2f})!")
                
        elif self.mission_phase == "stuck":
            self.stuck_duration += UPDATE_INTERVAL
            if self.stuck_duration >= 10:  # Stuck for 10 seconds
                self.mission_phase = "unstuck"
                self.is_stuck = False
                self.navigation_status = "navigating"
                self.speed = 0.6  # Slower after getting unstuck
                print(f"🟢 {self.robot_id} recovered and continuing to {self.target_waypoint}")
                
        elif self.mission_phase == "unstuck":
            # Continue to office2
            office2_pos = WAYPOINTS["office2"]
            if self.calculate_distance(current_pos, office2_pos) < 0.5:
                self.mission_phase = "to_office1"
                self.current_waypoint = "office2"
                self.target_waypoint = "office1"
                self.navigation_status = "navigating"
                self.speed = 0.8
                self.distance_traveled = 0.0
                print(f"✅ {self.robot_id} reached office2, now heading back to office1")
                
        elif self.mission_phase == "to_office1":
            # Check if we've reached office1
            office1_pos = WAYPOINTS["office1"]
            if self.calculate_distance(current_pos, office1_pos) < 0.5:
                self.mission_phase = "to_office2"
                self.current_waypoint = "office1"
                self.target_waypoint = "office2"
                self.navigation_status = "navigating"
                self.speed = 0.8
                self.distance_traveled = 0.0
                print(f"✅ {self.robot_id} reached office1, now heading back to office2")

    def simulate_step(self, dt: float):
        """Simulate one time step of robot movement"""
        self.update_mission_state()
        
        if not self.is_stuck:
            # Move towards current target
            target_pos = WAYPOINTS[self.target_waypoint]
            
            # Special handling for getting to stuck point first
            if self.mission_phase == "to_office2" and not self.is_stuck:
                # First go to stuck point
                target_pos = WAYPOINTS["stuck_point"]
            
            self.position = self.move_towards_target(target_pos, dt)

    def generate_telemetry(self) -> Dict:
        """Generate realistic telemetry data"""
        # Calculate expected position (where robot should be if following perfect path)
        target_pos = WAYPOINTS[self.target_waypoint]
        if self.mission_phase == "to_office2" and not self.is_stuck:
            target_pos = WAYPOINTS["stuck_point"]
        
        # Expected position is slightly ahead on the path
        expected_x = self.position["x"] + random.uniform(-0.3, 0.3)
        expected_y = self.position["y"] + random.uniform(-0.3, 0.3)
        
        # Add some sensor noise to position
        noisy_x = self.position["x"] + random.uniform(-0.1, 0.1)
        noisy_y = self.position["y"] + random.uniform(-0.1, 0.1)
        
        telemetry = {
            "robot_id": self.robot_id,
            "timestamp": datetime.now().isoformat(),
            "position": {"x": round(noisy_x, 2), "y": round(noisy_y, 2)},
            "expected_position": {"x": round(expected_x, 2), "y": round(expected_y, 2)},
            "movement_speed": round(self.speed + random.uniform(-0.1, 0.1), 2),
            "distance_traveled": round(self.distance_traveled, 2),
            "is_stuck": self.is_stuck,
            "current_waypoint": self.current_waypoint,
            "target_waypoint": self.target_waypoint,
            "navigation_status": self.navigation_status,
            "sensor_data": {
                "battery_level": round(100 - (self.total_distance * 2), 1),  # Battery drains with distance
                "obstacle_detected": self.is_stuck,
                "gps_accuracy": round(random.uniform(0.5, 2.0), 1),
                "wifi_signal": random.randint(70, 100)
            }
        }
        
        return telemetry

    def send_telemetry(self, telemetry: Dict) -> bool:
        """Send telemetry to the server"""
        try:
            response = requests.post(TELEMETRY_ENDPOINT, json=telemetry, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    return True
                else:
                    print(f"❌ Server error: {result.get('error', 'Unknown error')}")
                    return False
            else:
                print(f"❌ HTTP error: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection error: {e}")
            return False

    def print_status(self, telemetry: Dict):
        """Print current robot status"""
        pos = telemetry["position"]
        status_emoji = "🔴" if self.is_stuck else "🟢"
        
        print(f"{status_emoji} [{datetime.now().strftime('%H:%M:%S')}] {self.robot_id}")
        print(f"   📍 Position: ({pos['x']:.2f}, {pos['y']:.2f})")
        print(f"   🚩 Route: {self.current_waypoint} → {self.target_waypoint}")
        print(f"   🏃 Speed: {telemetry['movement_speed']:.2f} m/s")
        print(f"   📏 Distance: {telemetry['distance_traveled']:.2f}m")
        print(f"   🔋 Battery: {telemetry['sensor_data']['battery_level']:.1f}%")
        
        if self.is_stuck:
            print(f"   ⚠️  STUCK for {self.stuck_duration:.1f}s!")
        
        print()

def main():
    """Main simulation loop"""
    print("🤖 Starting Robot Telemetry Simulator")
    print(f"📡 Sending telemetry to: {TELEMETRY_ENDPOINT}")
    print(f"🔄 Update interval: {UPDATE_INTERVAL}s")
    print("=" * 50)
    
    robot = RobotSimulator(ROBOT_ID)
    
    try:
        step_count = 0
        while True:
            step_count += 1
            
            # Simulate robot movement
            robot.simulate_step(UPDATE_INTERVAL)
            
            # Generate and send telemetry
            telemetry = robot.generate_telemetry()
            success = robot.send_telemetry(telemetry)
            
            # Print status every few steps or when important events occur
            if step_count % 3 == 0 or robot.is_stuck or robot.mission_phase == "unstuck":
                robot.print_status(telemetry)
                if success:
                    print("   ✅ Telemetry sent successfully")
                else:
                    print("   ❌ Failed to send telemetry")
                print()
            
            # Wait for next update
            time.sleep(UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n🛑 Simulation stopped by user")
        print(f"📊 Total distance traveled: {robot.total_distance:.2f}m")
        print("👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Simulation error: {e}")

if __name__ == "__main__":
    main()