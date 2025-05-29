# chat_handler.py - Fixed LLM response handling
from datetime import datetime
from fastapi import Request
from typing import Dict, Any
import ollama
import traceback
import json

from function_executor import FunctionExecutor
from llm_intent_parser import LLMIntentParser
from context_manager import get_context_manager
from config_manager import get_config
from utils import generate_conversation_id, success_response, error_response

class ChatHandler:
    def __init__(self):
        self.config = get_config()
        self.ollama_client = ollama.Client()
        self.llm_model = self.config.llm.model_name
        
        # Initialize components
        self.intent_parser = LLMIntentParser()
        self.function_executor = FunctionExecutor()
        self.context_manager = get_context_manager()
        
        # Get waypoints from config
        self.waypoints = set(self.config.robot.waypoints)
        print(f"✅ ChatHandler initialized with {len(self.waypoints)} waypoints")

    async def handle_web_chat(self, request: Request) -> Dict[str, Any]:
        try:
            data = await request.json()
            message = data.get('message')
            user_id = data.get('user_id', 'web_admin')
            conversation_id = data.get('conversation_id') or generate_conversation_id('web', user_id)
            
            if not message:
                return error_response("No message provided")
            
            print(f"💬 Web chat - User: {user_id}, Conv: {conversation_id}")
            print(f"💬 User message: {message}")
            
            # Store user message
            message_id = await self.context_manager.db.store_chat_message("user", message, conversation_id, "web", user_id)
            print(f"✅ Stored user message with ID: {message_id}")
            
            # Phase 1: Parse intent
            intent_data = await self.intent_parser.parse_web_intent(message)
            print(f"🎯 Intent parsed: {intent_data}")
            
            # Phase 2: Build context and generate response
            context = await self.context_manager.build_web_context(conversation_id, user_id, message, intent_data)
            print(f"📝 Context built: {len(context.get('active_robots', []))} active robots")
            
            response = await self._generate_web_response(context, intent_data, message)
            print(f"🤖 Generated response: {response[:100]}..." if len(response) > 100 else f"🤖 Generated response: {response}")
            
            # Store assistant response
            response_id = await self.context_manager.db.store_chat_message("assistant", response, conversation_id, "web", user_id)
            print(f"✅ Stored assistant response with ID: {response_id}")
            
            result = {
                "response": response,
                "conversation_id": conversation_id,
                "intent_data": intent_data,
                "active_robots": context.get('active_robots', [])
            }
            
            print(f"📤 Returning success response: {json.dumps(result, indent=2)}")
            return success_response(result)
            
        except Exception as e:
            print(f"❌ Web chat error: {repr(e)}")
            traceback.print_exc()
            return error_response(str(e))

    async def handle_robot_chat(self, request: Request) -> Dict[str, Any]:
        """Handle robot user chat - navigation and small talk focused"""
        try:
            data = await request.json()
            robot_id = data.get('robot_id')
            user_message = data.get('user_message')
            conversation_id = data.get('conversation_id') or generate_conversation_id('robot', robot_id)
            
            if not robot_id or not user_message:
                return error_response("Missing robot_id or user_message")
            
            user_id = f"robot_{robot_id}"
            print(f"🤖 Robot chat - Robot: {robot_id}")
            
            # Store user message
            await self.context_manager.db.store_chat_message("user", user_message, conversation_id, "robot", user_id)
            
            # Phase 1: Parse intent and function calls
            intent_data = await self.intent_parser.parse_robot_intent(user_message, robot_id, list(self.waypoints))
            
            # Execute function calls if any
            function_results = {}
            if intent_data.get('function_calls'):
                function_results = await self.function_executor.execute_functions(
                    intent_data['function_calls'], robot_id, user_message
                )
            
            # Phase 2: Generate response
            context = await self.context_manager.build_robot_context(conversation_id, robot_id)
            response = await self._generate_robot_response(context, intent_data, function_results, user_message, robot_id)
            
            # Store response
            await self.context_manager.db.store_chat_message("assistant", response, conversation_id, "robot", user_id)
            
            result_data = {
                "robot_response": response,
                "conversation_id": conversation_id,
                "robot_id": robot_id,
                "intent_data": intent_data
            }
            
            if function_results:
                result_data["function_results"] = function_results
            
            return success_response(result_data)
            
        except Exception as e:
            print(f"❌ Robot chat error: {repr(e)}")
            traceback.print_exc()
            return error_response(str(e))

    async def _generate_web_response(self, context: Dict, intent_data: Dict, message: str) -> str:
        prompt = self._build_web_prompt(context, intent_data, message)
        print(f"🔍 LLM prompt preview: {prompt[:200]}...")
        
        try:
            # FIXED: Use proper ollama.chat() call with messages array
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "user", "content": prompt}  # Changed from system to user
                ]
            )
            
            print(f"🔍 Full LLM response: {response}")
            
            # Extract content from the nested message structure
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                content = response.message.content
            elif isinstance(response, dict) and 'message' in response:
                content = response['message'].get('content', '')
            else:
                print(f"⚠️ Unexpected response structure: {response}")
                content = str(response)
            
            # Check if content is empty or whitespace
            if not content or not content.strip():
                print("⚠️ LLM returned empty content! Using fallback response.")
                return "I understand your message, but I'm having trouble generating a response right now. Could you please try rephrasing your question?"
            
            print(f"✅ LLM content extracted successfully: {len(content)} characters")
            return content.strip()
            
        except Exception as e:
            print(f"❌ LLM call failed: {e}")
            traceback.print_exc()
            return "Sorry, I encountered an error while processing your request. Please try again."

    async def _generate_robot_response(self, context: Dict, intent_data: Dict, 
                                     function_results: Dict, user_message: str, robot_id: str) -> str:
        """Generate response for robot users"""
        prompt = self._build_robot_prompt(robot_id, context, intent_data, function_results, user_message)
        
        try:
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "user", "content": prompt}  # Changed from system to user
                ]
            )
            
            # Extract content properly
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                content = response.message.content
            elif isinstance(response, dict) and 'message' in response:
                content = response['message'].get('content', '')
            else:
                content = str(response)
            
            return content.strip() if content else "I'm sorry, I couldn't process that request."
            
        except Exception as e:
            print(f"❌ Robot LLM call failed: {e}")
            return "Sorry, I'm having trouble responding right now."

    def _build_web_prompt(self, context: Dict, intent_data: Dict, message: str) -> str:
        """Build prompt for web users - IMPROVED"""
        active_robots = context.get('active_robots', [])
        robot_status = context.get('robot_status', [])
        
        # Build a more comprehensive prompt
        prompt = f"""You are a helpful robot fleet monitoring assistant. Please respond naturally and conversationally to user questions about robots and system status.

CURRENT SYSTEM STATUS:
- Active Robots: {', '.join(active_robots) if active_robots else 'None currently active'}
- Number of robots with recent telemetry: {len(robot_status)}
- Intent detected: {intent_data.get('intent_type', 'general conversation')}

USER QUESTION: "{message}"

Please provide a helpful, friendly response. If the user is asking about robots, mention which ones are currently active. Keep your response conversational and informative. Always provide a complete response."""

        return prompt

    def _build_robot_prompt(self, robot_id: str, context: Dict, intent_data: Dict, 
                           function_results: Dict, user_message: str) -> str:
        """Build prompt for robot users - IMPROVED"""
        function_info = ""
        if function_results:
            if 'navigation_command' in function_results:
                nav = function_results['navigation_command']
                if nav.get('success'):
                    function_info = f"✅ Navigation command executed: {' -> '.join(nav.get('waypoints', []))}"
                else:
                    function_info = f"❌ Navigation failed: {nav.get('error', 'Unknown error')}"
            
            if 'alert_created' in function_results:
                alert = function_results['alert_created']
                function_info += f"\n🚨 Alert created (Priority: {alert.get('priority', 'MEDIUM')})"

        prompt = f"""You are the assistant for Robot {robot_id}. Respond helpfully and naturally to the user.

AVAILABLE WAYPOINTS: {', '.join(self.waypoints)}
DETECTED INTENT: {intent_data.get('intent_type', 'general chat')}

{function_info if function_info else ''}

USER MESSAGE: "{user_message}"

Please respond in a friendly, helpful manner. If navigation was requested and executed, confirm the action. Always provide a complete response."""

        return prompt

    async def get_conversation_history(self, conversation_id: str) -> Dict[str, Any]:
        """Get conversation history by ID"""
        try:
            messages = await self.context_manager.db.get_conversation_history(conversation_id)
            return success_response({
                "conversation_id": conversation_id,
                "messages": messages,
                "message_count": len(messages)
            })
        except Exception as e:
            return error_response(str(e))