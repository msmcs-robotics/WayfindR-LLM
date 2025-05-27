import json
import httpx
import traceback
from datetime import datetime
from fastapi import Request
from rag_store import (
    add_mcp_message,
    build_comprehensive_context,
    get_stuck_robots,
    search_telemetry_context
)
from llm_config import get_ollama_client, get_model_name

class ChatHandler:
    """Handles chat interactions with RAG-enhanced context and MCP function calling"""
    
    def __init__(self, mcp_server):
        self.mcp = mcp_server
        self.ollama_client = get_ollama_client()
        self.llm_model = get_model_name()
        self.simulation_api_url = "http://127.0.0.1:5001"
        
        print(f"✅ ChatHandler initialized with LLM model: {self.llm_model}")

    # ─── MAIN CHAT FUNCTIONALITY ──────────────────────────

    async def handle_chat(self, request: Request):
        """Main chat handler with comprehensive RAG context and MCP function calling"""
        try:
            data = await request.json()
            user_message = data.get('message')
            if not user_message:
                return {"error": "No message provided"}

            print(f"[CHAT] User: {user_message}")
            
            # Store user message immediately
            self._log_user_message(user_message)
            
            # Build comprehensive context using RAG
            context = build_comprehensive_context(user_message)
            
            # Create enhanced system prompt for chat with function calling
            system_prompt = self._create_chat_system_prompt()
            
            # Format context for LLM
            context_text = self._format_context_for_llm(context)
            
            # Prepare LLM prompt with context and function calling instructions
            user_prompt = self._create_user_prompt_with_context(user_message, context_text)
            
            # Call LLM with comprehensive context
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Extract and process LLM response
            llm_response = self._extract_llm_response(response)
            
            # Check if LLM wants to call MCP functions
            function_results = await self._process_function_calls(llm_response, user_message)
            
            # Create final response combining LLM response and function results
            final_response = self._create_final_response(llm_response, function_results)
            
            # Log the interaction
            self._log_assistant_response(final_response, function_results)
            
            print(f"[CHAT] Assistant: {final_response}")
            return {
                "response": final_response,
                "function_calls": function_results,
                "context_used": len(context.get('robot_telemetry', [])) > 0
            }

        except Exception as e:
            print(f"[CHAT ERROR] {e}")
            traceback.print_exc()
            return {"error": str(e), "error_type": type(e).__name__}

    async def handle_robot_assistance_request(self, request: Request):
        """Handle requests from robots needing assistance"""
        try:
            data = await request.json()
            robot_id = data.get("robot_id")
            message = data.get("message")
            priority = data.get("priority", "medium")
            telemetry_context = data.get("telemetry", {})
            
            if not robot_id or not message:
                return {"error": "Missing robot_id or message"}

            print(f"[ROBOT ASSIST] {robot_id}: {message} (Priority: {priority})")
            
            # Log robot assistance request
            self._log_robot_message(robot_id, message, priority, telemetry_context)
            
            # Build context specifically for robot assistance
            context = build_comprehensive_context(message, robot_id)
            
            # Create robot assistance prompt
            system_prompt = self._create_robot_assistance_prompt(robot_id, priority)
            
            # Format context for robot assistance
            assistance_prompt = self._create_robot_assistance_user_prompt(
                robot_id, message, telemetry_context, context
            )
            
            # Get LLM response for assistance
            response = self.ollama_client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": assistance_prompt}
                ]
            )
            
            llm_response = self._extract_llm_response(response)
            
            # Process any function calls for robot assistance
            function_results = await self._process_function_calls(llm_response, message, robot_id)
            
            # Log assistance response
            self._log_assistance_response(robot_id, llm_response, function_results)
            
            return {
                "status": "processed",
                "robot_id": robot_id,
                "assistance_response": llm_response,
                "function_calls": function_results,
                "priority": priority,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"[ROBOT ASSIST ERROR] {e}")
            traceback.print_exc()
            return {"error": str(e)}

    # ─── MCP FUNCTION IMPLEMENTATIONS ─────────────────────

    async def navigate_to_waypoint(self, waypoint_name: str, robot_id: str = None) -> dict:
        """Navigate robot to a single waypoint"""
        try:
            print(f"[NAV] Navigating {robot_id or 'robot'} to waypoint: {waypoint_name}")
            
            payload = {"waypoint": waypoint_name}
            if robot_id:
                payload["robot_id"] = robot_id
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.simulation_api_url}/navigate",
                    json=payload
                )
                
                success = response.status_code == 200
                result_data = response.json() if success else {"error": response.text}
                
                # Log navigation action
                add_mcp_message({
                    "role": "system",
                    "timestamp": datetime.now().isoformat(),
                    "agent_id": robot_id or "navigation_system",
                    "source": "navigation_function",
                    "action": "navigate",
                    "waypoint": waypoint_name,
                    "success": success,
                    "result": result_data
                })
                
                return {
                    "success": success,
                    "message": f"{'Successfully navigating' if success else 'Failed to navigate'} {robot_id or 'robot'} to {waypoint_name}",
                    "waypoint": waypoint_name,
                    "robot_id": robot_id,
                    "details": result_data
                }
                    
        except Exception as e:
            print(f"[NAV ERROR] {e}")
            error_result = {
                "success": False,
                "message": f"Navigation error: {str(e)}",
                "waypoint": waypoint_name,
                "robot_id": robot_id
            }
            
            # Log error
            add_mcp_message({
                "role": "system",
                "timestamp": datetime.now().isoformat(),
                "source": "navigation_error",
                "error": str(e),
                "waypoint": waypoint_name,
                "robot_id": robot_id
            })
            
            return error_result

    async def navigate_multiple_waypoints(self, waypoints: list, robot_id: str = None) -> dict:
        """Navigate through multiple waypoints in sequence"""
        try:
            print(f"[NAV MULTI] Navigating {robot_id or 'robot'} through waypoints: {waypoints}")
            
            payload = {"waypoints": waypoints}
            if robot_id:
                payload["robot_id"] = robot_id
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.simulation_api_url}/nav_points",
                    json=payload
                )
                
                success = response.status_code == 200
                result_data = response.json() if success else {"error": response.text}
                
                # Log multi-waypoint navigation
                add_mcp_message({
                    "role": "system",
                    "timestamp": datetime.now().isoformat(),
                    "agent_id": robot_id or "navigation_system",
                    "source": "navigation_function",
                    "action": "nav_points",
                    "waypoints": waypoints,
                    "success": success,
                    "result": result_data
                })
                
                return {
                    "success": success,
                    "message": f"{'Successfully navigating' if success else 'Failed to navigate'} {robot_id or 'robot'} through {len(waypoints)} waypoints",
                    "waypoints": waypoints,
                    "robot_id": robot_id,
                    "details": result_data
                }
                    
        except Exception as e:
            print(f"[NAV MULTI ERROR] {e}")
            return {
                "success": False,
                "message": f"Multi-waypoint navigation error: {str(e)}",
                "waypoints": waypoints,
                "robot_id": robot_id
            }

    async def emergency_stop(self, robot_id: str = None) -> dict:
        """Emergency stop for specified robot or all robots"""
        try:
            print(f"[EMERGENCY] Emergency stop for: {robot_id or 'ALL ROBOTS'}")
            
            payload = {"robot_id": robot_id} if robot_id else {"all_robots": True}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.simulation_api_url}/emergency_stop",
                    json=payload
                )
                
                success = response.status_code == 200
                result_data = response.json() if success else {"error": response.text}
                
                # Log emergency stop
                add_mcp_message({
                    "role": "system",
                    "timestamp": datetime.now().isoformat(),
                    "agent_id": robot_id or "emergency_system",
                    "source": "emergency_function",
                    "action": "emergency_stop",
                    "success": success,
                    "result": result_data
                })
                
                return {
                    "success": success,
                    "message": f"Emergency stop {'executed' if success else 'failed'} for {robot_id or 'all robots'}",
                    "robot_id": robot_id,
                    "details": result_data
                }
                    
        except Exception as e:
            print(f"[EMERGENCY ERROR] {e}")
            return {
                "success": False,
                "message": f"Emergency stop error: {str(e)}",
                "robot_id": robot_id
            }

    # ─── PROMPT CREATION METHODS ──────────────────────────

    def _create_chat_system_prompt(self):
        """Create system prompt for general chat with MCP function calling"""
        return """You are an AI assistant for a robot guidance system. You help users interact with robots and navigate through a building.

AVAILABLE MCP FUNCTIONS:
- navigate(waypoint_name, robot_id=None): Navigate a robot to a specific waypoint
- nav_points([waypoint1, waypoint2, waypoint3], robot_id=None): Navigate through multiple waypoints in sequence  
- emergency_stop(robot_id=None): Emergency stop for specific robot or all robots

FUNCTION CALLING FORMAT:
When you need to call a function, include it in your response using this exact format:
FUNCTION_CALL: function_name(parameter1="value1", parameter2="value2")

CONTEXT AVAILABLE:
- Real-time robot telemetry and positions
- Navigation history and recent robot activity
- Information about stuck robots needing assistance
- Previous user conversations and requests

GUIDELINES:
1. Always explain what you're doing when calling functions
2. If robots are stuck, prioritize helping them with navigation functions
3. For navigation requests, determine the appropriate waypoints and call the function
4. For emergencies or safety concerns, use emergency_stop immediately
5. Keep responses helpful and conversational
6. If unsure about waypoint names, ask for clarification

Remember: You can call functions to actually navigate robots, not just suggest actions."""

    def _create_robot_assistance_prompt(self, robot_id, priority):
        """Create system prompt for robot assistance"""
        return f"""You are an AI assistant helping Robot {robot_id} that has requested assistance (Priority: {priority}).

AVAILABLE MCP FUNCTIONS:
- navigate(waypoint_name, robot_id): Navigate this robot to a specific waypoint
- nav_points([waypoint1, waypoint2], robot_id): Navigate through multiple waypoints
- emergency_stop(robot_id): Emergency stop this robot if unsafe

FUNCTION CALLING FORMAT:
FUNCTION_CALL: function_name(parameter1="value1", parameter2="value2")

ROBOT ASSISTANCE PRIORITIES:
- HIGH: Safety issues, robot completely stuck, blocking other robots
- MEDIUM: Navigation problems, minor obstacles, route optimization
- LOW: Status requests, minor adjustments

ANALYSIS APPROACH:
1. Assess the robot's situation from telemetry and message
2. Determine if immediate action is needed
3. Choose appropriate function calls to resolve the issue
4. Explain your reasoning clearly

Focus on practical solutions using the available functions."""

    def _create_user_prompt_with_context(self, user_message, context_text):
        """Create user prompt with RAG context"""
        return f"""ROBOT SYSTEM CONTEXT:
{context_text}

USER REQUEST: {user_message}

Analyze the user's request considering the current robot context. If they want navigation or robot control, use the appropriate MCP functions. Provide helpful information about robot status when relevant."""

    def _create_robot_assistance_user_prompt(self, robot_id, message, telemetry_context, rag_context):
        """Create prompt for robot assistance with full context"""
        context_parts = [
            f"ROBOT {robot_id} REQUEST: {message}",
            "",
            "CURRENT TELEMETRY:",
            json.dumps(telemetry_context, indent=2),
            "",
            "SYSTEM CONTEXT:"
        ]
        
        # Add stuck robots info
        if rag_context.get('stuck_robots'):
            context_parts.append(f"- {len(rag_context['stuck_robots'])} robots currently stuck")
        
        # Add recent activity
        if rag_context.get('recent_activity'):
            context_parts.append("- Recent robot activity available")
        
        # Add relevant telemetry
        if rag_context.get('robot_telemetry'):
            context_parts.append(f"- {len(rag_context['robot_telemetry'])} relevant telemetry entries found")
        
        return "\n".join(context_parts)

    # ─── RESPONSE PROCESSING METHODS ──────────────────────

    async def _process_function_calls(self, llm_response, original_message, robot_id=None):
        """Process function calls from LLM response"""
        function_results = []
        
        if "FUNCTION_CALL:" not in llm_response:
            return function_results
        
        # Extract function calls (simple parsing - could be made more robust)
        lines = llm_response.split('\n')
        for line in lines:
            if line.strip().startswith("FUNCTION_CALL:"):
                function_call = line.replace("FUNCTION_CALL:", "").strip()
                
                try:
                    result = await self._execute_function_call(function_call, robot_id)
                    function_results.append({
                        "function_call": function_call,
                        "result": result,
                        "success": result.get("success", False)
                    })
                except Exception as e:
                    print(f"[FUNCTION ERROR] {e}")
                    function_results.append({
                        "function_call": function_call,
                        "error": str(e),
                        "success": False
                    })
        
        return function_results

    async def _execute_function_call(self, function_call, default_robot_id=None):
        """Execute a single function call"""
        # Basic function call parsing (could be improved with proper AST parsing)
        if function_call.startswith("navigate("):
            # Extract parameters
            params = self._parse_function_params(function_call)
            waypoint = params.get("waypoint_name")
            robot_id = params.get("robot_id", default_robot_id)
            return await self.navigate_to_waypoint(waypoint, robot_id)
        
        elif function_call.startswith("nav_points("):
            params = self._parse_function_params(function_call)
            waypoints = params.get("waypoints", [])
            robot_id = params.get("robot_id", default_robot_id)
            return await self.navigate_multiple_waypoints(waypoints, robot_id)
        
        elif function_call.startswith("emergency_stop("):
            params = self._parse_function_params(function_call)
            robot_id = params.get("robot_id", default_robot_id)
            return await self.emergency_stop(robot_id)
        
        else:
            return {"success": False, "error": f"Unknown function: {function_call}"}

    def _parse_function_params(self, function_call):
        """Basic parameter parsing for function calls"""
        # This is a simplified parser - in production you'd want something more robust
        params = {}
        try:
            # Extract content between parentheses
            start = function_call.find('(') + 1
            end = function_call.rfind(')')
            param_str = function_call[start:end]
            
            # Split by commas and parse key=value pairs
            if param_str.strip():
                for param in param_str.split(','):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        
                        # Handle list parameters
                        if value.startswith('[') and value.endswith(']'):
                            # Simple list parsing
                            list_content = value[1:-1]
                            params[key] = [item.strip().strip('"\'') for item in list_content.split(',') if item.strip()]
                        else:
                            params[key] = value
        except Exception as e:
            print(f"[PARAM PARSE ERROR] {e}")
        
        return params

    def _create_final_response(self, llm_response, function_results):
        """Create final response combining LLM response and function results"""
        # Remove function call lines from LLM response for cleaner output
        response_lines = []
        for line in llm_response.split('\n'):
            if not line.strip().startswith("FUNCTION_CALL:"):
                response_lines.append(line)
        
        clean_response = '\n'.join(response_lines).strip()
        
        # Add function execution results if any
        if function_results:
            clean_response += "\n\n🤖 Actions taken:"
            for result in function_results:
                if result.get("success"):
                    clean_response += f"\n✅ {result['result'].get('message', 'Action completed')}"
                else:
                    clean_response += f"\n❌ {result.get('error', 'Action failed')}"
        
        return clean_response

    # ─── HELPER METHODS ────────────────────────────────────

    def _format_context_for_llm(self, context):
        """Format comprehensive context for LLM"""
        formatted_parts = []
        
        # Stuck robots (high priority)
        if context.get('stuck_robots'):
            formatted_parts.append(f"⚠️ STUCK ROBOTS ({len(context['stuck_robots'])} robots need assistance):")
            for robot in context['stuck_robots']:
                pos = robot.get('position', {})
                formatted_parts.append(f"  - {robot['robot_id']}: stuck at ({pos.get('x', 0):.1f}, {pos.get('y', 0):.1f}), trying to reach {robot.get('target_waypoint', 'unknown')}")
        
        # Recent robot activity
        if context.get('recent_activity'):
            formatted_parts.append(f"\n📍 RECENT ROBOT ACTIVITY:")
            for activity in context['recent_activity'][:3]:  # Show 3 most recent
                pos = activity.get('position', {})
                status = "🔴 STUCK" if activity.get('stuck') else "🟢 ACTIVE"
                formatted_parts.append(f"  - {activity['robot_id']}: {status} at ({pos.get('x', 0):.1f}, {pos.get('y', 0):.1f})")
        
        # Relevant telemetry context
        if context.get('robot_telemetry'):
            formatted_parts.append(f"\n🔍 RELEVANT TELEMETRY FOUND: {len(context['robot_telemetry'])} entries")
        
        return "\n".join(formatted_parts) if formatted_parts else "No specific robot context available."

    def _extract_llm_response(self, response):
        """Safely extract LLM response content"""
        try:
            if 'message' in response and response['message'] and 'content' in response['message']:
                content = response['message']['content']
                if content and content.strip():
                    return content.strip()
        except Exception as e:
            print(f"[LLM RESPONSE ERROR] {e}")
        
        return "I'm unable to provide a response at this time."

    # ─── LOGGING METHODS ───────────────────────────────────

    def _log_user_message(self, message):
        """Log user message to RAG system"""
        add_mcp_message({
            "role": "user",
            "timestamp": datetime.now().isoformat(),
            "agent_id": "user",
            "source": "chat",
            "message": message
        })

    def _log_assistant_response(self, response, function_results):
        """Log assistant response to RAG system"""
        add_mcp_message({
            "role": "assistant",
            "timestamp": datetime.now().isoformat(),
            "agent_id": "llm",
            "source": "chat_response",
            "message": response,
            "function_calls": function_results
        })

    def _log_robot_message(self, robot_id, message, priority, telemetry_context):
        """Log robot assistance request"""
        add_mcp_message({
            "role": "robot",
            "timestamp": datetime.now().isoformat(),
            "agent_id": robot_id,
            "source": "robot_assistance_request",
            "message": message,
            "priority": priority,
            "telemetry": telemetry_context
        })

    def _log_assistance_response(self, robot_id, response, function_results):
        """Log assistance response"""
        add_mcp_message({
            "role": "assistant",
            "timestamp": datetime.now().isoformat(),
            "agent_id": "llm",
            "source": "robot_assistance_response",
            "robot_id": robot_id,
            "message": response,
            "function_calls": function_results
        })