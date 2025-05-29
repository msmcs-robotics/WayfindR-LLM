# telemetry_handler.py - Updated
from datetime import datetime
from fastapi import Request
from typing import Dict, Any, Optional, List
from utils import success_response, error_response
from db_manager import get_db_manager
from config_manager import get_config

class TelemetryHandler:
    """Handle robot telemetry reception and status queries"""
    
    def __init__(self):
        self.config = get_config()
        self.db = get_db_manager()
        print("✅ TelemetryHandler initialized")
    
    async def receive_telemetry(self, request: Request) -> Dict[str, Any]:
        """Receive and store robot telemetry data"""
        try:
            data = await request.json()
            robot_id = data.get('robot_id')
            telemetry_data = data.get('telemetry', {})
            
            if not robot_id:
                return error_response("Missing robot_id")
            
            if not telemetry_data:
                return error_response("Missing telemetry data")
            
            # Add timestamp if not provided
            if 'timestamp' not in telemetry_data:
                telemetry_data['timestamp'] = datetime.now().isoformat()
            
            print(f"📡 Telemetry from {robot_id}: {telemetry_data.get('navigation_status', 'unknown')}")
            
            # Store telemetry as vector in Qdrant
            point_id = self.db.store_telemetry(robot_id, telemetry_data)
            
            if point_id:
                return success_response({
                    "robot_id": robot_id,
                    "point_id": point_id,
                    "timestamp": telemetry_data['timestamp'],
                    "status": "stored"
                })
            else:
                return error_response("Failed to store telemetry")
                
        except Exception as e:
            print(f"❌ Telemetry reception error: {e}")
            return error_response(str(e))
    
    async def get_robot_status(self, robot_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current status of robots"""
        try:
            if robot_id:
                # Get specific robot status
                telemetry_records = self._get_robot_telemetry_by_id(robot_id, limit=1)
                
                if telemetry_records:
                    record = telemetry_records[0]
                    return success_response({
                        "robot_id": robot_id,
                        "status": "active",
                        "last_update": record["timestamp"],
                        "telemetry": record["telemetry"]
                    })
                else:
                    return success_response({
                        "robot_id": robot_id,
                        "status": "inactive",
                        "message": "No recent telemetry data"
                    })
            else:
                # Get all active robots
                active_robots = self.db.get_active_robots(hours=self.config.system.telemetry_retention_hours)
                
                robot_statuses = []
                for rid in active_robots:
                    records = self._get_robot_telemetry_by_id(rid, limit=1)
                    if records:
                        robot_statuses.append({
                            "robot_id": rid,
                            "status": "active",
                            "last_update": records[0]["timestamp"],
                            "telemetry": records[0]["telemetry"]
                        })
                
                return success_response({
                    "active_robot_count": len(active_robots),
                    "robots": robot_statuses,
                    "timestamp": datetime.now().isoformat()
                })
                
        except Exception as e:
            print(f"❌ Get robot status error: {e}")
            return error_response(str(e))
    
    def _get_robot_telemetry_by_id(self, robot_id: str, limit: int = 1) -> List[Dict]:
        """Helper method to get robot telemetry"""
        try:
            # This would need to be implemented in DatabaseManager
            # For now using a placeholder implementation
            return self.db.get_robot_telemetry(robot_id, limit)
        except Exception as e:
            print(f"❌ Error getting telemetry for {robot_id}: {e}")
            return []