"""
Chat Handler for WayfindR-LLM
Implements two-phase LLM strategy for chat processing

Two chat modes:
1. Operator Chat (web dashboard) - For system management and robot control
2. Robot Chat (Android app) - For visitor interaction and navigation
"""
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

# Import LLM
try:
    from llm_config import get_ollama_client, get_model_name, chat_with_retry
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# Import components
try:
    from agents.intent_parser import parse_intent, parse_operator_intent
    from agents.function_executor import execute_function, execute_operator_command
    from rag.context_builder import get_context_builder
except ImportError:
    parse_intent = None
    parse_operator_intent = None
    execute_function = None
    execute_operator_command = None
    get_context_builder = None

# Import logging
try:
    from rag.postgresql_store import add_log
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False
    add_log = None


# =============================================================================
# OPERATOR CHAT PROMPT (for dashboard - management focus)
# =============================================================================
OPERATOR_SYSTEM_PROMPT = """You are an AI assistant for the WayfindR robot fleet management system.
You help operators monitor and control tour guide robots in a building.

ROLE: You are speaking to an OPERATOR (staff member managing the robots), NOT a visitor.

{context}

AVAILABLE COMMANDS you can execute:
- Move robot to location: send_robot(robot_id, destination)
- Make robot announce: robot_announce(robot_id, message)
- Get robot status: get_status(robot_id) or get_all_status()
- Get system report: system_report()
- Recall robot to charging: recall_robot(robot_id)

OPERATOR CAPABILITIES:
- Ask for reports on robot status, battery levels, locations
- Command robots to move to specific locations
- Make robots announce messages to visitors
- Monitor system health and telemetry
- Recall robots for charging or maintenance

RESPONSE GUIDELINES:
- Be professional and concise
- When showing status, use clear formatting
- Confirm commands before/after execution
- Report any issues or errors clearly
- Do NOT guide the operator to locations (they're managing the system, not visiting)

Current intent: {intent_type}
Commands requested: {commands}
"""

# =============================================================================
# ROBOT CHAT PROMPT (for Android app - visitor interaction)
# =============================================================================
ROBOT_RESPONSE_PROMPT = """You are a friendly tour guide robot assistant.
You help visitors navigate the building, answer questions, and provide assistance.

Building Information:
- You know the layout and can provide directions
- Available locations: {waypoints}

{context}

Guidelines:
- Be friendly, helpful, and concise
- If giving directions, be clear and specific
- If you don't know something, say so politely
- For emergencies, confirm that help has been alerted
- Keep responses conversational but informative

Current user intent: {intent_type}
Mentioned locations: {mentioned_waypoints}
"""


