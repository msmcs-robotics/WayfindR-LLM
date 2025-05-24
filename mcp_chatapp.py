# mcp_chatapp.py - Updated with proper hybrid storage and MCP integration
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastmcp import FastMCP
import uvicorn
import re
import json
import psycopg2
from datetime import datetime, timedelta
import traceback
import sys
import httpx
import asyncio
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

from rag_store import (
    add_mcp_message, 
    init_stores, 
    retrieve_slam_telemetry,
    get_recent_chat_messages,
    add_navigation_command,
    update_command_status,
    get_navigation_commands,
    get_slam_maps,
    get_robot_telemetry_summary,
    health_check as storage_health_check,
    add_slam_telemetry
)
from llm_config import get_ollama_client, get_model_name
from qdrant_client import QdrantClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize stores on startup
logger.info("Initializing hybrid storage system...")
init_stores()
logger.info("✅ Hybrid storage system initialized")

# Database configuration
DB_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

# Qdrant configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
QDRANT_COLLECTION = "slam_telemetry"

# Initialize clients
ollama_client = get_ollama_client()
LLM_MODEL = get_model_name()
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Simulation API endpoint
SIMULATION_API_URL = "http://127.0.0.1:5001"

# Create FastAPI app and MCP server
app = FastAPI(title="SLAM Navigation MCP Chat System", version="2.0.0")
mcp = FastMCP("SLAM Navigation Agent Controller", app=app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── PYDANTIC MODELS ─────────────────────────────────────────
class ChatMessage(BaseModel):
    message: str
    robot_id: Optional[str] = None
    session_id: Optional[str] = "default"
    message_type: Optional[str] = "user_query"

class NavigationRequest(BaseModel):
    robot_id: str
    action: str
    parameters: Dict[str, Any]

class TelemetryQuery(BaseModel):
    query: str
    robot_id: Optional[str] = None
    limit: int = 10

# ─── MCP TOOL DEFINITIONS ────────────────────────────────────
@mcp.tool()
async def navigate_robot(robot_id: str, x: float, y: float, waypoint_name: str = None) -> dict:
    """Navigate a robot to specific coordinates with optional waypoint name"""
    logger.info(f"🎯 [MCP ACTION] Navigate robot '{robot_id}' to ({x}, {y}) waypoint: {waypoint_name}")
    
    # Store navigation command in PostgreSQL
    command_data = {
        "action": "navigate",
        "target_x": x,
        "target_y": y,
        "waypoint_name": waypoint_name,
        "timestamp": datetime.now().isoformat()
    }
    
    command_id = add_navigation_command(robot_id, "navigate", command_data)
    
    # Call the simulation API to navigate the robot
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{SIMULATION_API_URL}/mcp/navigate",
                params={"robot_id": robot_id, "destination": waypoint_name or f"({x}, {y})"}
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Update command status to completed
                update_command_status(command_id, "completed", result)
                
                # Store MCP action in PostgreSQL
                mcp_message = {
                    "source": "mcp",
                    "action": "navigate_robot",
                    "robot_id": robot_id,
                    "command_id": command_id,
                    "parameters": command_data,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                }
                add_mcp_message(mcp_message)
                
                return {
                    "status": "success",
                    "message": f"Robot {robot_id} navigating to {waypoint_name or f'({x}, {y})'}",
                    "command_id": command_id,
                    "robot_response": result
                }
            else:
                # Update command status to failed
                error_data = {"error": f"HTTP {response.status_code}", "response": response.text}
                update_command_status(command_id, "failed", error_data)
                
                return {
                    "status": "error",
                    "message": f"Failed to send navigation command: HTTP {response.status_code}",
                    "command_id": command_id
                }
                
        except Exception as e:
            logger.error(f"❌ Error in navigate_robot: {e}")
            update_command_status(command_id, "failed", {"error": str(e)})
            return {"status": "error", "message": f"Navigation failed: {str(e)}", "command_id": command_id}

@mcp.tool()
async def stop_robot(robot_id: str, emergency: bool = False) -> dict:
    """Stop robot navigation with optional emergency flag"""
    logger.info(f"🛑 [MCP ACTION] Stop robot '{robot_id}' (emergency: {emergency})")
    
    # Store stop command
    command_data = {
        "action": "stop",
        "emergency": emergency,
        "timestamp": datetime.now().isoformat()
    }
    
    command_id = add_navigation_command(robot_id, "stop", command_data)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{SIMULATION_API_URL}/mcp/stop",
                params={"robot_id": robot_id, "emergency": emergency}
            )
            
            if response.status_code == 200:
                result = response.json()
                update_command_status(command_id, "completed", result)
                
                # Store MCP action
                mcp_message = {
                    "source": "mcp",
                    "action": "stop_robot",
                    "robot_id": robot_id,
                    "command_id": command_id,
                    "parameters": command_data,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                }
                add_mcp_message(mcp_message)
                
                return {
                    "status": "success",
                    "message": f"Robot {robot_id} stopped {'(emergency)' if emergency else ''}",
                    "command_id": command_id,
                    "robot_response": result
                }
            else:
                error_data = {"error": f"HTTP {response.status_code}", "response": response.text}
                update_command_status(command_id, "failed", error_data)
                return {"status": "error", "message": "Failed to stop robot", "command_id": command_id}
                
        except Exception as e:
            logger.error(f"❌ Error in stop_robot: {e}")
            update_command_status(command_id, "failed", {"error": str(e)})
            return {"status": "error", "message": f"Stop command failed: {str(e)}", "command_id": command_id}

