#!/usr/bin/env python3
"""
robot_simulator.py - Simulate robot telemetry data and send to the system
"""

import asyncio
import json
import random
import time
from datetime import datetime
from typing import Dict, List, Tuple
import aiohttp
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

class RobotSimulator:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.robots = {}
        self.waypoints = [
            "entrance", "lobby", "office_a", "office_b", "conference_room",
            "kitchen", "storage", "charging_station", "workshop", "exit"
        ]
        self.running = False
        
    def create_robot(self, robot_id: str) -> Dict:
        """Create a new robot with initial state"""
        return {
            "robot_id": robot_id,
            "position": {
                "x": random.uniform(-10, 10),
                "y": random.uniform(-10, 10),
                "z": 0.0
            },
            "velocity": {
                "x": 0.0,
                "y": 0.0,
                "angular": 0.0
            },
            "battery_level": random.randint(20, 100),
            "navigation_status": random.choice(["idle", "navigating", "charging"]),
            "current_waypoint": random.choice(self.waypoints),
            "target_waypoint": None,
            "is_stuck": False,
            "obstacle_detected": False,
            "last_error": None,
            "system_status": "operational",
            "sensors": {
                "lidar_range": random.uniform(0.5, 5.0),
                "camera_status": "active",
                "imu_status": "calibrated"
            },
            "mission": {
                "current_task": random.choice(["patrol", "delivery", "cleaning", "maintenance"]),
                "progress": random.uniform(0, 100),
                "eta": random.randint(60, 1800)  # seconds
            }
        }
    
    def update_robot_state(self, robot: Dict) -> Dict:
        """Update robot state with realistic changes"""
        # Battery drain
        if robot["navigation_status"] == "charging":
            robot["battery_level"] = min(100, robot["battery_level"] + random.randint(1, 5))
        else:
            robot["battery_level"] = max(0, robot["battery_level"] - random.uniform(0.1, 0.5))
        
        # Position changes (if moving)
        if robot["navigation_status"] == "navigating" and not robot["is_stuck"]:
            # Random walk with some direction
            robot["position"]["x"] += random.uniform(-0.5, 0.5)
            robot["position"]["y"] += random.uniform(-0.5, 0.5)
            
            # Update velocity
            robot["velocity"]["x"] = random.uniform(-1.0, 1.0)
            robot["velocity"]["y"] = random.uniform(-1.0, 1.0)
            robot["velocity"]["angular"] = random.uniform(-0.5, 0.5)
        else:
            robot["velocity"] = {"x": 0.0, "y": 0.0, "angular": 0.0}
        
        # Navigation status changes
        if robot["battery_level"] < 20 and robot["navigation_status"] != "charging":
            robot["navigation_status"] = "charging"
            robot["current_waypoint"] = "charging_station"
        elif robot["battery_level"] > 80 and robot["navigation_status"] == "charging":
            robot["navigation_status"] = random.choice(["idle", "navigating"])
        
        # Random status changes
        if random.random() < 0.05:  # 5% chance
            robot["navigation_status"] = random.choice(["idle", "navigating", "paused"])
        
        # Stuck detection (rare)
        if random.random() < 0.02:  # 2% chance
            robot["is_stuck"] = not robot["is_stuck"]
            if robot["is_stuck"]:
                robot["navigation_status"] = "error"
                robot["last_error"] = "Path blocked - obstacle detected"
            else:
                robot["last_error"] = None
                robot["navigation_status"] = "navigating"
        
        # Obstacle detection
        robot["obstacle_detected"] = random.random() < 0.1  # 10% chance
        
        # Waypoint progression
        if robot["navigation_status"] == "navigating" and random.random() < 0.1:
            robot["current_waypoint"] = random.choice(self.waypoints)
            robot["target_waypoint"] = random.choice(self.waypoints)
        
        # Mission progress
        if robot["mission"]["current_task"] != "idle":
            robot["mission"]["progress"] = min(100, robot["mission"]["progress"] + random.uniform(0.5, 2.0))
            if robot["mission"]["progress"] >= 100:
                robot["mission"]["current_task"] = random.choice(["patrol", "delivery", "cleaning", "maintenance", "idle"])
                robot["mission"]["progress"] = 0
                robot["mission"]["eta"] = random.randint(60, 1800)
        
        # Sensor updates
        robot["sensors"]["lidar_range"] = random.uniform(0.5, 5.0)
        
        # System status
        if robot["battery_level"] < 5:
            robot["system_status"] = "critical"
        elif robot["is_stuck"] or robot["last_error"]:
            robot["system_status"] = "warning"
        else:
            robot["system_status"] = "operational"
        
        return robot
    
    async def send_telemetry(self, session: aiohttp.ClientSession, robot: Dict) -> bool:
        """Send telemetry data to the server"""
        try:
            telemetry_payload = {
                "robot_id": robot["robot_id"],
                "telemetry": {
                    "timestamp": datetime.now().isoformat(),
                    "position": robot["position"],
                    "velocity": robot["velocity"],
                    "battery_level": robot["battery_level"],
                    "navigation_status": robot["navigation_status"],
                    "current_waypoint": robot["current_waypoint"],
                    "target_waypoint": robot["target_waypoint"],
                    "is_stuck": robot["is_stuck"],
                    "obstacle_detected": robot["obstacle_detected"],
                    "last_error": robot["last_error"],
                    "system_status": robot["system_status"],
                    "sensors": robot["sensors"],
                    "mission": robot["mission"]
                }
            }
            
            async with session.post(
                f"{self.base_url}/telemetry",
                json=telemetry_payload,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    return True
                else:
                    console.print(f"[red]Telemetry failed for {robot['robot_id']}: {response.status}[/red]")
                    return False
                    
        except Exception as e:
            console.print(f"[red]Error sending telemetry for {robot['robot_id']}: {e}[/red]")
            return False
    
    async def send_chat_message(self, session: aiohttp.ClientSession, robot_id: str, message: str) -> bool:
        """Send a chat message from robot"""
        try:
            chat_payload = {
                "robot_id": robot_id,
                "user_message": message,
                "conversation_id": f"robot_{robot_id}_conv"
            }
            
            async with session.post(
                f"{self.base_url}/robot_chat",
                json=chat_payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        response_text = result.get("data", {}).get("robot_response", "No response")
                        console.print(f"[green]🤖 {robot_id}:[/green] {message}")
                        console.print(f"[blue]🤖 Response:[/blue] {response_text}")
                        return True
                    else:
                        console.print(f"[red]Chat failed for {robot_id}: {result.get('error', 'Unknown error')}[/red]")
                        return False
                else:
                    console.print(f"[red]Chat HTTP error for {robot_id}: {response.status}[/red]")
                    return False
                    
        except Exception as e:
            console.print(f"[red]Error sending chat for {robot_id}: {e}[/red]")
            return False
    
    def generate_robot_messages(self) -> List[Tuple[str, str]]:
        """Generate random robot chat messages"""
        messages = [
            ("Navigation complete", "I've reached the target waypoint successfully."),
            ("Battery low", "My battery is running low, heading to charging station."),
            ("Obstacle detected", "There's an obstacle in my path, requesting navigation assistance."),
            ("Task complete", "I've finished my current task and ready for new instructions."),
            ("Status update", "All systems operational, continuing patrol route."),
            ("Help request", "I'm stuck and need assistance, please help."),
            ("Waypoint question", "Can you guide me to the conference room?"),
            ("Battery charged", "Charging complete, ready to resume operations."),
            ("System check", "Running diagnostics, all sensors functioning normally."),
            ("Mission update", "Current mission progress at 75%, ETA 10 minutes.")
        ]
        
        selected_messages = []
        for robot_id in self.robots.keys():
            if random.random() < 0.3:  # 30% chance each robot sends a message
                message_type, message = random.choice(messages)
                selected_messages.append((robot_id, message))
        
        return selected_messages
    
    def create_status_table(self) -> Table:
        """Create a status table for display"""
        table = Table(
            title="🤖 Robot Fleet Status",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("Robot ID", style="cyan", width=12)
        table.add_column("Status", style="green", width=12)
        table.add_column("Battery", style="yellow", width=8)
        table.add_column("Position", style="blue", width=15)
        table.add_column("Waypoint", style="white", width=15)
        table.add_column("Task", style="magenta", width=12)
        
        for robot in self.robots.values():
            # Color code status
            status = robot["navigation_status"]
            if robot["is_stuck"]:
                status_style = "red"
                status = "STUCK"
            elif status == "charging":
                status_style = "yellow"
            elif status == "navigating":
                status_style = "green"
            else:
                status_style = "white"
            
            # Battery color coding
            battery = robot["battery_level"]
            if battery < 20:
                battery_style = "red"
            elif battery < 50:
                battery_style = "yellow"
            else:
                battery_style = "green"
            
            position = f"({robot['position']['x']:.1f}, {robot['position']['y']:.1f})"
            
            table.add_row(
                robot["robot_id"],
                f"[{status_style}]{status}[/{status_style}]",
                f"[{battery_style}]{battery:.1f}%[/{battery_style}]",
                position,
                robot["current_waypoint"] or "none",
                robot["mission"]["current_task"]
            )
        
        return table
    
    async def run_simulation(self, robot_ids: List[str], duration: int = 300, interval: float = 2.0):
        """Run the robot simulation"""
        console.print(f"[bold green]🚀 Starting robot simulation with {len(robot_ids)} robots[/bold green]")
        
        # Initialize robots
        for robot_id in robot_ids:
            self.robots[robot_id] = self.create_robot(robot_id)
        
        self.running = True
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            # Test connection first
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status != 200:
                        console.print(f"[red]Warning: Server health check failed ({response.status})[/red]")
            except Exception as e:
                console.print(f"[red]Warning: Cannot connect to server: {e}[/red]")
            
            with Live(self.create_status_table(), refresh_per_second=1) as live:
                cycle_count = 0
                
                while self.running and (time.time() - start_time) < duration:
                    cycle_start = time.time()
                    cycle_count += 1
                    
                    # Update robot states
                    for robot in self.robots.values():
                        self.update_robot_state(robot)
                    
                    # Send telemetry for all robots
                    telemetry_tasks = [
                        self.send_telemetry(session, robot) 
                        for robot in self.robots.values()
                    ]
                    await asyncio.gather(*telemetry_tasks, return_exceptions=True)
                    
                    # Occasionally send chat messages
                    if cycle_count % 10 == 0:  # Every 10 cycles
                        messages = self.generate_robot_messages()
                        for robot_id, message in messages:
                            await self.send_chat_message(session, robot_id, message)
                    
                    # Update display
                    live.update(self.create_status_table())
                    
                    # Wait for next cycle
                    elapsed = time.time() - cycle_start
                    if elapsed < interval:
                        await asyncio.sleep(interval - elapsed)
        
        console.print(f"[yellow]Simulation complete after {cycle_count} cycles[/yellow]")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Robot Fleet Simulator")
    parser.add_argument("--robots", "-r", nargs="+", default=["robot_001", "robot_002", "robot_003"],
                       help="Robot IDs to simulate")
    parser.add_argument("--duration", "-d", type=int, default=300,
                       help="Simulation duration in seconds")
    parser.add_argument("--interval", "-i", type=float, default=2.0,
                       help="Telemetry interval in seconds")
    parser.add_argument("--url", "-u", default="http://localhost:8000",
                       help="Base URL of the robot fleet server")
    
    args = parser.parse_args()
    
    try:
        simulator = RobotSimulator(base_url=args.url)
        
        console.print(f"[bold blue]🤖 Robot Fleet Simulator[/bold blue]")
        console.print(f"Robots: {', '.join(args.robots)}")
        console.print(f"Duration: {args.duration}s")
        console.print(f"Interval: {args.interval}s")
        console.print(f"Server: {args.url}")
        console.print("\n[dim]Press Ctrl+C to stop early[/dim]\n")
        
        asyncio.run(simulator.run_simulation(args.robots, args.duration, args.interval))
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Simulation stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Simulation failed: {e}[/red]")

if __name__ == "__main__":
    main()