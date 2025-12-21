"""
Function Executor for WayfindR-LLM
Execute parsed function calls (navigation, alerts, etc.)

Two types of executors:
1. Visitor functions (via robot chat) - navigation, help requests
2. Operator commands (via dashboard) - robot control, status reports

These are STUBS - actual robot communication via ROS 2/MQTT is future work.
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import logging
try:
    from rag.postgresql_store import add_log
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False
    add_log = None

# Import Qdrant for telemetry queries
try:
    from rag.qdrant_store import get_latest_telemetry, get_robot_telemetry_history
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    get_latest_telemetry = None
    get_robot_telemetry_history = None


# =============================================================================
# VISITOR FUNCTION EXECUTION (for robot chat)
# =============================================================================

async def execute_function(function_call: Dict[str, Any], robot_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a function call from intent parsing

    Args:
        function_call: Dictionary with:
            - name: Function name
            - args: Function arguments
        robot_id: Optional robot context

    Returns:
        Execution result
    """
    func_name = function_call.get('name', '')
    args = function_call.get('args', {})

    print(f"[EXECUTOR] Executing: {func_name} with args: {args}")

    if func_name == 'navigate_to_waypoint':
        return await navigate_to_waypoint(
            robot_id=robot_id,
            waypoints=args.get('waypoints', [])
        )

    elif func_name == 'alert_humans':
        return await alert_humans(
            robot_id=robot_id,
            message=args.get('message', 'Alert triggered')
        )

    else:
        return {
            "success": False,
            "error": f"Unknown function: {func_name}"
        }


async def navigate_to_waypoint(robot_id: Optional[str], waypoints: List[str]) -> Dict[str, Any]:
    """
    Navigate robot to specified waypoints

    STUB: In production, this would send commands to the robot via ROS 2/MQTT

    Args:
        robot_id: Robot to command
        waypoints: List of waypoints to navigate to

    Returns:
        Command status
    """
    command_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().isoformat()

    print(f"[NAVIGATOR] Command {command_id}: Navigate {robot_id or 'robot'} to {waypoints}")

    # Log the command
    if LOGGING_AVAILABLE and add_log:
        add_log(
            f"Navigation command: {waypoints}",
            metadata={
                "source": "system",
                "message_type": "command",
                "robot_id": robot_id,
                "command_type": "navigation",
                "waypoints": waypoints,
                "command_id": command_id,
                "timestamp": timestamp
            }
        )

    # STUB: Would send to robot here
    # In production:
    # - Publish to ROS 2 topic: /robot_id/navigation/goal
    # - Or send via MQTT: robots/robot_id/commands/navigate

    return {
        "success": True,
        "command_id": command_id,
        "robot_id": robot_id,
        "waypoints": waypoints,
        "status": "queued",
        "message": f"Navigation to {', '.join(waypoints)} has been queued",
        "note": "STUB: Actual robot communication not implemented"
    }


async def alert_humans(robot_id: Optional[str], message: str) -> Dict[str, Any]:
    """
    Alert human staff about an issue

    STUB: In production, this would trigger notifications/alarms

    Args:
        robot_id: Robot reporting the alert
        message: Alert message

    Returns:
        Alert status
    """
    alert_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().isoformat()

    # Determine priority from message content
    priority = "HIGH" if any(word in message.lower() for word in ["emergency", "fire", "danger", "urgent"]) else "MEDIUM"

    print(f"[ALERT] {priority} Alert {alert_id}: {message}")

    # Log the alert
    if LOGGING_AVAILABLE and add_log:
        add_log(
            f"ALERT [{priority}]: {message}",
            metadata={
                "source": robot_id or "system",
                "message_type": "notification",
                "alert_type": "human_alert",
                "priority": priority,
                "alert_id": alert_id,
                "timestamp": timestamp
            }
        )

    # STUB: Would send alert here
    # In production:
    # - Send push notification
    # - Trigger alarm system
    # - Log to monitoring dashboard

    return {
        "success": True,
        "alert_id": alert_id,
        "robot_id": robot_id,
        "priority": priority,
        "message": message,
        "status": "logged",
        "note": "STUB: Actual notification system not implemented"
    }


async def get_robot_location(robot_id: str) -> Dict[str, Any]:
    """
    Get current robot location

    STUB: Would query robot or telemetry database

    Args:
        robot_id: Robot to query

    Returns:
        Location information
    """
    # STUB: Would query actual robot location
    return {
        "success": True,
        "robot_id": robot_id,
        "location": "unknown",
        "note": "STUB: Location query not implemented"
    }


