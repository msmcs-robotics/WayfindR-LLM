"""
Telemetry Handler for WayfindR-LLM
Handles incoming telemetry from robots (Android app / Raspberry Pi)
"""
from datetime import datetime
from typing import Dict, Any, Optional

# Import storage
try:
    from rag.qdrant_store import add_telemetry, get_latest_telemetry, get_robot_telemetry_history
except ImportError:
    add_telemetry = None
    get_latest_telemetry = None
    get_robot_telemetry_history = None


async def receive_telemetry(robot_id: str, telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Receive and store telemetry from a robot

    Args:
        robot_id: Robot identifier (e.g., "robot_01")
        telemetry: Dictionary with robot status:
            - status: "idle" | "navigating" | "stuck" | "charging"
            - battery: Battery percentage (0-100)
            - current_location: Current waypoint/area name
            - destination: Target waypoint (if navigating)
            - position: Optional {x, y} coordinates
            - sensors: Optional sensor readings
            - error: Optional error message

    Returns:
        Success status and stored point ID
    """
    if not add_telemetry:
        return {
            "success": False,
            "error": "Qdrant not available"
        }

    # Add timestamp if not present
    if 'timestamp' not in telemetry:
        telemetry['timestamp'] = datetime.now().isoformat()

    try:
        point_id = add_telemetry(robot_id, telemetry)

        if point_id:
            print(f"[TELEMETRY] Stored telemetry for {robot_id}: {telemetry.get('status', 'unknown')}")
            return {
                "success": True,
                "point_id": point_id,
                "robot_id": robot_id
            }
        else:
            return {
                "success": False,
                "error": "Failed to store telemetry"
            }

    except Exception as e:
        print(f"[TELEMETRY] Error storing telemetry: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def get_robot_status(robot_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get current status for a robot or all robots

    Args:
        robot_id: Optional robot filter. If None, returns all robots.

    Returns:
        Dictionary with robot status information
    """
    if not get_latest_telemetry:
        return {
            "success": False,
            "error": "Qdrant not available"
        }

    try:
        latest = get_latest_telemetry(robot_id)

        if robot_id:
            if robot_id in latest:
                return {
                    "success": True,
                    "robot_id": robot_id,
                    "telemetry": latest[robot_id]
                }
            else:
                return {
                    "success": False,
                    "error": f"No telemetry found for {robot_id}"
                }
        else:
            return {
                "success": True,
                "robots": latest,
                "count": len(latest)
            }

    except Exception as e:
        print(f"[TELEMETRY] Error getting robot status: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def get_robot_history(robot_id: str, limit: int = 10) -> Dict[str, Any]:
    """
    Get telemetry history for a robot

    Args:
        robot_id: Robot identifier
        limit: Number of entries to retrieve

    Returns:
        Dictionary with telemetry history
    """
    if not get_robot_telemetry_history:
        return {
            "success": False,
            "error": "Qdrant not available"
        }

    try:
        history = get_robot_telemetry_history(robot_id, limit)

        return {
            "success": True,
            "robot_id": robot_id,
            "history": history,
            "count": len(history)
        }

    except Exception as e:
        print(f"[TELEMETRY] Error getting robot history: {e}")
        return {
            "success": False,
            "error": str(e)
        }


__all__ = [
    'receive_telemetry',
    'get_robot_status',
    'get_robot_history'
]
