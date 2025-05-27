#!/usr/bin/env python3
"""
Sample telemetry sender for Robot Guidance System
Sends realistic telemetry data to test the MCP chat app
"""

import requests
import json
import time
import random
from datetime import datetime, timedelta
import argparse
import threading

# Configuration
MCP_SERVER_URL = "http://127.0.0.1:5000"
TELEMETRY_ENDPOINT = f"{MCP_SERVER_URL}/telemetry"

# Sample waypoints for realistic navigation
WAYPOINTS = [
    "entrance", "reception", "lobby", "elevator", "stairs", 
    "cafeteria", "meeting_room_a", "meeting_room_b", "exit", 
    "parking", "restroom", "office_1", "office_2"
]

class RobotSimulator:
    """Simulates a robot with realistic telemetry patterns"""
    
    def __init__(self, robot_id, start_position=None):
        self.robot_id = robot_id
        self.position = start_position or {"x": random.uniform(0, 10), "y": random.uniform(0, 10)}
        self.target_position = self.position.copy()
        self.current_waypoint = random.choice(WAYPOINTS)
        self.target_waypoint = self.current_waypoint
        self.movement_speed = 0.0
        self.is_stuck = False
        self.navigation_status = "idle"
        self.stuck_probability = 0.02  # 2% chance per update
        self.unstuck_probability = 0.3  # 30% chance to get unstuck
        
    def update_position(self):
        """Update robot position with realistic movement"""
        if self.is_stuck:
            # Stuck robots don't move much
            self.movement_speed = random.uniform(0, 0.1)
            noise_x = random.uniform(-0.05, 0.05)
            noise_y = random.uniform(-0.05, 0.05)
            self.position["x"] += noise_x
            self.position["y"] += noise_y
            
            # Chance to get unstuck
            if random.random() < self.unstuck_probability:
                self.is_stuck = False
                self.navigation_status = "navigating"
                print(f"🟢 {self.robot_id} got unstuck!")
                
        else:
            # Normal movement toward target
            dx = self.target_position["x"] - self.position["x"]
            dy = self.target_position["y"] - self.position["y"]
            distance = (dx**2 + dy**2)**0.5
            
            if distance > 0.1:
                # Moving toward target
                self.movement_speed = random.uniform(0.3, 0.8)
                move_distance = self.movement_speed * 0.1  # 0.1 second intervals
                
                if distance > move_distance:
                    self.position["x"] += (dx / distance) * move_distance
                    self.position["y"] += (dy / distance) * move_distance
                    self.navigation_status = "navigating"
                else:
                    # Reached target
                    self.position = self.target_position.copy()
                    self.current_waypoint = self.target_waypoint
                    self.navigation_status = "arrived"
                    self.movement_speed = 0.0
                    
                    # Set new target after brief pause
                    if random.random() < 0.3:  # 30% chance to get new target
                        self._set_new_target()
            else:
                # At target, possibly idle
                self.movement_speed = 0.0
                if self.navigation_status == "arrived":
                    self.navigation_status = "idle"
                
                # Maybe get new target
                if random.random() < 0.1:  # 10% chance
                    self._set_new_target()
            
            # Random chance to get stuck
            if random.random() < self.stuck_probability:
                self.is_stuck = True
                self.navigation_status = "stuck"
                print(f"🔴 {self.robot_id} got stuck at ({self.position['x']:.2f}, {self.position['y']:.2f})")
    
    def _set_new_target(self):
        """Set a new navigation target"""
        self.target_waypoint = random.choice([wp for wp in WAYPOINTS if wp != self.current_waypoint])
        self.target_position = {
            "x": random.uniform(0, 10),
            "y": random.uniform(0, 10)
        }
        self.navigation_status = "navigating"
    
    def generate_telemetry(self):
        """Generate realistic telemetry data"""
        # Add some sensor noise
        position_noise_x = random.uniform(-0.02, 0.02)
        position_noise_y = random.uniform(-0.02, 0.02)
        
        # Expected vs actual position (encoder vs GPS/localization)
        expected_position = {
            "x": self.position["x"] + position_noise_x,
            "y": self.position["y"] + position_noise_y
        }
        
        # Sensor summary
        obstacles_detected = random.randint(0, 5) if not self.is_stuck else random.randint(3, 8)
        closest_obstacle = random.uniform(0.5, 3.0) if obstacles_detected > 0 else None
        
        if self.is_stuck and closest_obstacle:
            closest_obstacle = random.uniform(0.1, 0.5)  # Stuck robots have close obstacles
        
        sensor_summary = {
            "obstacles_detected": obstacles_detected,
            "closest_obstacle_distance": closest_obstacle,
            "imu_stable": not self.is_stuck and random.random() > 0.1,
            "wheel_encoder_error": random.uniform(0, 0.1) + (0.2 if self.is_stuck else 0)
        }
        
        return {
            "timestamp": datetime.now().isoformat(),
            "position": self.position.copy(),
            "expected_position": expected_position,
            "movement_speed": self.movement_speed,
            "distance_traveled": self.movement_speed * 0.1,  # Assuming 0.1s intervals
            "is_stuck": self.is_stuck,
            "current_waypoint": self.current_waypoint,
            "target_waypoint": self.target_waypoint,
            "navigation_status": self.navigation_status,
            "sensor_summary": sensor_summary
        }

