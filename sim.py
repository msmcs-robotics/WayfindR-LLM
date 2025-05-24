import math
import random
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
from matplotlib.animation import FuncAnimation
import datetime
from matplotlib.gridspec import GridSpec
import threading
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
from typing import Dict, List, Tuple, Optional, Any
import time
import requests
import asyncio
from collections import deque
import logging

# Import shared LLM configuration and RAG store
from llm_config import get_ollama_client, get_model_name
from rag_store import add_telemetry_data, init_stores

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize RAG stores
print("Initializing RAG stores...")
init_stores()
print("RAG stores initialized successfully!")

# Create FastAPI app
app = FastAPI(title="Robot Telemetry Collection System", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration parameters
TELEMETRY_UPDATE_FREQ = 0.5  # seconds - frequency of telemetry collection
MAX_TELEMETRY_HISTORY = 1000  # Maximum number of telemetry records to keep in memory
MAX_ROBOT_HISTORY = 500  # Maximum position history per robot
RASPBERRY_PI_BASE_URL = "http://192.168.1.100:5000"  # Default Pi address - configurable

# Global state for telemetry collection
connected_robots = {}  # robot_id -> robot info
telemetry_history = deque(maxlen=MAX_TELEMETRY_HISTORY)
robot_positions = {}  # robot_id -> deque of recent positions
robot_commands = {}  # robot_id -> list of pending commands
system_status = "running"
last_telemetry_update = time.time()

# Simulated robot for demonstration (remove when connecting to real Pi)
DEMO_MODE = True  # Set to False when connecting to real hardware

# Demo robot state (for simulation purposes only)
if DEMO_MODE:
    demo_robot = {
        "robot_id": "indoor_nav_robot_01",
        "position": {"x": 0.0, "y": 0.0, "heading": 0.0},
        "status": "idle",
        "target_waypoint": None,
        "battery_level": 100.0,
        "obstacle_distance": 5.0,
        "last_update": time.time()
    }
    connected_robots["indoor_nav_robot_01"] = demo_robot
    robot_positions["indoor_nav_robot_01"] = deque(maxlen=MAX_ROBOT_HISTORY)

# Pydantic models for API
class TelemetryData(BaseModel):
    timestamp: str
    robot_id: str
    position: Dict[str, float]  # {"x": float, "y": float, "heading": float}
    status: str
    target_waypoint: Optional[str] = None
    battery_level: float
    obstacle_distance: float
    lidar_summary: Optional[Dict[str, float]] = None
    navigation: Optional[Dict[str, Any]] = None
    sensors: Optional[Dict[str, Any]] = None

class NavigationCommand(BaseModel):
    robot_id: str
    command: str  # "goto", "stop", "home", "patrol", etc.
    parameters: Optional[Dict[str, Any]] = None

class RobotStatus(BaseModel):
    robot_id: str
    position: Dict[str, float]
    status: str
    target: Optional[str]
    battery: float
    obstacle_distance: float
    last_seen: float

class SystemHealth(BaseModel):
    status: str
    connected_robots: int
    telemetry_records: int
    last_update: float
    uptime: float

# System startup time for uptime calculation
system_start_time = time.time()

def process_telemetry_data(telemetry: TelemetryData):
    """Process incoming telemetry data and store in databases"""
    try:
        # Update robot state
        robot_info = {
            "robot_id": telemetry.robot_id,
            "position": telemetry.position,
            "status": telemetry.status,
            "target_waypoint": telemetry.target_waypoint,
            "battery_level": telemetry.battery_level,
            "obstacle_distance": telemetry.obstacle_distance,
            "last_update": time.time()
        }
        
        connected_robots[telemetry.robot_id] = robot_info
        
        # Store position history
        if telemetry.robot_id not in robot_positions:
            robot_positions[telemetry.robot_id] = deque(maxlen=MAX_ROBOT_HISTORY)
        
        robot_positions[telemetry.robot_id].append({
            "timestamp": telemetry.timestamp,
            "x": telemetry.position["x"],
            "y": telemetry.position["y"],
            "heading": telemetry.position["heading"]
        })
        
        # Add to telemetry history
        telemetry_history.append(telemetry.dict())
        
        # Create text representation for RAG storage
        telemetry_text = f"""Robot Navigation Telemetry Report
Time: {telemetry.timestamp}
Robot ID: {telemetry.robot_id}
Position: ({telemetry.position['x']}, {telemetry.position['y']}) meters
Heading: {telemetry.position['heading']} degrees
Status: {telemetry.status}
Target: {telemetry.target_waypoint or 'None'}
Battery: {telemetry.battery_level}%
Nearest Obstacle: {telemetry.obstacle_distance} meters"""

        # Add LIDAR summary if available
        if telemetry.lidar_summary:
            telemetry_text += f"""
LIDAR - Min/Avg/Max Distance: {telemetry.lidar_summary.get('min_distance', 0)}/{telemetry.lidar_summary.get('avg_distance', 0)}/{telemetry.lidar_summary.get('max_distance', 0)} meters"""

        # Add navigation info if available
        if telemetry.navigation:
            telemetry_text += f"""
Navigation Progress: {telemetry.navigation.get('waypoints_remaining', 0)} waypoints remaining
Navigation Time: {telemetry.navigation.get('navigation_time', 0)} seconds"""
        
        # Store in RAG system
        telemetry_id = add_telemetry_data(telemetry_text, {
            "robot_id": telemetry.robot_id,
            "timestamp": telemetry.timestamp,
            "status": telemetry.status,
            "position_x": telemetry.position["x"],
            "position_y": telemetry.position["y"],
            "battery": telemetry.battery_level,
            "obstacle_distance": telemetry.obstacle_distance
        })
        
        logger.info(f"Processed telemetry for {telemetry.robot_id}: {telemetry_id}")
        
    except Exception as e:
        logger.error(f"Error processing telemetry: {e}")

async def send_command_to_robot(robot_id: str, command: Dict[str, Any]) -> bool:
    """Send navigation command to Raspberry Pi"""
    try:
        # Get robot's IP address (in real deployment, this would be configured)
        robot_url = f"{RASPBERRY_PI_BASE_URL}/command"
        
        # In demo mode, just simulate the command
        if DEMO_MODE:
            logger.info(f"DEMO: Would send command to {robot_id}: {command}")
            # Simulate command execution for demo robot
            if robot_id in connected_robots:
                if command.get("action") == "goto":
                    connected_robots[robot_id]["status"] = "navigating"
                    connected_robots[robot_id]["target_waypoint"] = command.get("dest")
                elif command.get("action") == "stop":
                    connected_robots[robot_id]["status"] = "idle"
                    connected_robots[robot_id]["target_waypoint"] = None
            return True
        
        # Send actual HTTP request to Raspberry Pi
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.post(robot_url, json=command) as response:
                if response.status == 200:
                    logger.info(f"Command sent successfully to {robot_id}")
                    return True
                else:
                    logger.error(f"Failed to send command to {robot_id}: HTTP {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error sending command to {robot_id}: {e}")
        return False

def simulate_demo_robot_movement():
    """Simulate robot movement for demonstration purposes"""
    if not DEMO_MODE or "indoor_nav_robot_01" not in connected_robots:
        return
    
    robot = connected_robots["indoor_nav_robot_01"]
    
    # Simple movement simulation
    if robot["status"] == "navigating":
        # Simulate movement toward target
        current_x = robot["position"]["x"]
        current_y = robot["position"]["y"]
        
        # Simple target positions for demo
        targets = {
            "kitchen": (-15.0, 10.0),
            "living_room": (-10.0, -5.0),
            "bedroom1": (10.0, 10.0),
            "home": (0.0, 0.0)
        }
        
        target_name = robot.get("target_waypoint")
        if target_name and target_name in targets:
            target_x, target_y = targets[target_name]
            
            # Move toward target
            dx = target_x - current_x
            dy = target_y - current_y
            distance = math.sqrt(dx*dx + dy*dy)
            
            if distance < 0.5:  # Reached target
                robot["position"]["x"] = target_x
                robot["position"]["y"] = target_y
                robot["status"] = "reached_target"
            else:
                # Move 0.5 meters toward target
                move_speed = 0.5
                robot["position"]["x"] += (dx / distance) * move_speed
                robot["position"]["y"] += (dy / distance) * move_speed
                robot["position"]["heading"] = math.degrees(math.atan2(dy, dx))
    
    # Simulate battery drain
    robot["battery_level"] = max(0, robot["battery_level"] - 0.01)
    
    # Simulate obstacle distance variation
    robot["obstacle_distance"] = max(0.5, 5.0 + random.uniform(-1.0, 1.0))

# API Endpoints

@app.get("/")
async def root():
    return {"message": "Robot Telemetry Collection System", "version": "1.0.0"}

@app.post("/telemetry")
async def receive_telemetry(telemetry: TelemetryData):
    """Receive telemetry data from Raspberry Pi robots"""
    process_telemetry_data(telemetry)
    global last_telemetry_update
    last_telemetry_update = time.time()
    return {"status": "received", "robot_id": telemetry.robot_id}

@app.get("/robots")
async def get_connected_robots():
    """Get list of all connected robots and their status"""
    return {
        "robots": [
            RobotStatus(
                robot_id=robot_id,
                position=robot_info["position"],
                status=robot_info["status"],
                target=robot_info.get("target_waypoint"),
                battery=robot_info["battery_level"],
                obstacle_distance=robot_info["obstacle_distance"],
                last_seen=robot_info["last_update"]
            ).dict()
            for robot_id, robot_info in connected_robots.items()
        ]
    }

@app.get("/robots/{robot_id}")
async def get_robot_status(robot_id: str):
    """Get specific robot status"""
    if robot_id not in connected_robots:
        raise HTTPException(status_code=404, detail="Robot not found")
    
    robot_info = connected_robots[robot_id]
    return RobotStatus(
        robot_id=robot_id,
        position=robot_info["position"],
        status=robot_info["status"],
        target=robot_info.get("target_waypoint"),
        battery=robot_info["battery_level"],
        obstacle_distance=robot_info["obstacle_distance"],
        last_seen=robot_info["last_update"]
    )

@app.get("/robots/{robot_id}/history")
async def get_robot_position_history(robot_id: str, limit: int = 50):
    """Get robot position history"""
    if robot_id not in robot_positions:
        raise HTTPException(status_code=404, detail="Robot not found")
    
    history = list(robot_positions[robot_id])
    return {"robot_id": robot_id, "history": history[-limit:]}

@app.post("/command")
async def send_navigation_command(command: NavigationCommand):
    """Send navigation command to robot (called by MCP system)"""
    if command.robot_id not in connected_robots:
        raise HTTPException(status_code=404, detail="Robot not found")
    
    # Format command for Raspberry Pi
    pi_command = {
        "action": command.command,
        "parameters": command.parameters or {}
    }
    
    # Add specific parameters based on command type
    if command.command == "goto" and command.parameters:
        pi_command["dest"] = command.parameters.get("destination")
    
    success = await send_command_to_robot(command.robot_id, pi_command)
    
    if success:
        return {"status": "sent", "robot_id": command.robot_id, "command": command.command}
    else:
        raise HTTPException(status_code=500, detail="Failed to send command to robot")

@app.get("/telemetry")
async def get_recent_telemetry(limit: int = 50):
    """Get recent telemetry data"""
    recent_data = list(telemetry_history)[-limit:]
    return {"telemetry": recent_data, "count": len(recent_data)}

@app.get("/telemetry/{robot_id}")
async def get_robot_telemetry(robot_id: str, limit: int = 50):
    """Get telemetry data for specific robot"""
    robot_data = [
        record for record in telemetry_history 
        if record.get("robot_id") == robot_id
    ]
    return {"robot_id": robot_id, "telemetry": robot_data[-limit:], "count": len(robot_data)}

@app.get("/health")
async def get_system_health():
    """Get system health status"""
    current_time = time.time()
    return SystemHealth(
        status=system_status,
        connected_robots=len(connected_robots),
        telemetry_records=len(telemetry_history),
        last_update=last_telemetry_update,
        uptime=current_time - system_start_time
    )

@app.post("/emergency_stop")
async def emergency_stop_all():
    """Emergency stop all connected robots"""
    results = {}
    for robot_id in connected_robots.keys():
        command = {"action": "stop", "emergency": True}
        success = await send_command_to_robot(robot_id, command)
        results[robot_id] = "stopped" if success else "failed"
    
    return {"message": "Emergency stop issued", "results": results}

# MCP Integration Functions (called by the chatbot system)

@app.post("/mcp/navigate")
async def mcp_navigate_robot(robot_id: str, destination: str):
    """MCP function: Navigate robot to destination"""
    try:
        # Check if robot exists
        if robot_id not in connected_robots:
            return {"error": f"Robot {robot_id} not found", "status": "failed"}
        
        # Send command
        command = NavigationCommand(
            robot_id=robot_id,
            command="goto",
            parameters={"destination": destination}
        )
        result = await send_navigation_command(command)
        
        # Format response according to MCP spec
        return {
            "status": "success" if result.get("status") == "sent" else "failed",
            "robot_id": robot_id,
            "destination": destination,
            "command_sent": True,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to navigate robot {robot_id}: {e}")
        return {"error": str(e), "status": "failed", "robot_id": robot_id}

@app.post("/mcp/stop")
async def mcp_stop_robot(robot_id: str, emergency: bool = False):
    """MCP function: Stop robot navigation"""
    try:
        # Check if robot exists
        if robot_id not in connected_robots:
            return {"error": f"Robot {robot_id} not found", "status": "failed"}
        
        # Send command
        command = NavigationCommand(
            robot_id=robot_id,
            command="stop",
            parameters={"emergency": emergency}
        )
        result = await send_navigation_command(command)
        
        # Format response according to MCP spec
        return {
            "status": "success" if result.get("status") == "sent" else "failed",
            "robot_id": robot_id,
            "command_sent": True,
            "emergency": emergency,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to stop robot {robot_id}: {e}")
        return {"error": str(e), "status": "failed", "robot_id": robot_id}

@app.get("/mcp/status")
async def mcp_get_robot_status(robot_id: Optional[str] = None):
    """MCP function: Get robot status"""
    try:
        if robot_id:
            # Get specific robot status
            if robot_id not in connected_robots:
                return {"error": f"Robot {robot_id} not found", "status": "failed"}
            
            robot = connected_robots[robot_id]
            return {
                "status": "success",
                "robot": {
                    "robot_id": robot_id,
                    "position": robot["position"],
                    "status": robot["status"],
                    "target_waypoint": robot.get("target_waypoint"),
                    "battery_level": robot["battery_level"],
                    "obstacle_distance": robot["obstacle_distance"],
                    "last_update": robot["last_update"]
                }
            }
        else:
            # Get all robots
            robots = await get_connected_robots()
            return {
                "status": "success",
                "robots": robots["robots"]
            }
            
    except Exception as e:
        logger.error(f"Failed to get robot status: {e}")
        return {"error": str(e), "status": "failed"}

@app.get("/mcp/system_status")
async def mcp_get_system_status():
    """MCP function: Get comprehensive system status"""
    try:
        robots = await get_connected_robots()
        health = await get_system_health()
        
        return {
            "status": "success",
            "system_health": health.dict(),
            "robots": robots["robots"],
            "summary": {
                "total_robots": len(connected_robots),
                "active_robots": len([r for r in connected_robots.values() if r["status"] not in ["idle", "stopped"]]),
                "low_battery_robots": len([r for r in connected_robots.values() if r["battery_level"] < 20]),
                "navigating_robots": len([r for r in connected_robots.values() if r["status"] == "navigating"]),
                "last_telemetry_update": health.last_update,
                "system_uptime": health.uptime
            },
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return {"error": str(e), "status": "failed"}

@app.get("/mcp/history/{robot_id}")
async def mcp_get_robot_history(robot_id: str, limit: int = 20):
    """MCP function: Get robot position history"""
    try:
        if robot_id not in robot_positions:
            return {"error": f"Robot {robot_id} not found", "status": "failed"}
        
        history = list(robot_positions[robot_id])
        return {
            "status": "success",
            "robot_id": robot_id,
            "history": history[-limit:],
            "count": len(history[-limit:]),
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get robot history for {robot_id}: {e}")
        return {"error": str(e), "status": "failed"}

@app.get("/mcp/telemetry")
async def mcp_get_recent_telemetry(robot_id: Optional[str] = None, limit: int = 10):
    """MCP function: Get recent telemetry data"""
    try:
        if robot_id:
            if robot_id not in connected_robots:
                return {"error": f"Robot {robot_id} not found", "status": "failed"}
            
            robot_data = [
                record for record in telemetry_history 
                if record.get("robot_id") == robot_id
            ]
            return {
                "status": "success",
                "robot_id": robot_id,
                "telemetry": robot_data[-limit:],
                "count": len(robot_data[-limit:]),
                "timestamp": datetime.datetime.now().isoformat()
            }
        else:
            recent_data = list(telemetry_history)[-limit:]
            return {
                "status": "success",
                "telemetry": recent_data,
                "count": len(recent_data),
                "timestamp": datetime.datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Failed to get telemetry data: {e}")
        return {"error": str(e), "status": "failed"}

@app.post("/mcp/emergency_stop")
async def mcp_emergency_stop_all():
    """MCP function: Emergency stop all connected robots"""
    try:
        results = {}
        for robot_id in connected_robots.keys():
            command = {"action": "stop", "emergency": True}
            success = await send_command_to_robot(robot_id, command)
            results[robot_id] = "stopped" if success else "failed"
        
        return {
            "status": "completed",
            "message": f"Emergency stop sent to {len(results)} robots",
            "results": results,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to emergency stop all robots: {e}")
        return {"error": str(e), "status": "failed"}

@app.get("/mcp/commands/{robot_id}")
async def mcp_get_robot_commands_queue(robot_id: str):
    """MCP function: Get pending commands for a robot"""
    try:
        if robot_id not in robot_commands:
            return {"error": f"Robot {robot_id} not found", "status": "failed"}
        
        return {
            "status": "success",
            "robot_id": robot_id,
            "pending_commands": robot_commands.get(robot_id, []),
            "count": len(robot_commands.get(robot_id, [])),
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get command queue for {robot_id}: {e}")
        return {"error": str(e), "status": "failed"}

@app.post("/command_log")
async def log_command_to_telemetry(request: Request):
    """Endpoint for logging command execution to telemetry"""
    try:
        log_data = await request.json()
        robot_id = log_data.get("robot_id")
        
        if robot_id not in connected_robots:
            return {"status": "failed", "error": "Robot not found"}
        
        # Store command log (in a real system, this would go to a database)
        if robot_id not in robot_commands:
            robot_commands[robot_id] = []
        
        robot_commands[robot_id].append(log_data)
        return {"status": "logged"}
        
    except Exception as e:
        logger.error(f"Failed to log command: {e}")
        return {"status": "failed", "error": str(e)}

# Background tasks
async def telemetry_simulation_task():
    """Background task to simulate telemetry in demo mode"""
    while system_status == "running":
        if DEMO_MODE:
            simulate_demo_robot_movement()
            
            # Generate telemetry for demo robot
            robot = connected_robots.get("indoor_nav_robot_01")
            if robot:
                telemetry = TelemetryData(
                    timestamp=datetime.datetime.now().isoformat(),
                    robot_id=robot["robot_id"],
                    position=robot["position"],
                    status=robot["status"],
                    target_waypoint=robot.get("target_waypoint"),
                    battery_level=robot["battery_level"],
                    obstacle_distance=robot["obstacle_distance"],
                    lidar_summary={
                        "min_distance": robot["obstacle_distance"] - 1.0,
                        "avg_distance": robot["obstacle_distance"],
                        "max_distance": robot["obstacle_distance"] + 2.0
                    },
                    navigation={
                        "waypoints_remaining": 1 if robot["status"] == "navigating" else 0,
                        "navigation_time": time.time() - robot["last_update"]
                    }
                )
                process_telemetry_data(telemetry)
        
        await asyncio.sleep(TELEMETRY_UPDATE_FREQ)

@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    logger.info("Starting Robot Telemetry Collection System")
    if DEMO_MODE:
        logger.info("Running in DEMO mode - simulating robot telemetry")
        # Start background telemetry simulation
        asyncio.create_task(telemetry_simulation_task())

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global system_status
    system_status = "shutting_down"
    logger.info("Shutting down Robot Telemetry Collection System")

def run_api_server():
    """Run the FastAPI server"""
    uvicorn.run(app, host="0.0.0.0", port=5001, log_level="info")

if __name__ == "__main__":
    print("Starting Robot Telemetry Collection System")
    print(f"Demo Mode: {DEMO_MODE}")
    print("API Server will be available at http://localhost:5001")
    print("API Documentation at http://localhost:5001/docs")
    
    run_api_server()