import traceback
import json
from datetime import datetime, timedelta
from fastapi import Request
from typing import Dict, List, Optional, Any
from rag_store import (
    add_robot_telemetry,
    get_stuck_robots,
    build_comprehensive_context,
    get_recent_telemetry_context,
    add_mcp_message
)

class TelemetryHandler:
    """Enhanced telemetry handler with improved processing and context building"""

    def __init__(self):
        self.db_config = {
            "dbname": "rag_db",
            "user": "postgres", 
            "password": "password",
            "host": "localhost",
            "port": "5432"
        }
        print("✅ TelemetryHandler initialized")

    # ─── TELEMETRY RECEPTION AND PROCESSING ───────────────

    async def receive_telemetry(self, request: Request) -> Dict[str, Any]:
        """
        Receive and process telemetry data from robots.
        
        Expected payload:
        {
            "robot_id": "robot_1",
            "telemetry": {
                "timestamp": "2024-01-01T12:00:00",
                "position": {"x": 1.5, "y": 2.3},
                "expected_position": {"x": 1.6, "y": 2.4},
                "movement_speed": 0.5,
                "distance_traveled": 0.1,
                "is_stuck": False,
                "current_waypoint": "entrance",
                "target_waypoint": "reception", 
                "navigation_status": "navigating",
                "sensor_summary": {
                    "obstacles_detected": 2,
                    "closest_obstacle_distance": 1.2,
                    "path_blocked": False,
                    "position_accuracy": 0.05,
                    "imu_stable": True
                }
            }
        }
        """
        try:
            data = await request.json()
            robot_id = data.get("robot_id")
            telemetry_data = data.get("telemetry")
            
            if not robot_id or not telemetry_data:
                return {
                    "error": "Missing robot_id or telemetry data", 
                    "status": "error"
                }

            # Validate and enhance telemetry data
            processed_telemetry = self._process_telemetry_data(telemetry_data)
            
            # Store in RAG system (both PostgreSQL and Qdrant)
            telemetry_id = add_robot_telemetry(robot_id, processed_telemetry)
            
            # Check for critical situations requiring immediate attention
            alerts = self._analyze_telemetry_for_alerts(robot_id, processed_telemetry)
            
            # Log telemetry reception
            self._log_telemetry_event(robot_id, processed_telemetry, alerts)
            
            response = {
                "status": "success",
                "telemetry_id": telemetry_id,
                "robot_id": robot_id,
                "timestamp": processed_telemetry.get("timestamp"),
                "alerts": alerts
            }
            
            return response

        except Exception as e:
            print(f"[TELEMETRY ERROR] {e}")
            traceback.print_exc()
            return {"error": str(e), "status": "error"}

    def _process_telemetry_data(self, telemetry_data: Dict) -> Dict:
        """Process and validate incoming telemetry data"""
        # Ensure timestamp is present
        if "timestamp" not in telemetry_data:
            telemetry_data["timestamp"] = datetime.now().isoformat()
        
        # Ensure required fields have defaults
        defaults = {
            "movement_speed": 0.0,
            "distance_traveled": 0.0,
            "is_stuck": False,
            "navigation_status": "unknown",
            "position": {"x": 0.0, "y": 0.0},
            "expected_position": {"x": 0.0, "y": 0.0},
            "sensor_summary": {}
        }
        
        for key, default_value in defaults.items():
            if key not in telemetry_data:
                telemetry_data[key] = default_value
        
        # Calculate derived metrics
        telemetry_data = self._calculate_derived_metrics(telemetry_data)
        
        return telemetry_data

    def _calculate_derived_metrics(self, telemetry_data: Dict) -> Dict:
        """Calculate additional metrics from telemetry data"""
        pos = telemetry_data.get("position", {})
        expected_pos = telemetry_data.get("expected_position", {})
        
        # Calculate position error
        if pos and expected_pos:
            position_error = ((pos.get("x", 0) - expected_pos.get("x", 0))**2 + 
                            (pos.get("y", 0) - expected_pos.get("y", 0))**2)**0.5
            telemetry_data["position_error"] = round(position_error, 3)
        
        # Determine if robot is making progress
        speed = telemetry_data.get("movement_speed", 0)
        telemetry_data["making_progress"] = speed > 0.01  # 1cm/s threshold
        
        # Enhanced stuck detection
        if not telemetry_data.get("making_progress") and telemetry_data.get("target_waypoint"):
            sensor_summary = telemetry_data.get("sensor_summary", {})
            if sensor_summary.get("path_blocked", False) or telemetry_data.get("position_error", 0) > 0.5:
                telemetry_data["is_stuck"] = True
        
        return telemetry_data

    def _analyze_telemetry_for_alerts(self, robot_id: str, telemetry_data: Dict) -> List[Dict]:
        """Analyze telemetry for situations requiring immediate attention"""
        alerts = []
        
        # Stuck robot alert
        if telemetry_data.get("is_stuck"):
            alerts.append({
                "type": "stuck_robot",
                "priority": "high",
                "message": f"Robot {robot_id} is stuck and needs assistance",
                "current_waypoint": telemetry_data.get("current_waypoint"),
                "target_waypoint": telemetry_data.get("target_waypoint")
            })
        
        # High position error alert
        if telemetry_data.get("position_error", 0) > 1.0:  # 1 meter threshold
            alerts.append({
                "type": "position_error",
                "priority": "medium", 
                "message": f"Robot {robot_id} has high position error: {telemetry_data['position_error']:.2f}m"
            })
        
        # Obstacle detection alert
        sensor_summary = telemetry_data.get("sensor_summary", {})
        if sensor_summary.get("path_blocked"):
            alerts.append({
                "type": "path_blocked",
                "priority": "medium",
                "message": f"Robot {robot_id} path is blocked by obstacles"
            })
        
        return alerts

    def _log_telemetry_event(self, robot_id: str, telemetry_data: Dict, alerts: List[Dict]):
        """Log telemetry reception event"""
        status_emoji = "🔴" if telemetry_data.get("is_stuck") else "🟢"
        pos = telemetry_data.get("position", {})
        
        print(f"[TELEMETRY] {status_emoji} {robot_id} at ({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f})")
        
        if alerts:
            for alert in alerts:
                print(f"  ⚠️  {alert['priority'].upper()}: {alert['message']}")
        
        # Log to RAG system for context building
        add_mcp_message({
            "role": "system",
            "timestamp": datetime.now().isoformat(),
            "agent_id": robot_id,
            "source": "telemetry_reception",
            "message": f"Telemetry received: {telemetry_data.get('navigation_status', 'unknown')} status",
            "telemetry_summary": {
                "position": telemetry_data.get("position"),
                "is_stuck": telemetry_data.get("is_stuck"),
                "current_waypoint": telemetry_data.get("current_waypoint"),
                "target_waypoint": telemetry_data.get("target_waypoint")
            },
            "alerts": alerts
        })

    # ─── STATUS AND MONITORING ENDPOINTS ──────────────────

    async def get_telemetry_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all robots"""
        try:
            # Get recent telemetry data
            recent_data = get_recent_telemetry_context(
                robot_id=None, 
                hours_back=0.5,  # Last 30 minutes
                max_entries=100
            )
            
            # Process robot status
            robot_status = self._build_robot_status_summary(recent_data)
            
            # Get stuck robots
            stuck_robots = get_stuck_robots()
            stuck_robot_data = self._format_stuck_robots(stuck_robots)
            
            # Calculate system statistics
            stats = self._calculate_system_stats(robot_status, stuck_robot_data)
            
            return {
                "timestamp": datetime.now().isoformat(),
                "system_stats": stats,
                "robot_status": list(robot_status.values()),
                "stuck_robots": stuck_robot_data,
                "alerts": self._generate_system_alerts(robot_status, stuck_robot_data)
            }
            
        except Exception as e:
            print(f"[STATUS ERROR] {e}")
            traceback.print_exc()
            return {"error": str(e)}

    def _build_robot_status_summary(self, recent_data: List) -> Dict[str, Dict]:
        """Build robot status summary from recent telemetry data"""
        robot_status = {}
        
        for row in recent_data:
            robot_id = row[0]
            
            # Only keep the most recent entry per robot
            if robot_id not in robot_status:
                robot_status[robot_id] = {
                    "robot_id": robot_id,
                    "last_seen": row[1].isoformat(),
                    "position": {"x": float(row[2] or 0), "y": float(row[3] or 0)},
                    "expected_position": {"x": float(row[4] or 0), "y": float(row[5] or 0)},
                    "movement_speed": float(row[6] or 0),
                    "is_stuck": bool(row[7]),
                    "current_waypoint": row[8],
                    "target_waypoint": row[9],
                    "navigation_status": row[10] or "unknown",
                    "sensor_data": row[11] if len(row) > 11 else {},
                    "status_color": "🔴" if row[7] else "🟢"
                }
        
        return robot_status

    def _format_stuck_robots(self, stuck_robots: List) -> List[Dict]:
        """Format stuck robot data for response"""
        return [
            {
                "robot_id": row[0],
                "last_seen": row[1].isoformat() if row[1] else None,
                "position": {"x": float(row[2] or 0), "y": float(row[3] or 0)},
                "current_waypoint": row[4],
                "target_waypoint": row[5],
                "assistance_needed": True
            }
            for row in stuck_robots
        ]

    def _calculate_system_stats(self, robot_status: Dict, stuck_robots: List) -> Dict:
        """Calculate overall system statistics"""
        total_robots = len(robot_status)
        stuck_count = len(stuck_robots)
        active_robots = sum(1 for r in robot_status.values() if r["movement_speed"] > 0.01)
        
        return {
            "total_robots": total_robots,
            "active_robots": active_robots,
            "stuck_robots": stuck_count,
            "idle_robots": total_robots - active_robots - stuck_count,
            "system_health": "degraded" if stuck_count > 0 else "healthy"
        }

    def _generate_system_alerts(self, robot_status: Dict, stuck_robots: List) -> List[Dict]:
        """Generate system-level alerts"""
        alerts = []
        
        if len(stuck_robots) > 0:
            alerts.append({
                "type": "system_alert",
                "priority": "high" if len(stuck_robots) > 2 else "medium",
                "message": f"{len(stuck_robots)} robot(s) stuck and need assistance"
            })
        
        # Check for robots offline
        offline_threshold = datetime.now() - timedelta(minutes=5)
        offline_robots = [
            r["robot_id"] for r in robot_status.values() 
            if datetime.fromisoformat(r["last_seen"]) < offline_threshold
        ]
        
        if offline_robots:
            alerts.append({
                "type": "connectivity_alert",
                "priority": "medium",
                "message": f"Robots offline: {', '.join(offline_robots)}"
            })
        
        return alerts

    # ─── ROBOT-SPECIFIC TELEMETRY ─────────────────────────

    async def get_robot_telemetry(self, robot_id: str, hours: int = 1) -> Dict[str, Any]:
        """Get detailed telemetry history for a specific robot"""
        try:
            telemetry_data = get_recent_telemetry_context(
                robot_id=robot_id,
                hours_back=hours,
                max_entries=200
            )
            
            formatted_data = self._format_robot_telemetry(telemetry_data)
            analysis = self._analyze_robot_performance(formatted_data)
            
            return {
                "robot_id": robot_id,
                "hours_requested": hours,
                "data_points": len(formatted_data),
                "telemetry": formatted_data,
                "performance_analysis": analysis
            }
            
        except Exception as e:
            print(f"[ROBOT TELEMETRY ERROR] {e}")
            traceback.print_exc()
            return {"error": str(e)}

    def _format_robot_telemetry(self, telemetry_data: List) -> List[Dict]:
        """Format raw telemetry data for response"""
        return [
            {
                "timestamp": row[1].isoformat(),
                "position": {"x": float(row[2] or 0), "y": float(row[3] or 0)},
                "expected_position": {"x": float(row[4] or 0), "y": float(row[5] or 0)},
                "movement_speed": float(row[6] or 0),
                "is_stuck": bool(row[7]),
                "current_waypoint": row[8],
                "target_waypoint": row[9],
                "navigation_status": row[10] or "unknown",
                "sensor_data": row[11] if len(row) > 11 else {}
            }
            for row in telemetry_data
        ]

    def _analyze_robot_performance(self, telemetry_data: List[Dict]) -> Dict:
        """Analyze robot performance over the telemetry period"""
        if not telemetry_data:
            return {"error": "No telemetry data available"}
        
        # Calculate metrics
        speeds = [t["movement_speed"] for t in telemetry_data]
        stuck_count = sum(1 for t in telemetry_data if t["is_stuck"])
        
        # Unique waypoints visited
        waypoints_visited = set()
        for t in telemetry_data:
            if t["current_waypoint"]:
                waypoints_visited.add(t["current_waypoint"])
        
        return {
            "average_speed": round(sum(speeds) / len(speeds), 3) if speeds else 0,
            "max_speed": max(speeds) if speeds else 0,
            "stuck_incidents": stuck_count,
            "stuck_percentage": round((stuck_count / len(telemetry_data)) * 100, 1),
            "waypoints_visited": len(waypoints_visited),
            "uptime_percentage": 100.0,  # Could calculate based on data gaps
            "performance_rating": self._calculate_performance_rating(speeds, stuck_count, len(telemetry_data))
        }

    def _calculate_performance_rating(self, speeds: List[float], stuck_count: int, total_points: int) -> str:
        """Calculate overall performance rating"""
        avg_speed = sum(speeds) / len(speeds) if speeds else 0
        stuck_percentage = (stuck_count / total_points) * 100 if total_points > 0 else 0
        
        if stuck_percentage > 20 or avg_speed < 0.1:
            return "poor"
        elif stuck_percentage > 10 or avg_speed < 0.3:
            return "fair"
        elif stuck_percentage > 5 or avg_speed < 0.5:
            return "good"
        else:
            return "excellent"

    # ─── ROBOT ASSISTANCE HANDLING ────────────────────────

    async def handle_robot_assistance_request(self, robot_id: str, message: str, priority: str = "medium") -> Dict:
        """Handle assistance requests from robots"""
        try:
            # Get robot context
            context = build_comprehensive_context(message, robot_id)
            
            # Log assistance request
            add_mcp_message({
                "role": "robot",
                "timestamp": datetime.now().isoformat(),
                "agent_id": robot_id,
                "source": "assistance_request",
                "message": message,
                "priority": priority,
                "context": context
            })
            
            print(f"[ROBOT ASSISTANCE] {robot_id}: {message} (Priority: {priority})")
            
            return {
                "status": "logged",
                "robot_id": robot_id,
                "message": message,
                "priority": priority,
                "context_available": True,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"[ASSISTANCE ERROR] {e}")
            return {"error": str(e)}

    # ─── MCP TOOL SUPPORT ─────────────────────────────────

    async def get_current_robot_status(self) -> Dict:
        """Get current robot status for MCP tool usage"""
        return await self.get_telemetry_status()