def send_telemetry(robot_id, telemetry_data, verbose=False):
    """Send telemetry data to MCP server"""
    payload = {
        "robot_id": robot_id,
        "telemetry": telemetry_data
    }
    
    try:
        response = requests.post(TELEMETRY_ENDPOINT, json=payload, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            if verbose:
                status_indicator = "🔴" if telemetry_data.get("is_stuck") else "🟢"
                pos = telemetry_data["position"]
                waypoint_info = f"{telemetry_data['current_waypoint']} → {telemetry_data['target_waypoint']}"
                print(f"{status_indicator} {robot_id}: ({pos['x']:.2f}, {pos['y']:.2f}) [{waypoint_info}] {telemetry_data['navigation_status']}")
            return True
        else:
            print(f"❌ Failed to send telemetry for {robot_id}: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error sending telemetry for {robot_id}: {e}")
        return False

def send_robot_message(robot_id, message, priority="medium", context=None):
    """Send a message from robot to MCP system"""
    payload = {
        "robot_id": robot_id,
        "message": message,
        "priority": priority,
        "context": context or {}
    }
    
    try:
        response = requests.post(f"{MCP_SERVER_URL}/robot_message", json=payload, timeout=5)
        if response.status_code == 200:
            result = response.json()
            print(f"📨 {robot_id} message sent: {message}")
            return result
        else:
            print(f"❌ Failed to send robot message: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error sending robot message: {e}")
        return None

def simulate_robot(robot_id, duration_minutes=5, update_interval=1.0, verbose=False):
    """Simulate a single robot for specified duration"""
    robot = RobotSimulator(robot_id)
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    print(f"🤖 Starting simulation for {robot_id} (duration: {duration_minutes} minutes)")
    
    message_sent = False
    
    while time.time() < end_time:
        # Update robot state
        robot.update_position()
        
        # Generate and send telemetry
        telemetry = robot.generate_telemetry()
        success = send_telemetry(robot_id, telemetry, verbose)
        
        if not success:
            print(f"⚠️  Failed to send telemetry for {robot_id}")
        
        # If robot gets stuck, send assistance message (once)
        if robot.is_stuck and not message_sent:
            context = {
                "position": robot.position,
                "target_waypoint": robot.target_waypoint,
                "obstacles_nearby": telemetry["sensor_summary"]["obstacles_detected"]
            }
            
            messages = [
                f"Robot {robot_id} stuck, need to move to {robot.target_waypoint}",
                f"Help! {robot_id} cannot navigate, obstacles blocking path to {robot.target_waypoint}",
                f"{robot_id} requesting assistance - stuck near {robot.current_waypoint}",
            ]
            
            send_robot_message(robot_id, random.choice(messages), "high", context)
            message_sent = True
        elif not robot.is_stuck:
            message_sent = False  # Reset when unstuck
        
        time.sleep(update_interval)
    
    print(f"✅ Simulation completed for {robot_id}")

def send_single_telemetry(robot_id="TestBot", stuck=False):
    """Send a single telemetry data point"""
    robot = RobotSimulator(robot_id)
    
    if stuck:
        robot.is_stuck = True
        robot.navigation_status = "stuck"
        robot.movement_speed = 0.0
    
    telemetry = robot.generate_telemetry()
    
    print(f"🤖 Sending single telemetry for {robot_id}:")
    print(json.dumps(telemetry, indent=2))
    
    success = send_telemetry(robot_id, telemetry, verbose=True)
    
    if success and stuck:
        # Also send a help message
        send_robot_message(robot_id, f"{robot_id} stuck, need assistance to reach {robot.target_waypoint}", "high")
    
    return success

def main():
    parser = argparse.ArgumentParser(description="Send sample telemetry to Robot Guidance System")
    parser.add_argument("--robots", "-r", type=str, nargs="+", default=["Robot1"], 
                       help="Robot IDs to simulate (default: Robot1)")
    parser.add_argument("--duration", "-d", type=float, default=2.0,
                       help="Simulation duration in minutes (default: 2.0)")
    parser.add_argument("--interval", "-i", type=float, default=1.0,
                       help="Update interval in seconds (default: 1.0)")
    parser.add_argument("--single", "-s", action="store_true",
                       help="Send single telemetry point instead of continuous simulation")
    parser.add_argument("--stuck", action="store_true",
                       help="Make robot stuck (for single mode)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output")
    
    args = parser.parse_args()
    
    # Test server connectivity
    try:
        response = requests.get(f"{MCP_SERVER_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ MCP Server is running at {MCP_SERVER_URL}")
        else:
            print(f"⚠️  MCP Server responded with status {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to MCP Server at {MCP_SERVER_URL}: {e}")
        print("Make sure the server is running with: python main_mcp.py")
        return
    
    if args.single:
        # Send single telemetry point
        for robot_id in args.robots:
            send_single_telemetry(robot_id, stuck=args.stuck)
    else:
        # Start continuous simulation
        print(f"🚀 Starting telemetry simulation...")
        print(f"   Robots: {', '.join(args.robots)}")
        print(f"   Duration: {args.duration} minutes")
        print(f"   Update interval: {args.interval} seconds")
        print(f"   Server: {MCP_SERVER_URL}")
        
        # Create threads for each robot
        threads = []
        for robot_id in args.robots:
            thread = threading.Thread(
                target=simulate_robot,
                args=(robot_id, args.duration, args.interval, args.verbose)
            )
            threads.append(thread)
            thread.start()
        
        # Wait for all simulations to complete
        for thread in threads:
            thread.join()
        
        print("🏁 All robot simulations completed!")

if __name__ == "__main__":
    main()