from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastmcp import FastMCP
import uvicorn
import re
import json
import psycopg2
from datetime import datetime
import traceback
import sys
import httpx
from rag_store import add_mcp_message, init_stores, retrieve_telemetry
from llm_config import get_ollama_client, get_model_name
from qdrant_client import QdrantClient

# Initialize stores on startup
init_stores()

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
QDRANT_COLLECTION = "telemetry_data"

ollama_client = get_ollama_client()
LLM_MODEL = get_model_name()

# Simulation API endpoint
SIMULATION_API_URL = "http://127.0.0.1:5001"

# Create an MCP server
app = FastAPI()
mcp = FastMCP("Agent Movement and Simulation", app=app)

# Add CORS middleware to allow requests from all origins
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

# Database functions from chatapp - Updated to work with new schema
def fetch_logs_from_db(limit=None):
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                # Query the mcp_message_chains table instead of logs
                query = "SELECT id, message_chain, created_at FROM mcp_message_chains"
                if limit:
                    query += f" ORDER BY created_at DESC LIMIT {limit}"
                else:
                    query += " ORDER BY created_at DESC"
                cur.execute(query)
                rows = cur.fetchall()
                
                logs = []
                for row in rows:
                    log_id, message_data, created_at = row
                    
                    # Extract text from message_chain based on its structure
                    if isinstance(message_data, dict):
                        # If message_data is a dictionary
                        content = message_data.get("message", message_data.get("command", ""))
                    else:
                        # If it's something else, convert to string
                        content = str(message_data)
                    
                    logs.append({
                        "log_id": str(log_id),
                        "text": content,
                        "metadata": message_data,
                        "created_at": created_at.isoformat()
                    })
                return logs
    except Exception as e:
        print(f"Error fetching logs from DB: {e}")
        traceback.print_exc()
        return []

# New endpoints for frontend log viewing
@app.get("/qdrant_logs")
async def get_qdrant_logs():
    """API endpoint to fetch Qdrant logs"""
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        records = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=100,
            with_payload=True,
            with_vectors=False
        )[0]
        
        # Convert Qdrant records to JSON-serializable format
        serializable_records = []
        for record in records:
            serializable_records.append({
                "id": record.id,
                "payload": record.payload
            })
        
        return {"records": serializable_records}
    except Exception as e:
        print(f"Error fetching Qdrant logs: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/postgres_logs")