@mcp.tool()
async def get_robot_status(robot_id: str = None) -> dict:
    """Get current status of robots from the simulation system"""
    logger.info(f"📊 [MCP ACTION] Get robot status for '{robot_id or 'all robots'}'")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if robot_id:
                response = await client.get(f"{SIMULATION_API_URL}/mcp/status", params={"robot_id": robot_id})
            else:
                response = await client.get(f"{SIMULATION_API_URL}/mcp/status")
            
            if response.status_code == 200:
                result = response.json()
                
                # Store MCP action
                mcp_message = {
                    "source": "mcp",
                    "action": "get_robot_status",
                    "robot_id": robot_id,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                }
                add_mcp_message(mcp_message)
                
                return {"status": "success", "data": result}
            else:
                return {"status": "error", "message": f"Failed to get robot status: HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"❌ Error in get_robot_status: {e}")
            return {"status": "error", "message": f"Status query failed: {str(e)}"}

@mcp.tool()
async def get_system_health() -> dict:
    """Get comprehensive system health including storage and simulation"""
    logger.info("🏥 [MCP ACTION] Get system health")
    
    try:
        # Get storage health
        storage_health = storage_health_check()
        
        # Get simulation system health
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                sim_response = await client.get(f"{SIMULATION_API_URL}/mcp/system_status")
                if sim_response.status_code == 200:
                    sim_health = sim_response.json()
                else:
                    sim_health = {"status": "error", "message": "Simulation system unreachable"}
            except:
                sim_health = {"status": "error", "message": "Simulation system unreachable"}
        
        # Combine health data
        system_health = {
            "timestamp": datetime.now().isoformat(),
            "storage_system": storage_health,
            "simulation_system": sim_health,
            "overall_status": "healthy" if (
                storage_health.get("overall_status") == "healthy" and 
                sim_health.get("status") == "success"
            ) else "degraded"
        }
        
        # Store health check
        mcp_message = {
            "source": "mcp",
            "action": "get_system_health",
            "result": system_health,
            "timestamp": datetime.now().isoformat()
        }
        add_mcp_message(mcp_message)
        
        return {"status": "success", "data": system_health}
        
    except Exception as e:
        logger.error(f"❌ Error in get_system_health: {e}")
        return {"status": "error", "message": f"Health check failed: {str(e)}"}

@mcp.tool()
async def query_telemetry_data(query: str, robot_id: str = None, limit: int = 10) -> dict:
    """Query SLAM telemetry data using semantic search"""
    logger.info(f"🔍 [MCP ACTION] Query telemetry: '{query}' for robot '{robot_id or 'all'}'")
    
    try:
        # Retrieve telemetry from Qdrant using semantic search
        telemetry_results = retrieve_slam_telemetry(query, robot_id, limit)
        
        # Store MCP action
        mcp_message = {
            "source": "mcp",
            "action": "query_telemetry_data",
            "robot_id": robot_id,
            "query": query,
            "results_count": len(telemetry_results),
            "timestamp": datetime.now().isoformat()
        }
        add_mcp_message(mcp_message)
        
        return {
            "status": "success",
            "query": query,
            "robot_id": robot_id,
            "results": telemetry_results,
            "count": len(telemetry_results)
        }
        
    except Exception as e:
        logger.error(f"❌ Error in query_telemetry_data: {e}")
        return {"status": "error", "message": f"Telemetry query failed: {str(e)}"}

@mcp.tool()
async def get_robot_history(robot_id: str, limit: int = 20) -> dict:
    """Get navigation history for a specific robot"""
    logger.info(f"📜 [MCP ACTION] Get history for robot '{robot_id}'")
    
    try:
        # Get position history from simulation
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SIMULATION_API_URL}/mcp/history/{robot_id}", params={"limit": limit})
            
            if response.status_code == 200:
                history_data = response.json()
                
                # Get command history from PostgreSQL
                command_history = get_navigation_commands(robot_id, limit=limit)
                
                result = {
                    "robot_id": robot_id,
                    "position_history": history_data.get("history", []),
                    "command_history": command_history,
                    "telemetry_summary": get_robot_telemetry_summary(robot_id, hours=24)
                }
                
                # Store MCP action
                mcp_message = {
                    "source": "mcp",
                    "action": "get_robot_history",
                    "robot_id": robot_id,
                    "result_summary": {
                        "position_records": len(result["position_history"]),
                        "command_records": len(result["command_history"])
                    },
                    "timestamp": datetime.now().isoformat()
                }
                add_mcp_message(mcp_message)
                
                return {"status": "success", "data": result}
            else:
                return {"status": "error", "message": "Failed to get robot history"}
                
    except Exception as e:
        logger.error(f"❌ Error in get_robot_history: {e}")
        return {"status": "error", "message": f"History query failed: {str(e)}"}

