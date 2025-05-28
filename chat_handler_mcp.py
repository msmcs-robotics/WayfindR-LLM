import json
from datetime import datetime
from fastapi import Request
from rag_store import (
    store_chat_message,
    build_conversation_context,
    search_telemetry_context,
    get_recent_chat_messages  # Add this import
)
from llm_config import get_ollama_client, get_model_name
from prompts import (
    handle_chat_prompt,
    handle_llm_command_prompt,
    handle_robot_message_prompt
)

class ChatHandler:
    """Simplified chat handler focusing on core functionality with enhanced debugging"""
    
    def __init__(self, mcp=None):  # Accept mcp parameter
        self.mcp = mcp
        self.ollama_client = get_ollama_client()
        self.llm_model = get_model_name()
        print(f"✅ ChatHandler initialized with model: {self.llm_model}")
        print(f"🔧 Ollama client: {self.ollama_client}")

    def _extract_response(self, response):
        """Extract response text from Ollama response object with debugging"""
        try:
            print(f"🔍 [DEBUG] Raw Ollama response type: {type(response)}")
            print(f"🔍 [DEBUG] Raw Ollama response: {response}")
            
            if hasattr(response, 'message'):
                content = response.message.content if hasattr(response.message, 'content') else str(response.message)
                print(f"✅ [DEBUG] Extracted content via .message.content: {content}")
                return content
            elif hasattr(response, 'content'):
                print(f"✅ [DEBUG] Extracted content via .content: {response.content}")
                return response.content
            elif isinstance(response, dict):
                if 'message' in response and 'content' in response['message']:
                    content = response['message']['content']
                    print(f"✅ [DEBUG] Extracted content from dict: {content}")
                    return content
                elif 'response' in response:
                    print(f"✅ [DEBUG] Extracted content from dict response: {response['response']}")
                    return response['response']
            else:
                content = str(response)
                print(f"⚠️ [DEBUG] Fallback to string conversion: {content}")
                return content
        except Exception as e:
            print(f"❌ [DEBUG] Error extracting response: {e}")
            return f"Error extracting response: {e}"

    # Add the missing handle_chat method that the frontend expects
    async def handle_chat(self, request: Request):
        """Main chat endpoint that was missing from the original code"""
        try:
            print(f"📨 [DEBUG] Chat request received")
            data = await request.json()
            print(f"🔍 [DEBUG] Request data: {data}")
            
            message = data.get('message')
            user_id = data.get('user_id', 'anonymous')
            
            if not message:
                print(f"❌ [DEBUG] No message provided")
                return {"error": "No message provided", "success": False}
            
            print(f"💬 [DEBUG] Processing message: '{message}' from user: {user_id}")
            
            # Store user message
            message_id = store_chat_message("user", message, user_id)
            print(f"✅ [DEBUG] Stored user message with ID: {message_id}")
            
            # Build context
            context = build_conversation_context(message, user_id)
            print(f"📚 [DEBUG] Built context: {context.get('context_summary', 'No summary')}")
            
            # Prepare prompts
            system_prompt = handle_chat_prompt
            user_prompt = f"User message: {message}\n\nRecent context: {json.dumps(context, indent=2)}"
            
            print(f"🤖 [DEBUG] Calling Ollama with model: {self.llm_model}")
            print(f"🔧 [DEBUG] System prompt: {system_prompt}")
            print(f"🔧 [DEBUG] User prompt length: {len(user_prompt)} chars")
            
            # Call Ollama
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            print(f"📥 [DEBUG] Received Ollama response")
            assistant_response = self._extract_response(response)
            print(f"✅ [DEBUG] Extracted response: {assistant_response[:100]}...")
            
            # Store assistant response
            response_id = store_chat_message("assistant", assistant_response, user_id)
            print(f"✅ [DEBUG] Stored assistant message with ID: {response_id}")
            
            return {
                "response": assistant_response, 
                "success": True,
                "user_id": user_id,
                "message_id": response_id
            }
            
        except Exception as e:
            print(f"❌ [DEBUG] Chat handler error: {e}")
            import traceback
            print(f"❌ [DEBUG] Full traceback: {traceback.format_exc()}")
            return {"error": str(e), "success": False}

    async def handle_llm_command(self, request: Request):
        """Process natural language commands for robot navigation"""
        try:
            print(f"🤖 [DEBUG] LLM Command request received")
            data = await request.json()
            print(f"🔍 [DEBUG] Command data: {data}")
            
            command = data.get('command') or data.get('message')  # Support both field names
            user_id = data.get('user_id', 'anonymous')
            
            if not command:
                print(f"❌ [DEBUG] No command provided")
                return {"error": "No command provided", "success": False}
            
            print(f"⚡ [DEBUG] Processing command: '{command}' from user: {user_id}")
            
            # Store command as user message
            store_chat_message("user", f"Command: {command}", user_id)
            
            # Process with context
            context = build_conversation_context(command, user_id)
            system_prompt = handle_llm_command_prompt
            
            # Convert context to JSON-safe format with multiple fallbacks
            try:
                context_str = json.dumps(context, indent=2, default=str)
            except TypeError as e:
                print(f"⚠️ [DEBUG] JSON serialization error (first attempt): {e}")
                try:
                    # Try with a more aggressive serializer
                    from json import JSONEncoder
                    class DateTimeEncoder(JSONEncoder):
                        def default(self, o):
                            if isinstance(o, datetime):
                                return o.isoformat()
                            return super().default(o)
                    context_str = json.dumps(context, indent=2, cls=DateTimeEncoder)
                except Exception as e:
                    print(f"⚠️ [DEBUG] JSON serialization error (second attempt): {e}")
                    context_str = str(context)
            
            user_prompt = f"Command: {command}\nContext: {context_str}"
            
            print(f"🤖 [DEBUG] Calling Ollama for command processing")
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            assistant_response = self._extract_response(response)
            print(f"✅ [DEBUG] Command response: {assistant_response[:100]}...")
            
            store_chat_message("assistant", assistant_response, user_id)
            
            return {
                "response": assistant_response, 
                "command_processed": True,
                "success": True
            }
            
        except Exception as e:
            print(f"❌ [DEBUG] LLM Command error: {e}")
            import traceback
            print(f"❌ [DEBUG] Full traceback: {traceback.format_exc()}")
            return {"error": str(e), "success": False}

    async def handle_robot_message(self, request: Request):
        """Handle messages from robots requesting assistance"""
        try:
            print(f"🤖 [DEBUG] Robot message request received")
            data = await request.json()
            robot_id = data.get('robot_id')
            message = data.get('message')
            
            if not robot_id or not message:
                return {"error": "Missing robot_id or message", "success": False}
            
            print(f"🤖 [DEBUG] Robot {robot_id} message: {message}")
            
            # Store robot message
            store_chat_message("robot", message, robot_id)
            
            # Get context specific to this robot
            context = build_conversation_context(message, robot_id=robot_id)
            
            system_prompt = handle_robot_message_prompt
            user_prompt = f"Robot {robot_id} says: {message}\nContext: {json.dumps(context, indent=2)}"
            
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            assistant_response = self._extract_response(response)
            store_chat_message("assistant", assistant_response, robot_id)
            
            return {
                "response": assistant_response, 
                "robot_id": robot_id,
                "success": True
            }
            
        except Exception as e:
            print(f"❌ [DEBUG] Robot message error: {e}")
            return {"error": str(e), "success": False}

    async def get_logs(self):
        """Get chat and command logs"""
        try:
            print(f"📋 [DEBUG] Getting logs")
            messages = get_recent_chat_messages(limit=50)
            print(f"✅ [DEBUG] Retrieved {len(messages)} messages")
            return {"logs": messages, "count": len(messages)}
        except Exception as e:
            print(f"❌ [DEBUG] Get logs error: {e}")
            return {"error": str(e)}

    async def get_log_count(self):
        """Get current log count"""
        try:
            messages = get_recent_chat_messages(limit=1000)  # Get more for count
            print(f"📊 [DEBUG] Log count: {len(messages)}")
            return {"count": len(messages)}
        except Exception as e:
            print(f"❌ [DEBUG] Get log count error: {e}")
            return {"error": str(e)}

    # Navigation methods (simplified - you may need to implement actual robot control)
    async def navigate_to_waypoint(self, waypoint_name: str):
        """Navigate robot to a single waypoint"""
        print(f"🧭 [DEBUG] Navigate to waypoint: {waypoint_name}")
        return {"status": "navigation_started", "waypoint": waypoint_name}

    async def navigate_multiple_waypoints(self, waypoints: list):
        """Navigate robot through multiple waypoints"""
        print(f"🧭 [DEBUG] Navigate multiple waypoints: {waypoints}")
        return {"status": "multi_navigation_started", "waypoints": waypoints}

    async def emergency_stop(self, robot_id: str = None):
        """Emergency stop for robot(s)"""
        print(f"🛑 [DEBUG] Emergency stop for robot: {robot_id}")
        return {"status": "emergency_stop_activated", "robot_id": robot_id}

    async def pause_simulation(self):
        """Pause robot navigation"""
        print(f"⏸️ [DEBUG] Pause simulation")
        return {"status": "simulation_paused"}

    async def continue_simulation(self):
        """Resume robot navigation"""
        print(f"▶️ [DEBUG] Continue simulation")
        return {"status": "simulation_resumed"}

    async def get_simulation_info(self):
        """Get robot and navigation system information"""
        print(f"ℹ️ [DEBUG] Get simulation info")
        return {"status": "active", "robots": [], "simulation": "running"}

    async def get_chat_history(self, limit: int = 10, user_id: str = None):
        """Get chat history for a user"""
        try:
            print(f"📜 [DEBUG] Getting chat history - limit: {limit}, user_id: {user_id}")
            messages = get_recent_chat_messages(limit, user_id)
            print(f"✅ [DEBUG] Retrieved {len(messages)} chat history messages")
            return {"messages": messages, "count": len(messages)}
        except Exception as e:
            print(f"❌ [DEBUG] Get chat history error: {e}")
            return {"error": str(e)}