async def get_postgres_logs():
    """API endpoint to fetch PostgreSQL logs"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        relationships = []
        message_chains = []
        
        try:
            with conn.cursor() as cur:
                # Agent Relationships
                cur.execute("SELECT * FROM agent_relationships ORDER BY created_at DESC LIMIT 50;")
                relationships = [list(row) for row in cur.fetchall()]  # Convert tuples to lists for JSON serialization
                
                # Convert any JSON/JSONB fields to Python dicts
                for i, row in enumerate(relationships):
                    # Assuming index 2 is the JSONB field
                    if isinstance(row[2], psycopg2.extras.Json):
                        relationships[i][2] = dict(row[2])
                
                # MCP Message Chains
                cur.execute("SELECT * FROM mcp_message_chains ORDER BY created_at DESC LIMIT 50;")
                message_chains = [list(row) for row in cur.fetchall()]
                
                # Convert any JSON/JSONB fields to Python dicts
                for i, row in enumerate(message_chains):
                    # Assuming index 1 is the JSONB field
                    if isinstance(row[1], psycopg2.extras.Json):
                        message_chains[i][1] = dict(row[1])
        finally:
            conn.close()
        
        return {
            "relationships": relationships,
            "message_chains": message_chains
        }
    except Exception as e:
        print(f"Error fetching PostgreSQL logs: {e}")
        traceback.print_exc()
        return {"error": str(e)}

# Define the command to handle agent movement - Updated to use API calls
@mcp.tool()
async def move_agent(agent: str, x: float, y: float) -> dict:
    """Move an agent to specific coordinates"""
    print(f"[ACTION] Move agent '{agent}' to ({x}, {y})")
    
    # Call the simulation API to move the agent
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{SIMULATION_API_URL}/move_agent",
                json={"agent": agent, "x": x, "y": y}
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Log the movement action using the new RAG function
                timestamp = datetime.now().isoformat()
                
                # Create a structured message object for the new RAG system
                add_mcp_message({
                    "agent_id": agent,
                    "position": f"({x}, {y})",
                    "timestamp": timestamp,
                    "source": "mcp",
                    "action": "move",
                    "jammed": result.get("jammed", False)
                })
                
                # Format the response message
                if result.get("jammed", False):
                    message = (f"Agent {agent} is currently jammed (Comm quality: {result.get('communication_quality', 0.2)}). "
                             f"It will first return to its last safe position at {result.get('current_position')} "
                             f"before proceeding to ({x}, {y}).")
                else:
                    message = f"Moving {agent} to coordinates ({x}, {y})."
                
                return {
                    "success": True,
                    "message": message,
                    "x": x,
                    "y": y,
                    "jammed": result.get("jammed", False),
                    "communication_quality": result.get("communication_quality", 1.0),
                    "current_position": result.get("current_position")
                }
            else:
                error_msg = f"Error moving agent: {response.text}"
                print(f"[API ERROR] {error_msg}")
                return {
                    "success": False,
                    "message": error_msg
                }
        except Exception as e:
            error_msg = f"Exception occurred while moving agent: {str(e)}"
            print(f"[EXCEPTION] {error_msg}")
            return {
                "success": False,
                "message": error_msg
            }

# Direct API endpoint for simulation to call
@app.post("/move_agent_via_ollama")
async def move_agent_endpoint(request: Request):
    data = await request.json()
    agent = data.get("agent")
    x = float(data.get("x"))
    y = float(data.get("y"))
    
    result = await move_agent(agent, x, y)
    return result

# Process natural language commands - Updated to verify agents exist first
@app.post("/llm_command")
async def llm_command(request: Request):
    data = await request.json()
    command = data.get("message", "")

    print(f"[RECEIVED COMMAND] {command}")
    
    # Log the user command using the new RAG function
    timestamp = datetime.now().isoformat()
    add_mcp_message({
        "role": "user",
        "timestamp": timestamp,
        "agent_id": "user",
        "source": "command",
        "command": command
    })

    # First get the available agents from the simulation
    available_agents = {}
    live_agent_data = {}  # Store live data for LLM context
    try:
        async with httpx.AsyncClient() as client:
            # Get both agent list and their current status
            agents_response = await client.get(f"{SIMULATION_API_URL}/agents")
            status_response = await client.get(f"{SIMULATION_API_URL}/status")
            
            if agents_response.status_code == 200:
                available_agents = agents_response.json().get("agents", {})
                print(f"[AVAILABLE AGENTS] {list(available_agents.keys())}")
            
            if status_response.status_code == 200:
                live_agent_data = status_response.json()
                print(f"[LIVE AGENT DATA] Retrieved for {len(live_agent_data.get('agent_positions', {}))} agents")
    except Exception as e:
        print(f"[ERROR] Failed to fetch agent data: {e}")
        available_agents = {}
        live_agent_data = {}

    # Format prompt for the LLM with both historical and live data
    prompt = f"""You are an AI that controls agents in a 2D simulation.

Available agents: {", ".join(available_agents.keys()) if available_agents else "No agents available"}

User command: "{command}"

LIVE AGENT STATUS:
{format_live_agent_data(live_agent_data)}

If this is a movement command, extract:
1. The agent name (must match an available agent)
2. The x coordinate (number)
3. The y coordinate (number)

Respond ONLY with the agent name and coordinates in this exact format:
agent_name,x,y

