from datetime import datetime, timedelta
from fastapi import Request
from typing import Dict, List, Any
from rag_store import store_telemetry_vector, search_telemetry_context

class TelemetryHandler:
    """Simplified telemetry handler for robot sensor data"""

    def __init__(self):
        print("✅ TelemetryHandler initialized")

    async def receive_telemetry(self, request: Request) -> Dict[str, Any]:
        """
        Receive telemetry from robot and store in Qdrant
        
        Expected format:
        {
            "robot_id": "robot_1",
            "timestamp": "2024-01-01T12:00:00",
            "position": {"x": 1.5, "y": 2.3},
            "expected_position": {"x": 1.6, "y": 2.4},
            "movement_speed": 0.5,
            "distance_traveled": 0.1,
            "is_stuck": false,
            "current_waypoint": "entrance",
            "target_waypoint": "reception",
            "navigation_status": "navigating",
            "sensor_data": {...}
        }
        """
        try:
            data = await request.json()
            robot_id = data.get("robot_id")
            
            if not robot_id:
                return {"error": "Missing robot_id", "status": "error"}

            # Add timestamp if missing
            if "timestamp" not in data:
                data["timestamp"] = datetime.now().isoformat()

            # Validate and set defaults
            telemetry = self._validate_telemetry(data)
            
            # Store in Qdrant as vector
            vector_id = store_telemetry_vector(robot_id, telemetry)
            
            # Log and check for alerts
            alerts = self._check_alerts(robot_id, telemetry)
            self._log_telemetry(robot_id, telemetry, alerts)
            
            return {
                "status": "success",
                "robot_id": robot_id,
                "vector_id": vector_id,
                "alerts": alerts,
                "timestamp": telemetry["timestamp"]
            }

        except Exception as e:
            print(f"[TELEMETRY ERROR] {e}")
            return {"error": str(e), "status": "error"}

    def _validate_telemetry(self, data: Dict) -> Dict:
        """Validate and set defaults for telemetry data"""
        defaults = {
            "position": {"x": 0.0, "y": 0.0},
            "expected_position": {"x": 0.0, "y": 0.0},
            "movement_speed": 0.0,
            "distance_traveled": 0.0,
            "is_stuck": False,
            "current_waypoint": None,
            "target_waypoint": None,
            "navigation_status": "unknown",
            "sensor_data": {}
        }
        
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
        
        return data

    def _check_alerts(self, robot_id: str, telemetry: Dict) -> List[Dict]:
        """Check for alert conditions"""
        alerts = []
        
        if telemetry.get("is_stuck"):
            alerts.append({
                "type": "stuck_robot",
                "priority": "high",
                "message": f"Robot {robot_id} is stuck"
            })
        
        # Check position error
        pos = telemetry.get("position", {})
        exp_pos = telemetry.get("expected_position", {})
        pos_error = ((pos.get("x", 0) - exp_pos.get("x", 0))**2 + 
                     (pos.get("y", 0) - exp_pos.get("y", 0))**2)**0.5
        
        if pos_error > 1.0:  # 1 meter threshold
            alerts.append({
                "type": "position_error", 
                "priority": "medium",
                "message": f"Robot {robot_id} position error: {pos_error:.2f}m"
            })
        
        return alerts

    def _log_telemetry(self, robot_id: str, telemetry: Dict, alerts: List):
        """Log telemetry reception"""
        pos = telemetry.get("position", {})
        status_emoji = "🔴" if telemetry.get("is_stuck") else "🟢"
        
        print(f"[TELEMETRY] {status_emoji} {robot_id} at ({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f})")
        
        for alert in alerts:
            print(f"  ⚠️ {alert['priority'].upper()}: {alert['message']}")

    async def get_robot_status(self, robot_id: str = None) -> Dict[str, Any]:
        """Get current robot status from recent telemetry"""
        try:
            # Search for recent telemetry
            if robot_id:
                query = f"Robot {robot_id} current status position navigation"
            else:
                query = "robot status position navigation current"
            
            recent_telemetry = search_telemetry_context(query, robot_id, limit=10)
            
            # Group by robot_id and get most recent for each
            robot_status = {}
            for tel in recent_telemetry:
                rid = tel["robot_id"]
                if rid not in robot_status:
                    robot_status[rid] = tel
            
            return {
                "timestamp": datetime.now().isoformat(),
                "robots": list(robot_status.values()),
                "total_robots": len(robot_status)
            }
            
        except Exception as e:
            print(f"[STATUS ERROR] {e}")
            return {"error": str(e)}
        
    async def get_telemetry_status(self) -> Dict[str, Any]:
        """Get current status of all robots"""
        return await self.get_robot_status()  # Reuse existing method

    async def get_robot_telemetry(self, robot_id: str, hours: int = 1) -> Dict[str, Any]:
        """Get telemetry history for specific robot"""
        try:
            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            # Search for telemetry in time range
            query = f"Robot {robot_id} telemetry history position navigation"
            telemetry_data = search_telemetry_context(query, robot_id, limit=50)
            
            # Filter by time range (if timestamp parsing is needed)
            filtered_data = []
            for tel in telemetry_data:
                try:
                    tel_time = datetime.fromisoformat(tel["timestamp"].replace('Z', '+00:00'))
                    if start_time <= tel_time <= end_time:
                        filtered_data.append(tel)
                except:
                    # Include if timestamp parsing fails
                    filtered_data.append(tel)
            
            return {
                "robot_id": robot_id,
                "hours_requested": hours,
                "data_points": len(filtered_data),
                "telemetry": filtered_data[:20]  # Limit response size
            }
            
        except Exception as e:
            print(f"[TELEMETRY HISTORY ERROR] {e}")
            return {"error": str(e)}

    async def get_qdrant_logs(self) -> Dict[str, Any]:
        """Get Qdrant vector database logs"""
        try:
            # This would typically interface with Qdrant's logging
            # For now, return status info
            from qdrant_client import QdrantClient
            client = QdrantClient(host="localhost", port=6333)
            
            collections = client.get_collections()
            collection_info = []
            
            for collection in collections.collections:
                info = client.get_collection(collection.name)
                collection_info.append({
                    "name": collection.name,
                    "vectors_count": info.vectors_count,
                    "status": info.status
                })
            
            return {
                "status": "connected",
                "collections": collection_info
            }
            
        except Exception as e:
            return {"error": str(e), "status": "error"}

    async def get_postgres_logs(self) -> Dict[str, Any]:
        """Get PostgreSQL database logs"""
        try:
            # Get recent chat message stats
            from rag_store import DB_CONFIG
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_messages,
                            COUNT(DISTINCT user_id) as unique_users,
                            MAX(timestamp) as last_message
                        FROM chat_messages;
                    """)
                    stats = dict(cur.fetchone())
            
            return {
                "status": "connected",
                "database": DB_CONFIG["dbname"],
                "stats": stats
            }
            
        except Exception as e:
            return {"error": str(e), "status": "error"}

    async def get_current_robot_status(self) -> Dict[str, Any]:
        """Get current status of all robots (for MCP tool)"""
        return await self.get_robot_status()