# =============================================================================
# OPERATOR COMMAND EXECUTION (for dashboard)
# =============================================================================

async def execute_operator_command(command: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an operator command from the dashboard

    Args:
        command: Dictionary with:
            - type: Command type (send_robot, robot_announce, etc.)
            - robot_id: Target robot
            - Other command-specific fields

    Returns:
        Execution result
    """
    cmd_type = command.get('type', '')

    print(f"[OPERATOR CMD] Executing: {cmd_type} with: {command}")

    if cmd_type == 'send_robot':
        return await send_robot_to_location(
            robot_id=command.get('robot_id', 'robot_01'),
            destination=command.get('destination', 'reception')
        )

    elif cmd_type == 'robot_announce':
        return await robot_announce(
            robot_id=command.get('robot_id', 'all'),
            message=command.get('message', 'Attention please')
        )

    elif cmd_type == 'get_status':
        return await get_robot_status(
            robot_id=command.get('robot_id', 'robot_01')
        )

    elif cmd_type == 'get_all_status':
        return await get_all_robot_status()

    elif cmd_type == 'recall_robot':
        return await recall_robot(
            robot_id=command.get('robot_id', 'robot_01')
        )

    elif cmd_type == 'system_report':
        return await generate_system_report()

    else:
        return {
            "success": False,
            "error": f"Unknown command type: {cmd_type}"
        }


async def send_robot_to_location(robot_id: str, destination: str) -> Dict[str, Any]:
    """
    Send a robot to a specific location (operator command)

    STUB: Would send ROS 2/MQTT command to robot

    Args:
        robot_id: Robot to command
        destination: Target waypoint

    Returns:
        Command status
    """
    command_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().isoformat()

    print(f"[OPERATOR] Send {robot_id} to {destination} (cmd: {command_id})")

    # Log the command
    if LOGGING_AVAILABLE and add_log:
        add_log(
            f"Operator command: Send {robot_id} to {destination}",
            metadata={
                "source": "operator",
                "message_type": "command",
                "command_type": "send_robot",
                "robot_id": robot_id,
                "destination": destination,
                "command_id": command_id,
                "timestamp": timestamp
            }
        )

    # STUB: Would publish to ROS 2 or MQTT
    return {
        "success": True,
        "command_id": command_id,
        "robot_id": robot_id,
        "destination": destination,
        "status": "sent",
        "message": f"Command sent: {robot_id} navigating to {destination}",
        "note": "STUB: Actual robot communication not implemented"
    }


async def robot_announce(robot_id: str, message: str) -> Dict[str, Any]:
    """
    Make robot(s) announce a message

    STUB: Would send TTS command to robot

    Args:
        robot_id: Robot to command (or 'all')
        message: Message to announce

    Returns:
        Command status
    """
    command_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().isoformat()

    target = "all robots" if robot_id == "all" else robot_id
    print(f"[OPERATOR] Announce on {target}: {message[:50]}...")

    if LOGGING_AVAILABLE and add_log:
        add_log(
            f"Operator announcement ({target}): {message}",
            metadata={
                "source": "operator",
                "message_type": "command",
                "command_type": "announce",
                "robot_id": robot_id,
                "announcement": message,
                "command_id": command_id,
                "timestamp": timestamp
            }
        )

    return {
        "success": True,
        "command_id": command_id,
        "robot_id": robot_id,
        "message": message,
        "status": "broadcast_sent",
        "message": f"Announcement queued for {target}: '{message[:50]}...'",
        "note": "STUB: Actual TTS not implemented"
    }


async def get_robot_status(robot_id: str) -> Dict[str, Any]:
    """
    Get status of a specific robot

    Args:
        robot_id: Robot to query

    Returns:
        Robot status information
    """
    print(f"[OPERATOR] Getting status for {robot_id}")

    # Try to get from Qdrant
    if QDRANT_AVAILABLE and get_robot_telemetry_history:
        try:
            telemetry = get_robot_telemetry_history(robot_id, limit=1)
            if telemetry:
                latest = telemetry[0]
                return {
                    "success": True,
                    "robot_id": robot_id,
                    "status": latest.get("status", "online"),
                    "battery": latest.get("battery", "unknown"),
                    "location": latest.get("current_location", "unknown"),
                    "last_update": latest.get("timestamp", "unknown"),
                    "message": f"{robot_id} is {latest.get('status', 'online')} at {latest.get('current_location', 'unknown')} (battery: {latest.get('battery', '?')}%)"
                }
        except Exception as e:
            print(f"[OPERATOR] Error getting telemetry: {e}")

    # Fallback: no telemetry available
    return {
        "success": True,
        "robot_id": robot_id,
        "status": "unknown",
        "battery": "N/A",
        "location": "N/A",
        "message": f"{robot_id} status unknown - no telemetry data",
        "note": "No recent telemetry available"
    }


async def get_all_robot_status() -> Dict[str, Any]:
    """
    Get status of all robots

    Returns:
        Combined status report
    """
    print("[OPERATOR] Getting status for all robots")

    robots_status = []

    if QDRANT_AVAILABLE and get_latest_telemetry:
        try:
            # get_latest_telemetry returns {robot_id: telemetry_dict}
            all_telemetry = get_latest_telemetry()
            for robot_id, telemetry in all_telemetry.items():
                robots_status.append({
                    "robot_id": robot_id,
                    "status": telemetry.get("status", "unknown"),
                    "battery": telemetry.get("battery", "N/A"),
                    "location": telemetry.get("current_location", "N/A"),
                    "last_update": telemetry.get("timestamp", "N/A")
                })
        except Exception as e:
            print(f"[OPERATOR] Error getting robots: {e}")

    if not robots_status:
        # Return empty list with note
        return {
            "success": True,
            "total_robots": 0,
            "robots": [],
            "message": "No robots registered yet. Robots will appear when they send telemetry."
        }

    return {
        "success": True,
        "total_robots": len(robots_status),
        "robots": robots_status,
        "message": f"Found {len(robots_status)} robot(s) in system"
    }


async def recall_robot(robot_id: str) -> Dict[str, Any]:
    """
    Recall robot to charging station

    STUB: Would send recall command to robot

    Args:
        robot_id: Robot to recall (or 'all')

    Returns:
        Command status
    """
    command_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().isoformat()

    target = "all robots" if robot_id == "all" else robot_id
    print(f"[OPERATOR] Recalling {target} to charging station")

    if LOGGING_AVAILABLE and add_log:
        add_log(
            f"Operator recall command: {target}",
            metadata={
                "source": "operator",
                "message_type": "command",
                "command_type": "recall",
                "robot_id": robot_id,
                "command_id": command_id,
                "timestamp": timestamp
            }
        )

    return {
        "success": True,
        "command_id": command_id,
        "robot_id": robot_id,
        "destination": "charging_station",
        "status": "recall_sent",
        "message": f"Recall command sent to {target}. Returning to charging station.",
        "note": "STUB: Actual robot communication not implemented"
    }


async def generate_system_report() -> Dict[str, Any]:
    """
    Generate system-wide health report

    Returns:
        System health report
    """
    print("[OPERATOR] Generating system report")

    report = {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "system_status": "operational",
        "components": {
            "mcp_server": "online",
            "postgresql": "unknown",
            "qdrant": "unknown",
            "llm": "unknown"
        },
        "robots": []
    }

    # Check Qdrant
    if QDRANT_AVAILABLE and get_latest_telemetry:
        try:
            all_telemetry = get_latest_telemetry()
            report["components"]["qdrant"] = "online"
            report["total_robots"] = len(all_telemetry)

            for robot_id, telemetry in all_telemetry.items():
                report["robots"].append({
                    "robot_id": robot_id,
                    "battery": telemetry.get("battery", "N/A"),
                    "location": telemetry.get("current_location", "N/A"),
                    "status": telemetry.get("status", "unknown"),
                    "last_update": telemetry.get("timestamp", "N/A")
                })
        except Exception as e:
            report["components"]["qdrant"] = f"error: {e}"

    # Check PostgreSQL
    if LOGGING_AVAILABLE:
        report["components"]["postgresql"] = "online"

    # Check LLM
    try:
        from llm_config import get_ollama_client
        client = get_ollama_client()
        if client:
            report["components"]["llm"] = "available"
    except:
        pass

    # Build summary message
    online_robots = sum(1 for r in report["robots"] if r.get("status") in ["online", "idle", "navigating"])
    report["message"] = f"System operational. {len(report['robots'])} robots registered, {online_robots} active."

    return report


__all__ = [
    'execute_function',
    'execute_operator_command',
    'navigate_to_waypoint',
    'alert_humans',
    'get_robot_location',
    'send_robot_to_location',
    'robot_announce',
    'get_robot_status',
    'get_all_robot_status',
    'recall_robot',
    'generate_system_report'
]