If it's not a movement command, respond with: "Not a movement command"
"""

    try:
        # Get LLM response
        response = ollama_client.chat(model=LLM_MODEL, messages=[
            {"role": "user", "content": prompt}
        ])
        
        raw_response = response['message']['content'].strip()
        print(f"[OLLAMA RESPONSE] {raw_response}")

        # Log the assistant's raw response immediately
        timestamp = datetime.now().isoformat()
        add_mcp_message({
            "role": "assistant",
            "timestamp": timestamp,
            "agent_id": "ollama",
            "source": "response",
            "response": raw_response  # even if empty
        })

        # Check if response matches our expected movement command format
        if "," in raw_response and len(raw_response.split(",")) == 3:
            agent_name, x_str, y_str = raw_response.split(",")
            agent_name = agent_name.strip()
            
            # Validate agent exists
            if agent_name not in available_agents:
                return {"response": f"Error: Agent '{agent_name}' not found in simulation"}
            
            try:
                x = float(x_str.strip())
                y = float(y_str.strip())
                
                # Actually execute the movement
                move_result = await move_agent(agent_name, x, y)
                
                if move_result.get("success"):
                    # Include live data in response
                    response_data = {
                        "response": f"Moving {agent_name} to ({x}, {y}). {move_result.get('message', '')}",
                        "live_data": {
                            agent_name: live_agent_data.get('agent_positions', {}).get(agent_name)
                        }
                    }
                    return response_data
                else:
                    return {"response": f"Failed to move {agent_name}: {move_result.get('message', 'Unknown error')}"}
            
            except ValueError:
                return {"response": f"Invalid coordinates: {x_str}, {y_str}"}
        
        # Not a movement command or invalid format
        return {"response": raw_response if raw_response else "Command not understood"}

    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()
        
        # Log the error using the new RAG function
        add_mcp_message({
            "role": "system",
            "timestamp": datetime.now().isoformat(),
            "source": "command",
            "error": str(e)
        })

        return {
            "response": f"Error processing command: {e}"
        }

def format_live_agent_data(live_data):
    """Format live agent data for LLM prompt"""
    if not live_data or not live_data.get('agent_positions'):
        return "No live agent data available"
    
    formatted = []
    for agent_id, data in live_data['agent_positions'].items():
        status = "JAMMED" if data.get('jammed', False) else "CLEAR"
        comm_quality = data.get('communication_quality', 0)
        pos = data.get('position', {})
        formatted.append(
            f"{agent_id}: Position ({pos.get('x', '?')}, {pos.get('y', '?')}) - {status} - Comm: {comm_quality:.2f}"
        )
    
    return "\n".join(formatted)

# Chat endpoint from Flask app now in FastAPI - Updated to incorporate simulation status and new RAG
@app.post("/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        user_message = data.get('message')
        if not user_message:
            return {"error": "No message provided"}
        
        # Get ALL logs for RAG context without limit
        logs = fetch_logs_from_db()
        print(f"Retrieved {len(logs)} logs for RAG context")
        
        # Get current simulation status
        sim_status = {}
        try:
            async with httpx.AsyncClient() as client:
                status_response = await client.get(f"{SIMULATION_API_URL}/status")
                if status_response.status_code == 200:
                    sim_status = status_response.json()
        except Exception as e:
            print(f"Error fetching simulation status: {e}")
            sim_status = {"error": str(e)}
        
        # Sort logs by timestamp for consistency
        logs_sorted = sorted(
            logs,
            key=lambda x: x.get("metadata", {}).get("timestamp", x.get("created_at", "")),
            reverse=True  # Most recent first
        )
        
        # Format context in a structured way
        simulation_context = []
        for log in logs_sorted:
            metadata = log.get("metadata", {})
            
            # Handle both old and new metadata formats
            if isinstance(metadata, dict):
                agent_id = metadata.get("agent_id", "Unknown")
                position = metadata.get("position", "Unknown")
                jammed = "JAMMED" if metadata.get("jammed", False) else "CLEAR"
                timestamp = metadata.get("timestamp", "Unknown time")
                
                # Extract message or command based on source
                if metadata.get("source") == "command":
                    text = metadata.get("command", "")
                elif metadata.get("source") == "chat":
                    text = metadata.get("message", "")
                else:
                    text = log.get("text", "")
                
                # Create rich context entries
                entry = f"LOG: Agent {agent_id} at position {position} is {jammed} at {timestamp}: {text}"
                simulation_context.append(entry)
        
        # Add current simulation status
        if sim_status:
            simulation_context.append("\nCURRENT SIMULATION STATUS:")
            simulation_context.append(f"Running: {sim_status.get('running', 'Unknown')}")
            simulation_context.append(f"Iteration Count: {sim_status.get('iteration_count', 'Unknown')}")
            
            # Add current agent positions
            agent_positions = sim_status.get('agent_positions', {})
            if agent_positions:
                simulation_context.append("Current Agent Positions:")
                for agent_id, data in agent_positions.items():
                    jammed_status = "JAMMED" if data.get("jammed", False) else "CLEAR"
                    comm_quality = data.get("communication_quality", 0)
                    position = data.get("position", {})
                    x = position.get("x", 0) if isinstance(position, dict) else 0
                    y = position.get("y", 0) if isinstance(position, dict) else 0
                    simulation_context.append(f"  {agent_id}: Position ({x}, {y}) - {jammed_status} - Comm Quality: {comm_quality:.2f}")
        
        # Format full context
        context_text = "\n".join(simulation_context)
        
        # Check for duplicate commands (issued within last 10 seconds)
        for log in logs_sorted[:5]:  # Check most recent 5 logs
            metadata = log.get("metadata", {})
            if metadata.get("role") == "user" and metadata.get("source") == "command":
                recent_time = metadata.get("timestamp")
                # Get the command from the new metadata structure
                recent_text = metadata.get("command", "")
                if recent_time and (datetime.now() - datetime.fromisoformat(recent_time)).total_seconds() < 10:
                    if recent_text.lower() == user_message.lower():
                        print(f"Detected duplicate command processing: '{user_message}'")
                        return {"response": ""}  # Empty response for duplicates
        
        # Create a clear system prompt for the LLM
        system_prompt = """You are an assistant for a Multi-Agent Simulation system. Provide helpful, accurate information about the simulation based on the logs and current status.

