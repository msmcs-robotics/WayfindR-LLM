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
        """Get Qdrant vector database logs - FIXED to return records format expected by frontend"""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Filter
            
            client = QdrantClient(host="localhost", port=6333)
            
            # Get recent telemetry records from Qdrant
            try:
                # Get collection info
                collection_info = client.get_collection("robot_telemetry")
                
                # Use scroll to get recent points instead of search
                scroll_result = client.scroll(
                    collection_name="robot_telemetry",
                    limit=20,  # Get last 20 records
                    with_payload=True,
                    with_vectors=False
                )
                
                records = []
                for point in scroll_result[0]:  # scroll returns (points, next_page_offset)
                    # Format as expected by frontend
                    record = {
                        "id": str(point.id),
                        "payload": point.payload
                    }
                    records.append(record)
                
                return {
                    "status": "success",
                    "records": records,
                    "total_points": collection_info.vectors_count,
                    "collection_status": "healthy"
                }
                
            except Exception as collection_error:
                print(f"[QDRANT COLLECTION ERROR] {collection_error}")
                return {
                    "status": "error", 
                    "records": [],
                    "error": f"Collection error: {collection_error}"
                }
            
        except Exception as e:
            print(f"[QDRANT CONNECTION ERROR] {e}")
            return {
                "status": "error",
                "records": [],
                "error": f"Connection error: {e}"
            }

    async def get_postgres_logs(self) -> Dict[str, Any]:
        """Get PostgreSQL database logs - FIXED to return correct data from chat_messages table"""
        try:
            from rag_store import DB_CONFIG
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
                with conn.cursor() as cur:
                    # Get recent chat messages (these are the actual PostgreSQL records)
                    cur.execute("""
                        SELECT 
                            id,
                            role,
                            content,
                            timestamp,
                            user_id,
                            metadata
                        FROM chat_messages 
                        ORDER BY timestamp DESC 
                        LIMIT 20;
                    """)
                    
                    chat_records = []
                    for row in cur.fetchall():
                        # Format for frontend display as "message chains"
                        record = [
                            str(row['id']),
                            {
                                "role": row['role'],
                                "content": row['content'][:200] + "..." if len(row['content']) > 200 else row['content'],
                                "user_id": row['user_id'],
                                "metadata": row['metadata']
                            },
                            {},  # Empty relationships field
                            row['timestamp'].isoformat() if row['timestamp'] else datetime.now().isoformat()
                        ]
                        chat_records.append(record)
                    
                    # Get summary stats
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_messages,
                            COUNT(DISTINCT user_id) as unique_users,
                            MAX(timestamp) as last_message
                        FROM chat_messages;
                    """)
                    stats = dict(cur.fetchone())
                    
                    return {
                        "status": "success",
                        "message_chains": chat_records,
                        "relationships": [],  # No relationships in our simple schema
                        "stats": {
                            "total_messages": stats['total_messages'],
                            "unique_users": stats['unique_users'],
                            "last_message": stats['last_message'].isoformat() if stats['last_message'] else None
                        }
                    }
            
        except Exception as e:
            print(f"[POSTGRES ERROR] {e}")
            return {
                "status": "error",
                "message_chains": [],
                "relationships": [],
                "error": str(e)
            }

    async def get_current_robot_status(self) -> Dict[str, Any]:
        """Get current status of all robots (for MCP tool)"""
        return await self.get_robot_status()