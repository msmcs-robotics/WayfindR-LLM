import json
from datetime import datetime
from fastapi import Request
from typing import Dict, Any, Optional, List
import uuid
import re

from rag_store import (
    store_chat_message,
    build_conversation_context,
    get_conversation_history
)
from llm_config import get_ollama_client, get_model_name
from prompts import web_chat_prompt, robot_chat_prompt

class ChatHandler:
    """Streamlined handler for web and robot conversations with function calling"""
    
    def __init__(self):
        self.ollama_client = get_ollama_client()
        self.llm_model = get_model_name()
        
        # Available waypoints for navigation
        self.waypoints = {
            'reception', 'cafeteria', 'meeting_room_a', 'meeting_room_b', 
            'elevator', 'exit', 'main_hall'
        }
        
        print(f"✅ ChatHandler initialized with model: {self.llm_model}")

    def _extract_response(self, response):
        """Extract response text from Ollama response"""
        try:
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                return response.message.content
            elif hasattr(response, 'content'):
                return response.content
            elif isinstance(response, dict):
                if 'message' in response and 'content' in response['message']:
                    return response['message']['content']
                elif 'response' in response:
                    return response['response']
            return str(response)
        except Exception as e:
            print(f"❌ Error extracting response: {e}")
            return f"Error extracting response: {e}"

    def _generate_conversation_id(self, user_type: str, user_id: str) -> str:
        """Generate unique conversation ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{user_type}_{user_id}_{timestamp}_{str(uuid.uuid4())[:8]}"

    async def handle_web_chat(self, request: Request) -> Dict[str, Any]:
        """Handle chat messages from web users - for system monitoring/debugging"""
        try:
            data = await request.json()
            message = data.get('message')
            user_id = data.get('user_id', 'web_admin')
            conversation_id = data.get('conversation_id')
            
            if not message:
                return {"error": "No message provided", "success": False}
            
            if not conversation_id:
                conversation_id = self._generate_conversation_id('web', user_id)
            
            print(f"💬 Web chat - User: {user_id}, Conv: {conversation_id}")
            
            # Store user message
            store_chat_message("user", message, conversation_id, "web", user_id)
            
            # Build context and generate response
            context = build_conversation_context(conversation_id, user_id, message)
            
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": web_chat_prompt},
                    {"role": "user", "content": f"User message: {message}\n\nContext: {json.dumps(context, default=str)}"}
                ]
            )
            
            assistant_response = self._extract_response(response)
            
            # Store assistant response
            store_chat_message("assistant", assistant_response, conversation_id, "web", user_id)
            
            return {
                "response": assistant_response,
                "conversation_id": conversation_id,
                "success": True
            }
            
        except Exception as e:
            print(f"❌ Web chat error: {e}")
            return {"error": str(e), "success": False}

    async def handle_robot_chat(self, request: Request) -> Dict[str, Any]:
        """Handle chat messages from robot users with function calling"""
        try:
            data = await request.json()
            robot_id = data.get('robot_id')
            user_message = data.get('user_message')
            conversation_id = data.get('conversation_id')
            
            if not robot_id or not user_message:
                return {"error": "Missing robot_id or user_message", "success": False}
            
            if not conversation_id:
                conversation_id = self._generate_conversation_id('robot', robot_id)
            
            user_id = f"robot_{robot_id}"
            print(f"🤖 Robot chat - Robot: {robot_id}, Conv: {conversation_id}")
            
            # Store user message
            store_chat_message("user", user_message, conversation_id, "robot", user_id)
            
            # Build context and generate response
            context = build_conversation_context(conversation_id, user_id, user_message)
            
            # Enhanced prompt with function calling instructions
            enhanced_prompt = f"""
{robot_chat_prompt}

FUNCTION CALLING:
If user wants navigation, respond with: NAVIGATE_TO: [waypoint1, waypoint2, ...]
If robot reports being stuck, respond with: CREATE_ALERT: [description]

Available waypoints: {', '.join(self.waypoints)}

