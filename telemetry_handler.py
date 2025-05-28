from datetime import datetime
from fastapi import Request
from typing import Dict, Any
from rag_store import store_telemetry_vector, get_robot_status

class TelemetryHandler:
    """Simplified telemetry handler for robot sensor data"""

    def __init__(self):
        print("✅ TelemetryHandler initialized")

    async def receive_telemetry(self, request: Request) -> Dict[str, Any]:
        """Receive and store robot telemetry"""
        try:
            data = await request.json()
            robot_id = data.get("robot_id")
            
            if not robot_id:
                return {"error": "Missing robot_id", "status": "error"}

            # Add timestamp if missing
            if "timestamp" not in data:
                data["timestamp"] = datetime.now().isoformat()

            # Store in Qdrant as vector
            vector_id = store_telemetry_vector(robot_id, data)
            
            # Check for stuck condition
            is_stuck = data.get("is_stuck", False)
            if is_stuck:
                print(f"🚨 Robot {robot_id} reports stuck status")
            
            # Log basic telemetry
            pos = data.get("position", {})
            status = data.get("navigation_status", "unknown")
            print(f"📡 {robot_id} at ({pos.get('x', 0):.1f}, {pos.get('y', 0):.1f}) - {status}")
            
            return {
                "status": "success",
                "robot_id": robot_id,
                "vector_id": vector_id,
                "is_stuck": is_stuck,
                "timestamp": data["timestamp"]
            }

        except Exception as e:
            print(f"❌ Telemetry error: {e}")
            return {"error": str(e), "status": "error"}

    async def get_robot_status(self, robot_id: str = None) -> Dict[str, Any]:
        """Get current robot status"""
        try:
            robots = get_robot_status(robot_id)
            
            return {
                "timestamp": datetime.now().isoformat(),
                "robots": robots,
                "total_robots": len(robots),
                "success": True
            }
            
        except Exception as e:
            print(f"❌ Status error: {e}")
            return {"error": str(e), "success": False}