async def handle_web_chat(message: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Handle OPERATOR chat from web dashboard (management/control focus)

    This is for operators managing the robot fleet, NOT visitors.
    Operators can:
    - Get status reports on robots
    - Send robots to locations
    - Make robots announce messages
    - Monitor system health

    Args:
        message: Operator message
        user_id: Optional operator identifier

    Returns:
        Chat response with command results
    """
    conversation_id = f"operator_{user_id or 'anon'}_{uuid.uuid4().hex[:8]}"

    return await _process_operator_chat(
        message=message,
        conversation_id=conversation_id,
        user_id=user_id
    )


async def handle_robot_chat(message: str, robot_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Handle chat from Android app on robot (visitor interaction focus)

    Args:
        message: User message
        robot_id: Robot identifier
        user_id: Optional user identifier

    Returns:
        Chat response with potential navigation commands
    """
    conversation_id = f"robot_{robot_id}_{uuid.uuid4().hex[:8]}"

    return await _process_robot_chat(
        message=message,
        conversation_id=conversation_id,
        user_id=user_id,
        robot_id=robot_id
    )


# =============================================================================
# OPERATOR CHAT PROCESSING (Dashboard)
# =============================================================================

async def _process_operator_chat(
    message: str,
    conversation_id: str,
    user_id: Optional[str]
) -> Dict[str, Any]:
    """
    Process operator chat for system management

    Operators can:
    - Request status reports
    - Send robots to locations
    - Make robots announce messages
    - Monitor system health
    """
    timestamp = datetime.now().isoformat()

    # Log operator message
    if LOGGING_AVAILABLE and add_log:
        add_log(
            message,
            metadata={
                "source": "operator",
                "message_type": "command",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "timestamp": timestamp
            }
        )

    print(f"\n[OPERATOR] Processing command: {message[:50]}...")

    # === PHASE 1: Parse Operator Intent ===
    intent = {"intent_type": "query", "commands": [], "robots_mentioned": []}
    if parse_operator_intent:
        intent = parse_operator_intent(message)
    else:
        # Fallback parsing
        intent = _fallback_operator_parse(message)

    print(f"[OPERATOR] Intent: {intent.get('intent_type')} - commands: {intent.get('commands', [])}")

    # === PHASE 2: Execute Commands ===
    command_results = []
    if execute_operator_command and intent.get('commands'):
        for cmd in intent['commands']:
            result = await execute_operator_command(cmd)
            command_results.append(result)
            print(f"[OPERATOR] Command result: {result}")

    # === PHASE 3: Generate Response ===
    response_text = await _generate_operator_response(
        message=message,
        intent=intent,
        command_results=command_results
    )

    # Log response
    if LOGGING_AVAILABLE and add_log:
        add_log(
            response_text,
            metadata={
                "source": "system",
                "message_type": "response",
                "conversation_id": conversation_id,
                "intent_type": intent.get('intent_type'),
                "timestamp": datetime.now().isoformat()
            }
        )

    return {
        "success": True,
        "response": response_text,
        "conversation_id": conversation_id,
        "intent": intent.get('intent_type'),
        "commands_executed": command_results if command_results else None
    }


def _fallback_operator_parse(message: str) -> Dict[str, Any]:
    """Simple fallback parsing for operator commands"""
    message_lower = message.lower()

    result = {
        "intent_type": "query",
        "commands": [],
        "robots_mentioned": []
    }

    # Check for status/report requests
    if any(word in message_lower for word in ["status", "report", "how is", "where is", "battery", "health"]):
        result["intent_type"] = "status_query"

    # Check for send/move commands
    elif any(word in message_lower for word in ["send", "move", "navigate", "go to", "take"]):
        result["intent_type"] = "send_command"

        # Extract robot ID
        import re
        robot_match = re.search(r'robot[_\s]?(\d+|one|two|three|01|02|03)', message_lower)
        if robot_match:
            result["robots_mentioned"].append(f"robot_{robot_match.group(1)}")

        # Try to extract destination
        try:
            from core.config import WAYPOINTS
            for waypoint in WAYPOINTS:
                if waypoint.lower().replace("_", " ") in message_lower:
                    result["commands"].append({
                        "type": "send_robot",
                        "robot_id": result["robots_mentioned"][0] if result["robots_mentioned"] else "robot_01",
                        "destination": waypoint
                    })
                    break
        except ImportError:
            pass

    # Check for announce commands
    elif any(word in message_lower for word in ["announce", "say", "tell", "broadcast"]):
        result["intent_type"] = "announce_command"

    # Check for recall/return commands
    elif any(word in message_lower for word in ["recall", "return", "come back", "charging"]):
        result["intent_type"] = "recall_command"

    return result


async def _generate_operator_response(
    message: str,
    intent: Dict[str, Any],
    command_results: list
) -> str:
    """Generate response for operator"""

    # Build context with current system state
    context_str = ""
    if get_context_builder:
        builder = get_context_builder()
        context_str = builder.build_system_context()

    # Add command results
    if command_results:
        context_str += "\n\nCommand Results:"
        for result in command_results:
            status = "Success" if result.get('success') else "Failed"
            context_str += f"\n- {status}: {result.get('message', 'No details')}"

    if not LLM_AVAILABLE:
        return _fallback_operator_response(intent, command_results, context_str)

    try:
        client = get_ollama_client()
        model = get_model_name()

        system_prompt = OPERATOR_SYSTEM_PROMPT.format(
            context=context_str,
            intent_type=intent.get('intent_type', 'query'),
            commands=str(intent.get('commands', []))
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]

        response = chat_with_retry(client, model, messages, max_retries=2)

        if response:
            return response.get('message', {}).get('content', _fallback_operator_response(intent, command_results, context_str))
        else:
            return _fallback_operator_response(intent, command_results, context_str)

    except Exception as e:
        print(f"[OPERATOR] Error generating response: {e}")
        return _fallback_operator_response(intent, command_results, context_str)


def _fallback_operator_response(intent: Dict[str, Any], command_results: list, context: str) -> str:
    """Fallback response for operator when LLM unavailable"""
    intent_type = intent.get('intent_type', 'query')

    if intent_type == 'status_query':
        return f"**System Status Report**\n\n{context}\n\n(LLM unavailable - showing raw status)"

    elif intent_type == 'send_command':
        if command_results and command_results[0].get('success'):
            return f"Command executed: {command_results[0].get('message', 'Robot sent to destination')}"
        else:
            return "Command queued. Robot will navigate to the specified location."

    elif intent_type == 'announce_command':
        return "Announcement command received. Robot will broadcast the message."

    elif intent_type == 'recall_command':
        return "Recall command received. Robot will return to charging station."

    else:
        return f"**Operator Console**\n\nI can help you manage the robot fleet. Try:\n- \"Show status of all robots\"\n- \"Send robot_01 to cafeteria\"\n- \"Make robot_01 announce 'Tours starting soon'\"\n- \"Get system health report\"\n\n{context}"


# =============================================================================
# ROBOT CHAT PROCESSING (Android App)
# =============================================================================

async def _process_robot_chat(
    message: str,
    conversation_id: str,
    user_id: Optional[str],
    robot_id: str
) -> Dict[str, Any]:
    """
    Process visitor chat from Android app on robot

    Visitors can:
    - Ask for directions
    - Get help
    - Have small talk
    - Report emergencies
    """
    timestamp = datetime.now().isoformat()

    # Log user message
    if LOGGING_AVAILABLE and add_log:
        add_log(
            message,
            metadata={
                "source": "visitor",
                "message_type": "command",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "robot_id": robot_id,
                "timestamp": timestamp
            }
        )

    print(f"\n[ROBOT] Processing visitor message: {message[:50]}...")

    # === PHASE 1: Intent Parsing ===
    intent = {"intent_type": "smalltalk", "waypoints": [], "function_calls": []}
    if parse_intent:
        intent = parse_intent(message, robot_id)
    print(f"[ROBOT] Intent: {intent.get('intent_type')} - waypoints: {intent.get('waypoints', [])}")

    # Execute any function calls
    function_results = []
    if execute_function and intent.get('function_calls'):
        for func_call in intent['function_calls']:
            result = await execute_function(func_call, robot_id)
            function_results.append(result)

    # === PHASE 2: Response Generation ===
    response_text = await _generate_robot_response(
        message=message,
        intent=intent,
        function_results=function_results,
        robot_id=robot_id
    )

    # Log response
    if LOGGING_AVAILABLE and add_log:
        add_log(
            response_text,
            metadata={
                "source": "robot",
                "message_type": "response",
                "conversation_id": conversation_id,
                "intent_type": intent.get('intent_type'),
                "robot_id": robot_id,
                "timestamp": datetime.now().isoformat()
            }
        )

    return {
        "success": True,
        "response": response_text,
        "conversation_id": conversation_id,
        "intent": intent.get('intent_type'),
        "waypoints": intent.get('waypoints', []),
        "function_results": function_results if function_results else None
    }


async def _generate_robot_response(
    message: str,
    intent: Dict[str, Any],
    function_results: list,
    robot_id: str
) -> str:
    """Generate response for visitor on robot"""

    if not LLM_AVAILABLE:
        return _fallback_robot_response(intent, function_results)

    try:
        client = get_ollama_client()
        model = get_model_name()

        # Build context
        context_str = ""
        if get_context_builder:
            builder = get_context_builder()
            context_str = builder.build_system_context()

        if function_results:
            context_str += "\n\nActions taken:"
            for result in function_results:
                if result.get('success'):
                    context_str += f"\n- {result.get('message', 'Action completed')}"

        try:
            from core.config import WAYPOINTS
            waypoints = ", ".join(WAYPOINTS)
        except ImportError:
            waypoints = "reception, cafeteria, meeting rooms, elevator, exit"

        system_prompt = ROBOT_RESPONSE_PROMPT.format(
            waypoints=waypoints,
            context=context_str,
            intent_type=intent.get('intent_type', 'general'),
            mentioned_waypoints=", ".join(intent.get('waypoints', [])) or "none"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]

        response = chat_with_retry(client, model, messages, max_retries=2)

        if response:
            return response.get('message', {}).get('content', _fallback_robot_response(intent, function_results))
        else:
            return _fallback_robot_response(intent, function_results)

    except Exception as e:
        print(f"[ROBOT] Error generating response: {e}")
        return _fallback_robot_response(intent, function_results)


def _fallback_robot_response(intent: Dict[str, Any], function_results: list) -> str:
    """Generate fallback response for visitor when LLM unavailable"""
    intent_type = intent.get('intent_type', 'smalltalk')
    waypoints = intent.get('waypoints', [])

    if intent_type == 'navigation' and waypoints:
        if function_results and function_results[0].get('success'):
            return f"I've set course for {', '.join(waypoints)}. Please follow me!"
        else:
            return f"I can help you get to {', '.join(waypoints)}. Let me guide you there."

    elif intent_type == 'emergency':
        return "I've alerted the staff about your emergency. Help is on the way. Please stay calm."

    elif intent_type == 'help':
        return "I'm here to help! I can guide you to different locations in the building. Where would you like to go?"

    elif intent_type == 'status_query':
        return "I'm a tour guide robot. I can help you navigate this building and answer questions about the facilities."

    elif intent_type == 'greeting':
        return "Hello! Welcome to the facility. I'm your tour guide robot. How can I help you today?"

    elif intent_type == 'farewell':
        return "Goodbye! Thank you for visiting. Have a wonderful day!"

    else:
        return "Hello! I'm your tour guide robot. I can help you find locations in the building or answer questions. How can I assist you?"


__all__ = [
    'handle_web_chat',
    'handle_robot_chat'
]
