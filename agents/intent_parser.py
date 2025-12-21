"""
Intent Parser for WayfindR-LLM
Phase 1 of two-phase LLM strategy: Parse user intent to structured JSON
"""
import json
import re
from typing import Dict, Any, Optional

# Import LLM config
try:
    from llm_config import get_ollama_client, get_model_name, chat_with_retry
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# Import waypoints
try:
    from core.config import WAYPOINTS
except ImportError:
    WAYPOINTS = ["reception", "cafeteria", "meeting_room_a", "elevator", "exit"]


# =============================================================================
# VISITOR INTENT PARSING (for Android app / robot chat)
# =============================================================================

INTENT_SYSTEM_PROMPT = """You are an intent parser for a tour guide robot system.
Analyze the user's message and extract structured intent information.

IMPORTANT: You must respond with ONLY valid JSON, no other text.

Available intent types:
- "navigation": User wants to go somewhere or get directions
- "status_query": User asking about robot status, battery, location
- "smalltalk": General conversation, greetings, questions about the building
- "help": User needs assistance or is lost
- "emergency": User reports an emergency or needs urgent help

Available waypoints: {waypoints}

Extract:
1. intent_type: One of the types above
2. waypoints: List of mentioned locations (empty if none)
3. urgency: "low", "medium", or "high"
4. function_calls: List of functions to call (if applicable)

Available functions:
- navigate_to_waypoint(waypoints: list): Navigate robot to specified locations
- alert_humans(message: str): Alert staff about an issue

Example outputs:

User: "Take me to the cafeteria"
{{"intent_type": "navigation", "waypoints": ["cafeteria"], "urgency": "low", "function_calls": [{{"name": "navigate_to_waypoint", "args": {{"waypoints": ["cafeteria"]}}}}]}}

User: "Where is the bathroom?"
{{"intent_type": "navigation", "waypoints": ["restroom"], "urgency": "low", "function_calls": []}}

User: "Hello, how are you?"
{{"intent_type": "smalltalk", "waypoints": [], "urgency": "low", "function_calls": []}}

User: "I'm lost and need help"
{{"intent_type": "help", "waypoints": [], "urgency": "medium", "function_calls": []}}

User: "There's a fire!"
{{"intent_type": "emergency", "waypoints": [], "urgency": "high", "function_calls": [{{"name": "alert_humans", "args": {{"message": "Emergency: fire reported"}}}}]}}

RESPOND WITH ONLY VALID JSON."""