Keep your responses concise and focused on answering the user's questions.
- If the user is asking about agent positions or statuses, give them the current information
- Don't recite all the log history unless specifically asked
- For questions about recent commands, just give a brief status update
"""
        
        # Call the LLM with all information
        response = ollama_client.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"SIMULATION LOGS AND STATUS:\n{context_text}\n\nUSER QUERY: {user_message}\n\nAnswer based only on information provided above."}
            ]
        )
        
        # Debug response
        print("\n===== LLM RESPONSE =====")
        print(f"Model: {LLM_MODEL}")
        print("Content:", end=" ")
        if 'message' in response and response['message']:
            print(response['message']['content'])
        else:
            print("NO CONTENT")
        print("========================\n")
        
        # Extract response safely
        ollama_response = ""
        if 'message' in response and response['message']:
            if 'content' in response['message'] and response['message']['content']:
                ollama_response = response['message']['content']
        
        # Ensure we got some response
        if not ollama_response.strip():
            ollama_response = "I'm unable to provide an answer based on the available logs and simulation status."
        
        # Log interaction with the new RAG system
        timestamp = datetime.now().isoformat()
        
        # Log user message
        add_mcp_message({
            "role": "user",
            "timestamp": timestamp,
            "agent_id": "user",
            "source": "chat",
            "message": user_message
        })

        # Log assistant response
        add_mcp_message({
            "role": "assistant",
            "timestamp": timestamp,
            "agent_id": "ollama",
            "source": "chat",
            "message": ollama_response
        })
        
        return {"response": ollama_response}
    except Exception as e:
        print(f"ERROR in chat route: {e}")
        traceback.print_exc()
        return {"error": str(e), "error_type": type(e).__name__}

# Added new endpoint to get simulation parameters
@app.get("/simulation_info")
async def get_simulation_info():
    """Get information about the simulation configuration"""
    try:
        async with httpx.AsyncClient() as client:
            params_response = await client.get(f"{SIMULATION_API_URL}/simulation_params")
            agents_response = await client.get(f"{SIMULATION_API_URL}/agents")
            
            if params_response.status_code == 200 and agents_response.status_code == 200:
                params = params_response.json()
                agents = agents_response.json()
                
                return {
                    "simulation_params": params,
                    "agents": agents.get("agents", {})
                }
            else:
                return {
                    "error": "Failed to fetch simulation information",
                    "params_status": params_response.status_code,
                    "agents_status": agents_response.status_code
                }
    except Exception as e:
        print(f"Error fetching simulation info: {e}")
        return {"error": str(e)}

# Added control endpoints to start/pause/continue simulation
@app.post("/control/pause")
async def pause_simulation():
    """Pause the simulation via API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{SIMULATION_API_URL}/control/pause")
            return response.json()
    except Exception as e:
        return {"error": str(e)}

