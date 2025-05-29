# llm_intent_parser.py - Streamlined with ollama integration
from typing import Dict, List, Any
import ollama
import json
import re
from config_manager import get_config

class LLMIntentParser:
    def __init__(self):
        self.config = get_config()
        self.ollama_client = ollama.Client()
        self.llm_model = self.config.llm.model_name
        print("✅ LLMIntentParser initialized")

    async def _parse_with_llm(self, prompt: str) -> Dict:
        """Base method for LLM parsing"""
        try:
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[{"role": "system", "content": prompt}]
            )
            return self._extract_json(response['message']['content'])
        except Exception as e:
            print(f"❌ LLM parsing error: {e}")
            return None

    async def parse_web_intent(self, message: str) -> Dict[str, Any]:
        """Parse web user message for monitoring and fleet overview"""
        intent_prompt = f"""Analyze this web user's robot monitoring message. Return ONLY valid JSON:

{{
    "intent_type": "general_status" | "fleet_overview" | "specific_robot" | "chat",
    "needs_robot_data": true/false,
    "keywords": ["keyword1", "keyword2"],
    "urgency": "low" | "medium" | "high"
}}

USER MESSAGE: {message}

JSON:"""

        parsed_json = await self._parse_with_llm(intent_prompt)
        return self._validate_web_intent(parsed_json or {})

    async def parse_robot_intent(self, message: str, robot_id: str, waypoints: List[str]) -> Dict[str, Any]:
        """Parse robot user message for navigation and assistance"""
        intent_prompt = f"""Analyze this user's message to robot {robot_id}. Return ONLY valid JSON:

AVAILABLE WAYPOINTS: {', '.join(waypoints)}

{{
    "intent_type": "navigation" | "emergency" | "chat" | "help",
    "function_calls": [list of function objects],
    "mentioned_waypoints": ["waypoint1"],
    "urgency": "low" | "medium" | "high"
}}

FUNCTION FORMATS:
- Navigation: {{"function": "navigate_to_waypoint", "waypoints": ["cafeteria"]}}
- Emergency: {{"function": "alert_humans", "message": "description"}}

USER MESSAGE: {message}

JSON:"""

        parsed_json = await self._parse_with_llm(intent_prompt)
        return self._validate_web_intent(parsed_json or {})

    def _extract_json(self, text: str) -> Dict:
        """Extract JSON from LLM response"""
        try:
            # Try direct JSON parsing first
            return json.loads(text.strip())
        except:
            # Try to find JSON in text
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            return None

    def _validate_web_intent(self, parsed: Dict) -> Dict[str, Any]:
        """Validate web intent structure"""
        return {
            "intent_type": parsed.get("intent_type", "chat"),
            "needs_robot_data": parsed.get("needs_robot_data", True),
            "keywords": parsed.get("keywords", [])[:5],
            "urgency": parsed.get("urgency", "low")
        }

    def _validate_robot_intent(self, parsed: Dict, waypoints: List[str]) -> Dict[str, Any]:
        """Validate robot intent structure"""
        # Filter valid waypoints
        mentioned_waypoints = [wp for wp in parsed.get("mentioned_waypoints", []) if wp in waypoints]
        
        # Validate function calls
        function_calls = []
        for func in parsed.get("function_calls", []):
            if func.get("function") == "navigate_to_waypoint":
                valid_waypoints = [wp for wp in func.get("waypoints", []) if wp in waypoints]
                if valid_waypoints:
                    function_calls.append({"function": "navigate_to_waypoint", "waypoints": valid_waypoints})
            elif func.get("function") == "alert_humans":
                function_calls.append(func)
        
        return {
            "intent_type": parsed.get("intent_type", "chat"),
            "function_calls": function_calls,
            "mentioned_waypoints": mentioned_waypoints,
            "urgency": parsed.get("urgency", "low")
        }

    def _fallback_web_intent(self, message: str) -> Dict[str, Any]:
        """Simple fallback for web messages"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['robot', 'fleet', 'status']):
            intent_type = "fleet_overview" if 'fleet' in message_lower else "general_status"
            needs_data = True
        else:
            intent_type = "chat"
            needs_data = False
        
        return {
            "intent_type": intent_type,
            "needs_robot_data": needs_data,
            "keywords": [word for word in message.split()[:3] if len(word) > 2],
            "urgency": "high" if any(word in message_lower for word in ['urgent', 'emergency']) else "low"
        }

    def _fallback_robot_intent(self, message: str, waypoints: List[str]) -> Dict[str, Any]:
        """Simple fallback for robot messages"""
        message_lower = message.lower()
        mentioned_waypoints = [wp for wp in waypoints if wp.lower() in message_lower]
        
        function_calls = []
        intent_type = "chat"
        urgency = "low"
        
        # Navigation detection
        if any(word in message_lower for word in ['take me', 'go to', 'navigate']) and mentioned_waypoints:
            function_calls.append({"function": "navigate_to_waypoint", "waypoints": mentioned_waypoints})
            intent_type = "navigation"
            urgency = "medium"
        
        # Emergency detection
        elif any(word in message_lower for word in ['help', 'stuck', 'emergency']):
            function_calls.append({"function": "alert_humans", "message": f"User message: {message}"})
            intent_type = "emergency"
            urgency = "high"
        
        return {
            "intent_type": intent_type,
            "function_calls": function_calls,
            "mentioned_waypoints": mentioned_waypoints,
            "urgency": urgency
        }