def parse_intent(message: str, robot_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Parse user message to extract intent

    Args:
        message: User's message
        robot_id: Optional robot context

    Returns:
        Dictionary with:
            - intent_type: Type of intent
            - waypoints: List of mentioned waypoints
            - urgency: low/medium/high
            - function_calls: List of functions to execute
            - raw_message: Original message
    """
    # Default response
    default_result = {
        "intent_type": "smalltalk",
        "waypoints": [],
        "urgency": "low",
        "function_calls": [],
        "raw_message": message
    }

    if not LLM_AVAILABLE:
        print("[INTENT] LLM not available, using fallback parsing")
        return _fallback_parse(message)

    try:
        client = get_ollama_client()
        model = get_model_name()

        # Build prompt with waypoints
        system_prompt = INTENT_SYSTEM_PROMPT.format(
            waypoints=", ".join(WAYPOINTS)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]

        response = chat_with_retry(client, model, messages, max_retries=2)

        if not response:
            print("[INTENT] No response from LLM, using fallback")
            return _fallback_parse(message)

        # Extract JSON from response
        content = response.get('message', {}).get('content', '')
        result = _extract_json(content)

        if result:
            result['raw_message'] = message
            print(f"[INTENT] Parsed: {result.get('intent_type')} - waypoints: {result.get('waypoints', [])}")
            return result
        else:
            print("[INTENT] Failed to parse JSON, using fallback")
            return _fallback_parse(message)

    except Exception as e:
        print(f"[INTENT] Error parsing intent: {e}")
        return _fallback_parse(message)


def _extract_json(content: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM response"""
    # Try direct parse
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass

    # Try to find JSON in response
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None


def _fallback_parse(message: str) -> Dict[str, Any]:
    """Simple regex-based fallback parsing"""
    message_lower = message.lower()

    result = {
        "intent_type": "smalltalk",
        "waypoints": [],
        "urgency": "low",
        "function_calls": [],
        "raw_message": message
    }

    # Check for navigation keywords
    nav_keywords = ["take me", "go to", "navigate", "where is", "how do i get to", "find"]
    if any(kw in message_lower for kw in nav_keywords):
        result["intent_type"] = "navigation"

        # Extract waypoints
        for waypoint in WAYPOINTS:
            if waypoint.lower().replace("_", " ") in message_lower:
                result["waypoints"].append(waypoint)

        if result["waypoints"]:
            result["function_calls"] = [{
                "name": "navigate_to_waypoint",
                "args": {"waypoints": result["waypoints"]}
            }]

    # Check for status queries
    status_keywords = ["status", "battery", "where are you", "location"]
    if any(kw in message_lower for kw in status_keywords):
        result["intent_type"] = "status_query"

    # Check for help
    help_keywords = ["help", "lost", "confused", "don't know"]
    if any(kw in message_lower for kw in help_keywords):
        result["intent_type"] = "help"
        result["urgency"] = "medium"

    # Check for emergency
    emergency_keywords = ["emergency", "fire", "help me", "urgent", "danger"]
    if any(kw in message_lower for kw in emergency_keywords):
        result["intent_type"] = "emergency"
        result["urgency"] = "high"
        result["function_calls"] = [{
            "name": "alert_humans",
            "args": {"message": f"Emergency reported: {message}"}
        }]

    # Greetings
    greetings = ["hello", "hi", "hey", "good morning", "good afternoon"]
    if any(g in message_lower for g in greetings):
        result["intent_type"] = "greeting"

    # Farewells
    farewells = ["bye", "goodbye", "see you", "thanks", "thank you"]
    if any(f in message_lower for f in farewells):
        result["intent_type"] = "farewell"

    return result


# =============================================================================
# OPERATOR INTENT PARSING (for web dashboard / management)
# =============================================================================

OPERATOR_INTENT_PROMPT = """You are an intent parser for a robot fleet management system.
Analyze the OPERATOR's message and extract structured intent for robot management commands.

IMPORTANT: You must respond with ONLY valid JSON, no other text.

Available intent types:
- "status_query": Operator asking about robot status, battery, locations, health
- "send_command": Operator wants to move/send a robot somewhere
- "announce_command": Operator wants a robot to announce/say something
- "recall_command": Operator wants to recall a robot (to charging/home)
- "system_report": Operator wants a system-wide report
- "general": General question or conversation

Available waypoints: {waypoints}

Extract:
1. intent_type: One of the types above
2. robots_mentioned: List of robot IDs mentioned (e.g., ["robot_01"])
3. commands: List of commands to execute
4. target_location: Destination if moving robot
5. announce_message: Message content if announcing

Available commands:
- send_robot(robot_id, destination): Send robot to a location
- robot_announce(robot_id, message): Make robot announce a message
- get_status(robot_id): Get single robot status
- get_all_status(): Get all robots status
- recall_robot(robot_id): Recall robot to charging
- system_report(): Generate system health report

Example outputs:

Operator: "What is the status of robot_01?"
{{"intent_type": "status_query", "robots_mentioned": ["robot_01"], "commands": [{{"type": "get_status", "robot_id": "robot_01"}}]}}

Operator: "Send robot 1 to the cafeteria"
{{"intent_type": "send_command", "robots_mentioned": ["robot_01"], "commands": [{{"type": "send_robot", "robot_id": "robot_01", "destination": "cafeteria"}}], "target_location": "cafeteria"}}

Operator: "Make all robots announce that the tour is starting"
{{"intent_type": "announce_command", "robots_mentioned": ["all"], "commands": [{{"type": "robot_announce", "robot_id": "all", "message": "The tour is starting"}}], "announce_message": "The tour is starting"}}

Operator: "Show me a system report"
{{"intent_type": "system_report", "robots_mentioned": [], "commands": [{{"type": "system_report"}}]}}

Operator: "Recall robot_02 for charging"
{{"intent_type": "recall_command", "robots_mentioned": ["robot_02"], "commands": [{{"type": "recall_robot", "robot_id": "robot_02"}}]}}

RESPOND WITH ONLY VALID JSON."""


def parse_operator_intent(message: str) -> Dict[str, Any]:
    """
    Parse operator message to extract management intent

    Args:
        message: Operator's command message

    Returns:
        Dictionary with:
            - intent_type: Type of operator intent
            - robots_mentioned: List of robot IDs
            - commands: List of commands to execute
            - raw_message: Original message
    """
    default_result = {
        "intent_type": "general",
        "robots_mentioned": [],
        "commands": [],
        "raw_message": message
    }

    if not LLM_AVAILABLE:
        print("[OPERATOR INTENT] LLM not available, using fallback parsing")
        return _fallback_operator_parse(message)

    try:
        client = get_ollama_client()
        model = get_model_name()

        system_prompt = OPERATOR_INTENT_PROMPT.format(
            waypoints=", ".join(WAYPOINTS)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]

        response = chat_with_retry(client, model, messages, max_retries=2)

        if not response:
            print("[OPERATOR INTENT] No response from LLM, using fallback")
            return _fallback_operator_parse(message)

        content = response.get('message', {}).get('content', '')
        result = _extract_json(content)

        if result:
            result['raw_message'] = message
            print(f"[OPERATOR INTENT] Parsed: {result.get('intent_type')} - commands: {result.get('commands', [])}")
            return result
        else:
            print("[OPERATOR INTENT] Failed to parse JSON, using fallback")
            return _fallback_operator_parse(message)

    except Exception as e:
        print(f"[OPERATOR INTENT] Error parsing intent: {e}")
        return _fallback_operator_parse(message)


def _fallback_operator_parse(message: str) -> Dict[str, Any]:
    """Simple fallback parsing for operator commands"""
    message_lower = message.lower()

    result = {
        "intent_type": "general",
        "robots_mentioned": [],
        "commands": [],
        "raw_message": message
    }

    # Extract robot IDs mentioned
    robot_patterns = [
        r'robot[_\s]?(\d+)',
        r'robot[_\s]?(one|two|three)',
        r'all robots?'
    ]

    for pattern in robot_patterns:
        matches = re.findall(pattern, message_lower)
        for match in matches:
            if match in ['one', '1']:
                result["robots_mentioned"].append("robot_01")
            elif match in ['two', '2']:
                result["robots_mentioned"].append("robot_02")
            elif match in ['three', '3']:
                result["robots_mentioned"].append("robot_03")
            elif 'all' in message_lower:
                result["robots_mentioned"].append("all")
            elif match.isdigit():
                result["robots_mentioned"].append(f"robot_{match.zfill(2)}")

    # Check for status/report requests
    if any(word in message_lower for word in ["status", "report", "how is", "where is", "battery", "health", "show me"]):
        result["intent_type"] = "status_query"

        if "system" in message_lower or "all" in message_lower or not result["robots_mentioned"]:
            result["commands"].append({"type": "get_all_status"})
        else:
            for robot in result["robots_mentioned"]:
                result["commands"].append({"type": "get_status", "robot_id": robot})

    # Check for send/move commands
    elif any(word in message_lower for word in ["send", "move", "navigate", "go to", "take"]):
        result["intent_type"] = "send_command"

        # Try to extract destination
        for waypoint in WAYPOINTS:
            waypoint_variants = [waypoint.lower(), waypoint.lower().replace("_", " ")]
            if any(v in message_lower for v in waypoint_variants):
                robot_id = result["robots_mentioned"][0] if result["robots_mentioned"] else "robot_01"
                result["commands"].append({
                    "type": "send_robot",
                    "robot_id": robot_id,
                    "destination": waypoint
                })
                break

    # Check for announce commands
    elif any(word in message_lower for word in ["announce", "say", "tell", "broadcast"]):
        result["intent_type"] = "announce_command"

        # Try to extract message (simplified)
        quote_match = re.search(r'["\']([^"\']+)["\']', message)
        announce_msg = quote_match.group(1) if quote_match else "Attention please"

        robot_id = result["robots_mentioned"][0] if result["robots_mentioned"] else "all"
        result["commands"].append({
            "type": "robot_announce",
            "robot_id": robot_id,
            "message": announce_msg
        })

    # Check for recall/return commands
    elif any(word in message_lower for word in ["recall", "return", "come back", "charging", "home"]):
        result["intent_type"] = "recall_command"

        robot_id = result["robots_mentioned"][0] if result["robots_mentioned"] else "all"
        result["commands"].append({
            "type": "recall_robot",
            "robot_id": robot_id
        })

    # Check for system report
    elif any(word in message_lower for word in ["system report", "full report", "overview"]):
        result["intent_type"] = "system_report"
        result["commands"].append({"type": "system_report"})

    return result


__all__ = ['parse_intent', 'parse_operator_intent']