@app.post("/control/continue")
async def continue_simulation():
    """Continue the simulation via API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{SIMULATION_API_URL}/control/continue")
            return response.json()
    except Exception as e:
        return {"error": str(e)}

# LOG endpoints - Updated to work with the new schema
@app.get("/logs")
async def get_logs():
    try:
        logs = fetch_logs_from_db(limit=100)
        
        # Format logs for frontend compatibility
        formatted_logs = []
        for log in logs:
            metadata = log.get("metadata", {})
            
            # Handle both message and command based on source
            text = ""
            if isinstance(metadata, dict):
                if metadata.get("source") == "command":
                    text = metadata.get("command", "")
                elif metadata.get("source") == "chat":
                    text = metadata.get("message", "")
                elif "action" in metadata:
                    text = f"Action: {metadata.get('action')} for {metadata.get('agent_id')}"
                else:
                    # Fallback if there's no specific text field
                    text = log.get("text", "")
            
            formatted_logs.append({
                "log_id": log.get("log_id"),
                "text": text,
                "metadata": metadata,
                "created_at": log.get("created_at")
            })
        
        return {
            "logs": formatted_logs,
            "has_more": False  # You could paginate in future
        }
    except Exception as e:
        print(f"Error in /logs route: {e}")
        traceback.print_exc()
        return {"error": f"Internal server error: {str(e)}"}

@app.get("/log_count")
async def log_count():
    """
    Return the current number of logs in the system.
    """
    try:
        logs = fetch_logs_from_db()
        return {"log_count": len(logs)}
    except Exception as e:
        print("Error in /log_count route:", e)
        return {"error": "Internal server error"}

# Root endpoint to serve the HTML with Jinja2
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        error_msg = f"ERROR: Could not render template 'index.html': {e}"
        print(error_msg)
        return HTMLResponse(content=f"<html><body>{error_msg}</body></html>", status_code=500)

@app.get("/test")
async def test():
    return {"message": "FastAPI server is running correctly!"}

# Health check endpoint that also verifies simulation API connectivity
@app.get("/health")
async def health_check():
    """Check if the server and simulation API are reachable"""
    try:
        # Check if simulation API is reachable
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SIMULATION_API_URL}/")
            simulation_status = "online" if response.status_code == 200 else "offline"
    except Exception as e:
        simulation_status = f"unreachable: {str(e)}"
    
    return {
        "mcp_server": "online",
        "simulation_api": simulation_status,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    print("Starting integrated MCP server with chat app...")
    print(f"Python version: {sys.version}")
    print("Visit http://127.0.0.1:5000")
    uvicorn.run(app, host="127.0.0.1", port=5000)