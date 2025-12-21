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
        result["intent_type"] = "smalltalk"

    return result


__all__ = ['parse_intent']
