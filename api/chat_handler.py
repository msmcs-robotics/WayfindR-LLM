"""
Chat Handler for WayfindR-LLM
Implements two-phase LLM strategy for chat processing
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
    from agents.intent_parser import parse_intent
    from agents.function_executor import execute_function
    from rag.context_builder import get_context_builder
except ImportError:
    parse_intent = None
    execute_function = None
    get_context_builder = None

# Import logging
try:
    from rag.postgresql_store import add_log
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False
    add_log = None


RESPONSE_SYSTEM_PROMPT = """You are a friendly and helpful tour guide robot assistant.
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
    Handle chat from web dashboard (monitoring/admin focus)

    Args:
        message: User message
        user_id: Optional user identifier

    Returns:
        Chat response
    """
    conversation_id = f"web_{user_id or 'anon'}_{uuid.uuid4().hex[:8]}"

    return await _process_chat(
        message=message,
        conversation_id=conversation_id,
        source="web",
        user_id=user_id,
        robot_id=None
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

    return await _process_chat(
        message=message,
        conversation_id=conversation_id,
        source="robot",
        user_id=user_id,
        robot_id=robot_id
    )


async def _process_chat(
    message: str,
    conversation_id: str,
    source: str,
    user_id: Optional[str],
    robot_id: Optional[str]
) -> Dict[str, Any]:
    """
    Core chat processing with two-phase LLM strategy

    Phase 1: Parse intent
    Phase 2: Generate response
    """
    timestamp = datetime.now().isoformat()

    # Log user message
    if LOGGING_AVAILABLE and add_log:
        add_log(
            message,
            metadata={
                "source": "user",
                "message_type": "command",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "robot_id": robot_id,
                "timestamp": timestamp
            }
        )

    # === PHASE 1: Intent Parsing ===
    print(f"\n[CHAT] Processing message: {message[:50]}...")

    intent = {"intent_type": "smalltalk", "waypoints": [], "function_calls": []}
    if parse_intent:
        intent = parse_intent(message, robot_id)
        print(f"[CHAT] Intent: {intent.get('intent_type')} - waypoints: {intent.get('waypoints', [])}")

    # Execute any function calls
    function_results = []
    if execute_function and intent.get('function_calls'):
        for func_call in intent['function_calls']:
            result = await execute_function(func_call, robot_id)
            function_results.append(result)
            print(f"[CHAT] Function result: {result}")

    # === PHASE 2: Response Generation ===
    response_text = await _generate_response(
        message=message,
        intent=intent,
        function_results=function_results,
        robot_id=robot_id,
        conversation_id=conversation_id
    )

    # Log assistant response
    if LOGGING_AVAILABLE and add_log:
        add_log(
            response_text,
            metadata={
                "source": "llm",
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


async def _generate_response(
    message: str,
    intent: Dict[str, Any],
    function_results: list,
    robot_id: Optional[str],
    conversation_id: Optional[str]
) -> str:
    """Generate LLM response using context and intent"""

    if not LLM_AVAILABLE:
        return _fallback_response(intent, function_results)

    try:
        client = get_ollama_client()
        model = get_model_name()

        # Build context
        context_str = ""
        if get_context_builder:
            builder = get_context_builder()
            context_str = builder.build_system_context()

        # Add function results to context
        if function_results:
            context_str += "\n\nActions taken:"
            for result in function_results:
                if result.get('success'):
                    context_str += f"\n- {result.get('message', 'Action completed')}"

        # Get waypoints from config
        try:
            from core.config import WAYPOINTS
            waypoints = ", ".join(WAYPOINTS)
        except ImportError:
            waypoints = "reception, cafeteria, meeting rooms, elevator, exit"

        # Build system prompt
        system_prompt = RESPONSE_SYSTEM_PROMPT.format(
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
            return response.get('message', {}).get('content', _fallback_response(intent, function_results))
        else:
            return _fallback_response(intent, function_results)

    except Exception as e:
        print(f"[CHAT] Error generating response: {e}")
        return _fallback_response(intent, function_results)


def _fallback_response(intent: Dict[str, Any], function_results: list) -> str:
    """Generate fallback response when LLM is unavailable"""
    intent_type = intent.get('intent_type', 'smalltalk')
    waypoints = intent.get('waypoints', [])

    if intent_type == 'navigation' and waypoints:
        if function_results and function_results[0].get('success'):
            return f"I've queued navigation to {', '.join(waypoints)}. Please follow me!"
        else:
            return f"I can help you get to {', '.join(waypoints)}. Let me guide you there."

    elif intent_type == 'emergency':
        return "I've alerted the staff about your emergency. Help is on the way. Please stay calm."

    elif intent_type == 'help':
        return "I'm here to help! I can guide you to different locations in the building. Where would you like to go?"

    elif intent_type == 'status_query':
        return "I'm a tour guide robot. I can help you navigate this building and answer questions about the facilities."

    else:
        return "Hello! I'm your tour guide robot. I can help you find locations in the building or answer questions. How can I assist you?"


__all__ = [
    'handle_web_chat',
    'handle_robot_chat'
]