@mcp.tool()
async def emergency_stop_all() -> dict:
    """Emergency stop all connected robots"""
    logger.info("🚨 [MCP ACTION] Emergency stop all robots")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{SIMULATION_API_URL}/mcp/emergency_stop")
            
            if response.status_code == 200:
                result = response.json()
                
                # Store emergency action
                mcp_message = {
                    "source": "mcp",
                    "action": "emergency_stop_all",
                    "result": result,
                    "timestamp": datetime.now().isoformat(),
                    "priority": "emergency"
                }
                add_mcp_message(mcp_message)
                
                return {"status": "success", "message": "Emergency stop issued to all robots", "data": result}
            else:
                return {"status": "error", "message": "Failed to issue emergency stop"}
                
    except Exception as e:
        logger.error(f"❌ Error in emergency_stop_all: {e}")
        return {"status": "error", "message": f"Emergency stop failed: {str(e)}"}

# ─── CHAT PROCESSING ─────────────────────────────────────────
async def process_chat_message(message: str, robot_id: str = None, session_id: str = "default") -> dict:
    """Process chat message with LLM and MCP integration"""
    try:
        # Store user message in PostgreSQL
        user_message = {
            "role": "user",
            "message": message,
            "robot_id": robot_id,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }
        add_mcp_message(user_message)
        
        # Get recent context from PostgreSQL
        recent_messages = get_recent_chat_messages(robot_id=robot_id, limit=10)
        
        # Build context for LLM
        context = "You are an AI assistant controlling a SLAM navigation robot system. "
        context += "You have access to MCP tools for robot control and telemetry queries. "
        context += "Use the available tools to help users navigate robots, check status, and analyze telemetry data.\n\n"
        
        # Add recent chat context
        if recent_messages:
            context += "Recent conversation context:\n"
            for msg in recent_messages[-5:]:  # Last 5 messages
                msg_data = msg.get("message_chain", {})
                if msg_data.get("role") == "user":
                    context += f"User: {msg_data.get('message', '')}\n"
                elif msg_data.get("role") == "assistant":
                    context += f"Assistant: {msg_data.get('message', '')}\n"
            context += "\n"
        
        # Add robot context if specified
        if robot_id:
            context += f"Current robot context: {robot_id}\n"
            # Get recent telemetry for this robot
            telemetry_results = retrieve_slam_telemetry(
                f"recent status for {robot_id}", robot_id=robot_id, limit=3
            )
            if telemetry_results:
                context += "Recent telemetry data:\n"
                for result in telemetry_results:
                    payload = result.get("payload", {})
                    context += f"- Position: ({payload.get('position_x', 0):.1f}, {payload.get('position_y', 0):.1f}), "
                    context += f"Status: {payload.get('status', 'unknown')}, "
                    context += f"Battery: {payload.get('battery_level', 0):.1f}%\n"
                context += "\n"
        
        # Current user message
        full_prompt = context + f"User: {message}\n\nAssistant:"
        
        # Get LLM response
        response = ollama_client.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": message}
            ]
        )
        
        assistant_response = response["message"]["content"]
        
        # Store assistant response in PostgreSQL
        assistant_message = {
            "role": "assistant",
            "message": assistant_response,
            "robot_id": robot_id,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "model_used": LLM_MODEL
        }
        add_mcp_message(assistant_message)
        
        return {
            "status": "success",
            "response": assistant_response,
            "context_used": len(recent_messages),
            "robot_id": robot_id
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing chat message: {e}")
        return {"status": "error", "message": f"Chat processing failed: {str(e)}"}

# ─── WEB INTERFACE ROUTES ────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def chat_interface(request: Request):
    """Main chat interface"""
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/chat")
async def chat_endpoint(chat_msg: ChatMessage):
    """Chat endpoint for processing messages"""
    try:
        result = await process_chat_message(
            message=chat_msg.message,
            robot_id=chat_msg.robot_id,
            session_id=chat_msg.session_id
        )
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"❌ Chat endpoint error: {e}")
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )

@app.get("/api/robots")
async def api_get_robots():
    """Get list of available robots"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{SIMULATION_API_URL}/robots")
            if response.status_code == 200:
                return response.json()
            else:
                return {"robots": [], "error": "Simulation system unavailable"}
    except Exception as e:
        return {"robots": [], "error": str(e)}

@app.get("/api/telemetry")
async def api_query_telemetry(query: TelemetryQuery):
    """Query telemetry data via REST API"""
    try:
        results = retrieve_slam_telemetry(query.query, query.robot_id, query.limit)
        return {"status": "success", "results": results, "count": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/health")
async def api_health_check():
    """API health check endpoint"""
    try:
        health_result = await get_system_health()
        return health_result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/chat/history")
async def api_chat_history(robot_id: str = None, limit: int = 50):
    """Get chat history"""
    try:
        messages = get_recent_chat_messages(robot_id=robot_id, limit=limit)
        return {"status": "success", "messages": messages, "count": len(messages)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ─── TELEMETRY INJECTION ENDPOINT ────────────────────────────
@app.post("/api/telemetry/inject")
async def inject_telemetry_data(request: Request):
    """Endpoint for injecting telemetry data directly into Qdrant (for testing/debugging)"""
    try:
        telemetry_data = await request.json()
        robot_id = telemetry_data.get("robot_id", "test_robot")
        
        # Store in Qdrant using the hybrid storage system
        telemetry_id = add_slam_telemetry(robot_id, telemetry_data)
        
        return {
            "status": "success", 
            "message": f"Telemetry stored with ID: {telemetry_id}",
            "telemetry_id": telemetry_id
        }
    except Exception as e:
        logger.error(f"❌ Error injecting telemetry: {e}")
        return {"status": "error", "message": str(e)}

# ─── STARTUP AND CONFIGURATION ───────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    logger.info("🚀 Starting SLAM Navigation MCP Chat System")
    logger.info(f"📊 Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    logger.info(f"🗄️  PostgreSQL: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    logger.info(f"🤖 LLM Model: {LLM_MODEL}")
    logger.info(f"🎮 Simulation API: {SIMULATION_API_URL}")
    
    # Test connections
    try:
        # Test storage health
        health = storage_health_check()
        if health["overall_status"] == "healthy":
            logger.info("✅ Hybrid storage system is healthy")
        else:
            logger.warning("⚠️  Storage system has issues")
            
        # Test simulation API
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{SIMULATION_API_URL}/health")
                if response.status_code == 200:
                    logger.info("✅ Simulation system is reachable")
                else:
                    logger.warning("⚠️  Simulation system returned error")
            except:
                logger.warning("⚠️  Cannot reach simulation system")
                
    except Exception as e:
        logger.error(f"❌ Startup health check failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down SLAM Navigation MCP Chat System")

def run_chat_server():
    """Run the chat server"""
    uvicorn.run(app, host="0.0.0.0", port=5002, log_level="info")

if __name__ == "__main__":
    print("🚀 Starting SLAM Navigation MCP Chat System")
    print("💬 Chat Interface: http://localhost:5002")
    print("📚 API Documentation: http://localhost:5002/docs")
    print("🔧 MCP Tools Available:")
    print("   - navigate_robot(robot_id, x, y, waypoint_name)")
    print("   - stop_robot(robot_id, emergency)")
    print("   - get_robot_status(robot_id)")
    print("   - query_telemetry_data(query, robot_id, limit)")
    print("   - get_robot_history(robot_id, limit)")
    print("   - get_system_health()")
    print("   - emergency_stop_all()")
    
    run_chat_server()