User message: {user_message}
Robot ID: {robot_id}
Recent conversation: {json.dumps(context.get('conversation_history', [])[-3:], default=str)}
"""
            
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": enhanced_prompt}
                ]
            )
            
            robot_response = self._extract_response(response)
            
            # Process function calls
            function_results = await self._process_function_calls(robot_response, robot_id, user_message)
            
            # Clean response for user (remove function call syntax)
            clean_response = self._clean_response_for_user(robot_response)
            
            # Store robot's response
            store_chat_message("assistant", clean_response, conversation_id, "robot", user_id)
            
            result = {
                "robot_response": clean_response,
                "conversation_id": conversation_id,
                "robot_id": robot_id,
                "success": True
            }
            
            # Add function call results if any
            if function_results:
                result.update(function_results)
            
            return result
            
        except Exception as e:
            print(f"❌ Robot chat error: {e}")
            return {"error": str(e), "success": False}

    async def _process_function_calls(self, response: str, robot_id: str, user_message: str) -> Dict:
        """Process function calls from LLM response"""
        results = {}
        
        # Check for navigation command
        nav_match = re.search(r'NAVIGATE_TO:\s*\[(.*?)\]', response)
        if nav_match:
            waypoints_str = nav_match.group(1)
            waypoints = [w.strip().strip('"\'') for w in waypoints_str.split(',') if w.strip()]
            # Validate waypoints
            valid_waypoints = [w for w in waypoints if w in self.waypoints]
            if valid_waypoints:
                nav_result = await self.send_navigation_command(robot_id, valid_waypoints)
                results['navigation_command'] = nav_result
                print(f"🧭 Navigation command sent: {valid_waypoints}")
        
        # Check for alert creation
        alert_match = re.search(r'CREATE_ALERT:\s*\[(.*?)\]', response)
        if alert_match:
            alert_description = alert_match.group(1).strip().strip('"\'')
            alert_result = await self.create_stuck_alert(robot_id, alert_description)
            results['alert_created'] = alert_result
            print(f"🚨 Alert created: {alert_description}")
        
        # Auto-detect stuck condition from user message
        if any(word in user_message.lower() for word in ['stuck', 'help', 'problem', 'error', 'cannot move']):
            if 'alert_created' not in results:  # Don't duplicate alerts
                alert_result = await self.create_stuck_alert(robot_id, f"User reported issue: {user_message}")
                results['alert_created'] = alert_result
                print(f"🚨 Auto-alert for stuck robot: {robot_id}")
        
        return results

    def _clean_response_for_user(self, response: str) -> str:
        """Remove function call syntax from user-facing response"""
        # Remove function call lines
        response = re.sub(r'NAVIGATE_TO:\s*\[.*?\]\n?', '', response)
        response = re.sub(r'CREATE_ALERT:\s*\[.*?\]\n?', '', response)
        return response.strip()

    async def get_conversation_history(self, conversation_id: str) -> Dict[str, Any]:
        """Get conversation history by ID"""
        try:
            messages = get_conversation_history(conversation_id)
            return {
                "conversation_id": conversation_id,
                "messages": messages,
                "message_count": len(messages),
                "success": True
            }
        except Exception as e:
            print(f"❌ Get conversation history error: {e}")
            return {"error": str(e), "success": False}

    # ── FUNCTION IMPLEMENTATIONS ───────────────────────────
    async def create_stuck_alert(self, robot_id: str, message: str) -> Dict[str, Any]:
        """Create alert when robot is stuck (placeholder for real alert system)"""
        try:
            alert_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # This is where you'd integrate with your actual alert system
            # For now, just log and return success
            print(f"🚨 STUCK ALERT [{alert_id}] - Robot {robot_id}: {message}")
            
            # TODO: Integrate with actual alerting system (email, SMS, dashboard, etc.)
            
            return {
                "alert_id": alert_id,
                "robot_id": robot_id,
                "message": message,
                "timestamp": timestamp,
                "status": "alert_created",
                "success": True
            }
            
        except Exception as e:
            print(f"❌ Create alert error: {e}")
            return {"error": str(e), "success": False}

    async def send_navigation_command(self, robot_id: str, waypoints: List[str]) -> Dict[str, Any]:
        """Send navigation command to robot (placeholder for real robot communication)"""
        try:
            command_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # This is where you'd send actual commands to your robot
            # For now, just log and return success
            print(f"🧭 NAVIGATION COMMAND [{command_id}] - Robot {robot_id}: {' -> '.join(waypoints)}")
            
            # TODO: Integrate with actual robot communication system
            
            return {
                "command_id": command_id,
                "robot_id": robot_id,
                "waypoints": waypoints,
                "timestamp": timestamp,
                "status": "command_sent",
                "success": True
            }
            
        except Exception as e:
            print(f"❌ Navigation command error: {e}")
            return {"error": str(e), "success": False}