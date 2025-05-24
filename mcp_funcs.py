"""
Complete MCP Functions Implementation for Robot Navigation System

This module provides the complete MCP function implementation that integrates
with the telemetry collection system and handles robot command delegation.
"""

import requests
import json
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import time

logger = logging.getLogger(__name__)

# Configuration
TELEMETRY_SYSTEM_URL = "http://localhost:5001"  # URL of the telemetry collection system
RASPBERRY_PI_BASE_URL = "http://192.168.1.100:5000"  # Default Pi address - configurable
REQUEST_TIMEOUT = 10  # seconds

class RobotControlMCP:
    """Complete MCP functions for robot control and monitoring"""
    
    def __init__(self, telemetry_url: str = TELEMETRY_SYSTEM_URL, pi_url: str = RASPBERRY_PI_BASE_URL):
        self.telemetry_url = telemetry_url
        self.pi_base_url = pi_url
    
    async def navigate_robot(self, robot_id: str, destination: str) -> Dict[str, Any]:
        """
        Navigate robot to a specific destination
        
        Args:
            robot_id: Identifier of the robot to control
            destination: Name of the destination (e.g., "kitchen", "bedroom1", "home")
        
        Returns:
            Dictionary with command result
        """
        try:
            # First check if robot exists in telemetry system
            robot_status = await self._get_robot_from_telemetry(robot_id)
            if not robot_status:
                return {"error": f"Robot {robot_id} not found", "status": "failed"}
            
            # Send command directly to Raspberry Pi
            command = {
                "action": "goto",
                "dest": destination,
                "robot_id": robot_id,
                "timestamp": datetime.now().isoformat()
            }
            
            pi_result = await self._send_command_to_pi(robot_id, command)
            
            # Also notify telemetry system about the command
            await self._log_command_to_telemetry(robot_id, command, pi_result)
            
            return {
                "status": "success" if pi_result.get("success") else "failed",
                "robot_id": robot_id,
                "destination": destination,
                "command_sent": True,
                "pi_response": pi_result,
                "timestamp": command["timestamp"]
            }
            
        except Exception as e:
            logger.error(f"Failed to navigate robot {robot_id} to {destination}: {e}")
            return {"error": str(e), "status": "failed", "robot_id": robot_id}
    
    async def stop_robot(self, robot_id: str) -> Dict[str, Any]:
        """
        Stop robot navigation immediately
        
        Args:
            robot_id: Identifier of the robot to stop
        
        Returns:
            Dictionary with command result
        """
        try:
            # Check if robot exists
            robot_status = await self._get_robot_from_telemetry(robot_id)
            if not robot_status:
                return {"error": f"Robot {robot_id} not found", "status": "failed"}
            
            # Send stop command to Pi
            command = {
                "action": "stop",
                "robot_id": robot_id,
                "emergency": False,  # Regular stop, not emergency
                "timestamp": datetime.now().isoformat()
            }
            
            pi_result = await self._send_command_to_pi(robot_id, command)
            
            # Log command to telemetry
            await self._log_command_to_telemetry(robot_id, command, pi_result)
            
            return {
                "status": "success" if pi_result.get("success") else "failed",
                "robot_id": robot_id,
                "command_sent": True,
                "pi_response": pi_result,
                "timestamp": command["timestamp"]
            }
            
        except Exception as e:
            logger.error(f"Failed to stop robot {robot_id}: {e}")
            return {"error": str(e), "status": "failed", "robot_id": robot_id}
    
    async def get_robot_status(self, robot_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current status of robot(s) from telemetry system
        
        Args:
            robot_id: Specific robot ID, or None for all robots
        
        Returns:
            Dictionary with robot status information
        """
        try:
            if robot_id:
                # Get specific robot status
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                    async with session.get(f"{self.telemetry_url}/robots/{robot_id}") as response:
                        if response.status == 200:
                            data = await response.json()
                            return {"status": "success", "robot": data}
                        elif response.status == 404:
                            return {"error": f"Robot {robot_id} not found", "status": "failed"}
                        else:
                            return {"error": f"HTTP {response.status}", "status": "failed"}
            else:
                # Get all robots
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                    async with session.get(f"{self.telemetry_url}/robots") as response:
                        if response.status == 200:
                            data = await response.json()
                            return {"status": "success", "robots": data.get("robots", [])}
                        else:
                            return {"error": f"HTTP {response.status}", "status": "failed"}
                            
        except Exception as e:
            logger.error(f"Failed to get robot status: {e}")
            return {"error": str(e), "status": "failed"}
    
    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status including all robots and health metrics
        
        Returns:
            Dictionary with system status
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                # Get system health
                async with session.get(f"{self.telemetry_url}/health") as response:
                    if response.status != 200:
                        return {"error": f"Failed to get system health: HTTP {response.status}", "status": "failed"}
                    health_data = await response.json()
                
                # Get all robots
                async with session.get(f"{self.telemetry_url}/robots") as response:
                    if response.status != 200:
                        return {"error": f"Failed to get robots: HTTP {response.status}", "status": "failed"}
                    robots_data = await response.json()
                
                # Compile comprehensive status
                robots = robots_data.get("robots", [])
                return {
                    "status": "success",
                    "system_health": health_data,
                    "robots": robots,
                    "summary": {
                        "total_robots": len(robots),
                        "active_robots": len([r for r in robots if r.get("status") not in ["idle", "stopped"]]),
                        "low_battery_robots": len([r for r in robots if r.get("battery", 100) < 20]),
                        "navigating_robots": len([r for r in robots if r.get("status") == "navigating"]),
                        "last_telemetry_update": health_data.get("last_update", 0),
                        "system_uptime": health_data.get("uptime", 0)
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {"error": str(e), "status": "failed"}
    
    async def get_robot_history(self, robot_id: str, limit: int = 20) -> Dict[str, Any]:
        """
        Get recent position history for a robot
        
        Args:
            robot_id: Identifier of the robot
            limit: Number of recent positions to retrieve
        
        Returns:
            Dictionary with position history
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                async with session.get(
                    f"{self.telemetry_url}/robots/{robot_id}/history",
                    params={"limit": limit}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": "success",
                            "robot_id": robot_id,
                            "history": data.get("history", []),
                            "count": len(data.get("history", [])),
                            "timestamp": datetime.now().isoformat()
                        }
                    elif response.status == 404:
                        return {"error": f"Robot {robot_id} not found", "status": "failed"}
                    else:
                        return {"error": f"HTTP {response.status}", "status": "failed"}
                        
        except Exception as e:
            logger.error(f"Failed to get robot history for {robot_id}: {e}")
            return {"error": str(e), "status": "failed"}
    
    async def get_recent_telemetry(self, robot_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """
        Get recent telemetry data
        
        Args:
            robot_id: Specific robot ID, or None for all robots
            limit: Number of recent telemetry records
        
        Returns:
            Dictionary with telemetry data
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                if robot_id:
                    url = f"{self.telemetry_url}/telemetry/{robot_id}"
                else:
                    url = f"{self.telemetry_url}/telemetry"
                
                async with session.get(url, params={"limit": limit}) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": "success",
                            "robot_id": robot_id,
                            "telemetry": data.get("telemetry", []),
                            "count": data.get("count", 0),
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        return {"error": f"HTTP {response.status}", "status": "failed"}
                        
        except Exception as e:
            logger.error(f"Failed to get telemetry data: {e}")
            return {"error": str(e), "status": "failed"}
    
    async def emergency_stop_all(self) -> Dict[str, Any]:
        """
        Emergency stop all connected robots
        
        Returns:
            Dictionary with emergency stop results
        """
        try:
            # First get list of all robots
            robots_result = await self.get_robot_status()
            if robots_result.get("status") != "success":
                return {"error": "Failed to get robot list", "status": "failed"}
            
            robots = robots_result.get("robots", [])
            if not robots:
                return {"message": "No robots connected", "status": "success", "results": {}}
            
            # Send emergency stop to each robot
            results = {}
            for robot_data in robots:
                robot_id = robot_data.get("robot_id")
                if robot_id:
                    try:
                        command = {
                            "action": "stop",
                            "robot_id": robot_id,
                            "emergency": True,
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        pi_result = await self._send_command_to_pi(robot_id, command)
                        results[robot_id] = "stopped" if pi_result.get("success") else "failed"
                        
                        # Log emergency stop command
                        await self._log_command_to_telemetry(robot_id, command, pi_result)
                        
                    except Exception as e:
                        logger.error(f"Failed to emergency stop {robot_id}: {e}")
                        results[robot_id] = f"error: {str(e)}"
            
            # Also notify telemetry system
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                    async with session.post(f"{self.telemetry_url}/emergency_stop") as response:
                        pass  # We don't need to wait for this response
            except:
                pass  # Non-critical if telemetry system doesn't respond
            
            return {
                "status": "completed",
                "message": f"Emergency stop sent to {len(results)} robots",
                "results": results,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to emergency stop all robots: {e}")
            return {"error": str(e), "status": "failed"}
    
    async def get_robot_commands_queue(self, robot_id: str) -> Dict[str, Any]:
        """
        Get pending commands for a specific robot (new function)
        
        Args:
            robot_id: Identifier of the robot
        
        Returns:
            Dictionary with pending commands
        """
        try:
            # This would query the telemetry system for any queued commands
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                async with session.get(f"{self.telemetry_url}/robots/{robot_id}/commands") as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": "success",
                            "robot_id": robot_id,
                            "pending_commands": data.get("commands", []),
                            "count": len(data.get("commands", [])),
                            "timestamp": datetime.now().isoformat()
                        }
                    elif response.status == 404:
                        return {"error": f"Robot {robot_id} not found", "status": "failed"}
                    else:
                        return {"error": f"HTTP {response.status}", "status": "failed"}
                        
        except Exception as e:
            logger.error(f"Failed to get command queue for {robot_id}: {e}")
            return {"error": str(e), "status": "failed"}
    
    # Helper methods
    
    async def _get_robot_from_telemetry(self, robot_id: str) -> Optional[Dict]:
        """Get robot info from telemetry system"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                async with session.get(f"{self.telemetry_url}/robots/{robot_id}") as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as e:
            logger.error(f"Failed to get robot from telemetry: {e}")
            return None
    
    async def _send_command_to_pi(self, robot_id: str, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send command directly to Raspberry Pi"""
        try:
            # In production, you might have different URLs per robot
            # For now, using the configured base URL
            pi_url = f"{self.pi_base_url}/command"
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                async with session.post(pi_url, json=command) as response:
                    if response.status == 200:
                        result = await response.json()
                        return {"success": True, "response": result}
                    else:
                        error_text = await response.text()
                        return {"success": False, "error": f"HTTP {response.status}: {error_text}"}
                        
        except Exception as e:
            logger.error(f"Failed to send command to Pi: {e}")
            return {"success": False, "error": str(e)}
    
    async def _log_command_to_telemetry(self, robot_id: str, command: Dict[str, Any], result: Dict[str, Any]):
        """Log command execution to telemetry system"""
        try:
            log_data = {
                "robot_id": robot_id,
                "command": command,
                "result": result,
                "timestamp": datetime.now().isoformat()
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.post(f"{self.telemetry_url}/command_log", json=log_data) as response:
                    pass  # We don't need to wait for response, this is just logging
                    
        except Exception as e:
            logger.warning(f"Failed to log command to telemetry: {e}")

# MCP Function Registry with enhanced function definitions
MCP_FUNCTIONS = {
    "navigate_robot": {
        "description": "Navigate a robot to a specific destination using its built-in SLAM and pathfinding",
        "parameters": {
            "type": "object",
            "properties": {
                "robot_id": {
                    "type": "string",
                    "description": "The ID of the robot to control (e.g., 'indoor_nav_robot_01')"
                },
                "destination": {
                    "type": "string",
                    "description": "The destination waypoint name (e.g., 'kitchen', 'bedroom1', 'home', 'office', 'living_room')"
                }
            },
            "required": ["robot_id", "destination"]
        }
    },
    
    "stop_robot": {
        "description": "Stop a robot's current navigation and movement",
        "parameters": {
            "type": "object",
            "properties": {
                "robot_id": {
                    "type": "string",
                    "description": "The ID of the robot to stop"
                }
            },
            "required": ["robot_id"]
        }
    },
    
    "get_robot_status": {
        "description": "Get the current status, position, and battery level of a robot or all robots",
        "parameters": {
            "type": "object",
            "properties": {
                "robot_id": {
                    "type": "string",
                    "description": "The ID of a specific robot, or omit to get status of all robots"
                }
            },
            "required": []
        }
    },
    
    "get_system_status": {
        "description": "Get comprehensive system status including all robots, health metrics, and summary statistics",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    
    "get_robot_history": {
        "description": "Get recent position history and movement path for a robot",
        "parameters": {
            "type": "object",
            "properties": {
                "robot_id": {
                    "type": "string",
                    "description": "The ID of the robot"
                },
                "limit": {
                    "type": "integer", 
                    "description": "Number of recent positions to retrieve (default: 20, max: 100)"
                }
            },
            "required": ["robot_id"]
        }
    },
    
    "get_recent_telemetry": {
        "description": "Get recent telemetry data including sensor readings, navigation status, and system metrics",
        "parameters": {
            "type": "object",
            "properties": {
                "robot_id": {
                    "type": "string",
                    "description": "The ID of a specific robot, or omit to get telemetry from all robots"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recent telemetry records (default: 10, max: 50)"
                }
            },
            "required": []
        }
    },
    
    "emergency_stop_all": {
        "description": "Emergency stop all connected robots immediately - use only in emergency situations",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    
    "get_robot_commands_queue": {
        "description": "Get pending commands for a specific robot",
        "parameters": {
            "type": "object",
            "properties": {
                "robot_id": {
                    "type": "string",
                    "description": "The ID of the robot"
                }
            },
            "required": ["robot_id"]
        }
    }
}

# Function execution mapping
async def execute_mcp_function(function_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an MCP function with given parameters
    
    Args:
        function_name: Name of the function to execute
        parameters: Parameters to pass to the function
    
    Returns:
        Result of the function execution
    """
    robot_control = RobotControlMCP()
    
    try:
        if function_name == "navigate_robot":
            return await robot_control.navigate_robot(
                robot_id=parameters["robot_id"],
                destination=parameters["destination"]
            )
        
        elif function_name == "stop_robot":
            return await robot_control.stop_robot(
                robot_id=parameters["robot_id"]
            )
        
        elif function_name == "get_robot_status":
            return await robot_control.get_robot_status(
                robot_id=parameters.get("robot_id")
            )
        
        elif function_name == "get_system_status":
            return await robot_control.get_system_status()
        
        elif function_name == "get_robot_history":
            return await robot_control.get_robot_history(
                robot_id=parameters["robot_id"],
                limit=min(parameters.get("limit", 20), 100)  # Cap at 100
            )
        
        elif function_name == "get_recent_telemetry":
            return await robot_control.get_recent_telemetry(
                robot_id=parameters.get("robot_id"),
                limit=min(parameters.get("limit", 10), 50)  # Cap at 50
            )
        
        elif function_name == "emergency_stop_all":
            return await robot_control.emergency_stop_all()
        
        elif function_name == "get_robot_commands_queue":
            return await robot_control.get_robot_commands_queue(
                robot_id=parameters["robot_id"]
            )
        
        else:
            return {"error": f"Unknown function: {function_name}", "status": "failed"}
            
    except Exception as e:
        logger.error(f"Error executing MCP function {function_name}: {e}")
        return {"error": f"Function execution failed: {str(e)}", "status": "failed"}

# Convenience function for MCP-enabled chatbot integration
async def handle_mcp_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle an MCP request with error handling and logging
    
    Args:
        request_data: Dictionary containing 'function' and 'parameters' keys
    
    Returns:
        Result of the function call with metadata
    """
    start_time = time.time()
    
    try:
        function_name = request_data.get("function")
        parameters = request_data.get("parameters", {})
        
        if not function_name:
            return {"error": "Missing 'function' in request", "status": "failed"}
        
        if function_name not in MCP_FUNCTIONS:
            return {"error": f"Unknown function: {function_name}", "status": "failed"}
        
        logger.info(f"Executing MCP function: {function_name} with parameters: {parameters}")
        
        result = await execute_mcp_function(function_name, parameters)
        
        execution_time = time.time() - start_time
        logger.info(f"MCP function {function_name} completed in {execution_time:.2f}s")
        
        # Add metadata to result
        if isinstance(result, dict):
            result["execution_time"] = execution_time
            result["function_name"] = function_name
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"MCP request failed after {execution_time:.2f}s: {e}")
        return {
            "error": f"MCP request failed: {str(e)}",
            "status": "failed",
            "execution_time": execution_time
        }

# Example usage for testing
if __name__ == "__main__":
    async def test_mcp_functions():
        """Test the MCP functions"""
        # Test system status
        print("Testing system status...")
        result = await execute_mcp_function("get_system_status", {})
        print(f"System status: {result}")
        
        # Test robot status
        print("\nTesting robot status...")
        result = await execute_mcp_function("get_robot_status", {"robot_id": "indoor_nav_robot_01"})
        print(f"Robot status: {result}")
        
        # Test navigation command
        print("\nTesting navigation command...")
        result = await execute_mcp_function("navigate_robot", {
            "robot_id": "indoor_nav_robot_01",
            "destination": "kitchen"
        })
        print(f"Navigation result: {result}")
    
    # Run tests
    asyncio.run(test_mcp_functions())