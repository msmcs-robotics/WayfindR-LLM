import json
from datetime import datetime
from fastapi import Request
from typing import Dict, Any, Optional
from rag_store import (
    store_chat_message,
    build_conversation_context,
    get_recent_chat_messages,
    store_telemetry_vector
)
from llm_config import get_ollama_client, get_model_name
from prompts import handle_robot_chat_prompt

class RobotChatHandler:
    """Handler for robot-initiated conversations with users"""
    
    def __init__(self, mcp=None):
        self.mcp = mcp
        self.ollama_client = get_ollama_client()
        self.llm_model = get_model_name()
        print(f"✅ RobotChatHandler initialized with model: {self.llm_model}")

    def _extract_response(self, response):
        """Extract response text from Ollama response (reused from ChatHandler)"""
        try:
            if hasattr(response, 'message'):
                content = response.message.content if hasattr(response.message, 'content') else str(response.message)
                return content
            elif hasattr(response, 'content'):
                return response.content
            elif isinstance(response, dict):
                if 'message' in response and 'content' in response['message']:
                    return response['message']['content']
                elif 'response' in response:
                    return response['response']
            else:
                return str(response)
        except Exception as e:
            print(f"❌ [DEBUG] Error extracting response: {e}")
            return f"Error extracting response: {e}"

    async def handle_robot_chat(self, request: Request) -> Dict[str, Any]:
        """
        Handle chat messages from robots talking to users
        
        Expected format:
        {
            "robot_id": "robot_1",
            "user_message": "Hello there!",
            "conversation_id": "conv_123", # Optional: track conversations
            "user_id": "tablet_user_456", # Optional: identify user on tablet
            "context": {
                "location": "entrance",
                "greeting_type": "arrival",
                "user_detected": true
            }
        }
        """
        try:
            print(f"🤖💬 [DEBUG] Robot chat request received")
            data = await request.json()
            print(f"🔍 [DEBUG] Robot chat data: {data}")
            
            robot_id = data.get('robot_id')
            user_message = data.get('user_message')
            conversation_id = data.get('conversation_id')
            user_id = data.get('user_id', 'tablet_user')
            context = data.get('context', {})
            
            if not robot_id or not user_message:
                print(f"❌ [DEBUG] Missing robot_id or user_message")
                return {"error": "Missing robot_id or user_message", "success": False}
            
            # Create unique conversation identifier
            if not conversation_id:
                conversation_id = f"{robot_id}_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            print(f"🤖💬 [DEBUG] Processing robot chat - Robot: {robot_id}, User: {user_id}, Conv: {conversation_id}")
            
            # Store user message with robot context
            user_metadata = {
                "conversation_id": conversation_id,
                "robot_id": robot_id,
                "message_type": "robot_chat_user",
                "context": context
            }
            
            user_message_id = store_chat_message(
                role="user", 
                content=user_message, 
                user_id=f"{robot_id}_{user_id}",  # Composite ID for robot conversations
                metadata=user_metadata
            )
            
            print(f"✅ [DEBUG] Stored user message with ID: {user_message_id}")
            
            # Build conversation context (includes both chat history and telemetry)
            context_data = build_conversation_context(
                query=user_message, 
                user_id=f"{robot_id}_{user_id}",
                robot_id=robot_id
            )
            
            # Enhance context with robot-specific information
            enhanced_context = self._enhance_robot_context(context_data, robot_id, context)
            
            # Prepare prompts for robot conversation
            system_prompt = handle_robot_chat_prompt
            user_prompt = self._build_robot_chat_prompt(
                robot_id=robot_id,
                user_message=user_message,
                conversation_id=conversation_id,
                context=enhanced_context,
                additional_context=context
            )
            
            print(f"🤖 [DEBUG] Calling Ollama for robot chat response")
            print(f"🔧 [DEBUG] System prompt length: {len(system_prompt)} chars")
            print(f"🔧 [DEBUG] User prompt length: {len(user_prompt)} chars")
            
            # Get LLM response
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            robot_response = self._extract_response(response)
            print(f"✅ [DEBUG] Generated robot response: {robot_response[:100]}...")
            
            # Store robot's response
            robot_metadata = {
                "conversation_id": conversation_id,
                "robot_id": robot_id,
                "message_type": "robot_chat_assistant",
                "context": context,
                "responding_to": user_message_id
            }
            
            response_id = store_chat_message(
                role="assistant", 
                content=robot_response, 
                user_id=f"{robot_id}_{user_id}",
                metadata=robot_metadata
            )
            
            print(f"✅ [DEBUG] Stored robot response with ID: {response_id}")
            
            # Store conversation context as telemetry for future reference
            await self._store_conversation_telemetry(
                robot_id=robot_id,
                conversation_id=conversation_id,
                user_message=user_message,
                robot_response=robot_response,
                context=context
            )
            
            return {
                "robot_response": robot_response,
                "conversation_id": conversation_id,
                "robot_id": robot_id,
                "user_id": user_id,
                "message_id": response_id,
                "success": True
            }
            
        except Exception as e:
            print(f"❌ [DEBUG] Robot chat handler error: {e}")
            import traceback
            print(f"❌ [DEBUG] Full traceback: {traceback.format_exc()}")
            return {"error": str(e), "success": False}

    def _enhance_robot_context(self, context_data: Dict, robot_id: str, additional_context: Dict) -> Dict:
        """Enhance context with robot-specific information"""
        enhanced = context_data.copy()
        
        # Add robot-specific context
        enhanced["robot_context"] = {
            "robot_id": robot_id,
            "location": additional_context.get("location", "unknown"),
            "greeting_type": additional_context.get("greeting_type", "general"),
            "user_detected": additional_context.get("user_detected", False),
            "interaction_timestamp": datetime.now().isoformat()
        }
        
        # Analyze telemetry context for robot state
        if enhanced["telemetry_context"]:
            latest_telemetry = enhanced["telemetry_context"][0]  # Most recent
            enhanced["robot_context"]["current_status"] = {
                "position": latest_telemetry.get("telemetry", {}).get("position", {}),
                "navigation_status": latest_telemetry.get("telemetry", {}).get("navigation_status", "unknown"),
                "is_stuck": latest_telemetry.get("telemetry", {}).get("is_stuck", False),
                "current_waypoint": latest_telemetry.get("telemetry", {}).get("current_waypoint")
            }
        
        return enhanced

    def _build_robot_chat_prompt(self, robot_id: str, user_message: str, conversation_id: str, 
                                context: Dict, additional_context: Dict) -> str:
        """Build comprehensive prompt for robot chat interaction"""
        
        # Get recent conversation history for this specific robot-user pair
        recent_messages = context.get("chat_history", [])
        
        conversation_history = ""
        if recent_messages:
            conversation_history = "\n".join([
                f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:100]}..."
                for msg in recent_messages[-3:]  # Last 3 messages for context
            ])
        
        # Build robot status summary
        robot_status = "unknown"
        location_info = additional_context.get("location", "unknown location")
        
        if context.get("robot_context", {}).get("current_status"):
            status = context["robot_context"]["current_status"]
            robot_status = f"at {location_info}, navigation status: {status.get('navigation_status', 'unknown')}"
        
        prompt = f"""
Robot Chat Interaction:

Robot ID: {robot_id}
Conversation ID: {conversation_id}
Robot Status: {robot_status}
User Location: {location_info}
Greeting Type: {additional_context.get('greeting_type', 'general')}

Current User Message: {user_message}

Recent Conversation:
{conversation_history if conversation_history else "No previous conversation"}

Telemetry Context:
{json.dumps(context.get('telemetry_context', [])[:2], indent=2)}

Robot Context:
{json.dumps(context.get('robot_context', {}), indent=2)}

Please generate an appropriate response for the robot to say to the user.
"""
        
        return prompt.strip()

    async def _store_conversation_telemetry(self, robot_id: str, conversation_id: str, 
                                          user_message: str, robot_response: str, context: Dict):
        """Store conversation as telemetry for vector search and context building"""
        try:
            # Create telemetry data for conversation
            conversation_telemetry = {
                "timestamp": datetime.now().isoformat(),
                "conversation_id": conversation_id,
                "interaction_type": "user_chat",
                "user_message": user_message,
                "robot_response": robot_response,
                "location": context.get("location", "unknown"),
                "greeting_type": context.get("greeting_type", "general"),
                "user_detected": context.get("user_detected", False),
                "conversation_length": len(user_message) + len(robot_response),
                "interaction_successful": True
            }
            
            # Store in Qdrant for future context retrieval
            vector_id = store_telemetry_vector(robot_id, conversation_telemetry)
            print(f"✅ [DEBUG] Stored conversation telemetry with vector ID: {vector_id}")
            
        except Exception as e:
            print(f"⚠️ [DEBUG] Could not store conversation telemetry: {e}")

    async def get_conversation_history(self, request: Request) -> Dict[str, Any]:
        """Get conversation history for a specific robot-user pair"""
        try:
            data = await request.json()
            robot_id = data.get('robot_id')
            user_id = data.get('user_id', 'tablet_user')
            conversation_id = data.get('conversation_id')
            limit = data.get('limit', 20)
            
            if not robot_id:
                return {"error": "Missing robot_id", "success": False}
            
            composite_user_id = f"{robot_id}_{user_id}"
            
            # Get messages for this robot-user combination
            messages = get_recent_chat_messages(limit=limit, user_id=composite_user_id)
            
            # Filter by conversation_id if provided
            if conversation_id:
                messages = [
                    msg for msg in messages 
                    if msg.get('metadata', {}).get('conversation_id') == conversation_id
                ]
            
            # Group by conversation_id
            conversations = {}
            for msg in messages:
                conv_id = msg.get('metadata', {}).get('conversation_id', 'unknown')
                if conv_id not in conversations:
                    conversations[conv_id] = []
                conversations[conv_id].append(msg)
            
            return {
                "robot_id": robot_id,
                "user_id": user_id,
                "conversations": conversations,
                "total_messages": len(messages),
                "success": True
            }
            
        except Exception as e:
            print(f"❌ [DEBUG] Get conversation history error: {e}")
            return {"error": str(e), "success": False}

    async def get_active_conversations(self, robot_id: Optional[str] = None) -> Dict[str, Any]:
        """Get list of active conversations for robots"""
        try:
            # Get recent messages from all robot conversations
            if robot_id:
                # Get messages for specific robot
                messages = get_recent_chat_messages(limit=100, user_id=f"{robot_id}_")
            else:
                # Get all robot conversation messages
                messages = get_recent_chat_messages(limit=200)
                # Filter for robot chat messages
                messages = [
                    msg for msg in messages 
                    if msg.get('metadata', {}).get('message_type', '').startswith('robot_chat')
                ]
            
            # Group by conversation_id and get latest message for each
            active_conversations = {}
            for msg in messages:
                metadata = msg.get('metadata', {})
                conv_id = metadata.get('conversation_id')
                robot_id_from_msg = metadata.get('robot_id')
                
                if conv_id and robot_id_from_msg:
                    if conv_id not in active_conversations:
                        active_conversations[conv_id] = {
                            "conversation_id": conv_id,
                            "robot_id": robot_id_from_msg,
                            "last_message": msg.get('content', ''),
                            "last_timestamp": msg.get('timestamp'),
                            "message_count": 0,
                            "location": metadata.get('context', {}).get('location', 'unknown')
                        }
                    
                    active_conversations[conv_id]["message_count"] += 1
                    
                    # Keep the most recent timestamp
                    current_ts = active_conversations[conv_id]["last_timestamp"]
                    msg_ts = msg.get('timestamp')
                    if not current_ts or (msg_ts and msg_ts > current_ts):
                        active_conversations[conv_id]["last_timestamp"] = msg_ts
                        active_conversations[conv_id]["last_message"] = msg.get('content', '')
            
            return {
                "active_conversations": list(active_conversations.values()),
                "total_conversations": len(active_conversations),
                "robot_id_filter": robot_id,
                "success": True
            }
            
        except Exception as e:
            print(f"❌ [DEBUG] Get active conversations error: {e}")
            return {"error": str(e), "success": False}