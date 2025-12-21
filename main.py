#!/usr/bin/env python3
"""
WayfindR-LLM Main Application
FastAPI server for tour guide robot system
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn
import sys
from datetime import datetime

# Import configuration
from core.config import SERVER_HOST, SERVER_PORT, SYSTEM_NAME

# Import handlers
from api.chat_handler import handle_web_chat, handle_robot_chat
from api.telemetry_handler import receive_telemetry, get_robot_status, get_robot_history
from api.streaming import (
    stream_postgresql,
    stream_qdrant,
    get_postgresql_data,
    get_qdrant_data
)

# Initialize LLM
print("[MCP] Initializing LLM...")
try:
    from llm_config import initialize_llm, get_model_name
    import llm_config

    ollama_client, llm_ready = initialize_llm(preload=False)
    LLM_MODEL = get_model_name()

    if llm_ready:
        print(f"[MCP] LLM configured: {LLM_MODEL} (will load on first use)")
    else:
        print(f"[MCP] LLM not available, will retry on first request")
except ImportError as e:
    print(f"[MCP] LLM not available: {e}")
    llm_ready = False

# Initialize RAG stores
print("[RAG] Initializing storage...")
try:
    from rag import postgresql_store, qdrant_store
    print("[RAG] PostgreSQL and Qdrant stores initialized")
except Exception as e:
    print(f"[RAG] Storage initialization warning: {e}")

# Create FastAPI app
app = FastAPI(title=SYSTEM_NAME)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# =============================================================================
# MAIN ROUTES
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve main dashboard"""
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        error_msg = f"ERROR: Could not render template: {e}"
        print(error_msg)
        return HTMLResponse(content=f"<html><body>{error_msg}</body></html>", status_code=500)


@app.get("/health")
async def health_check():
    """Check system health"""
    health = {
        "mcp_server": "online",
        "llm": "ready" if llm_ready else "unavailable",
        "timestamp": datetime.now().isoformat()
    }

    # Check Qdrant
    try:
        from rag.qdrant_store import qdrant_client, get_all_robots
        if qdrant_client:
            health["qdrant"] = "available"
            robots = get_all_robots(limit=10)
            health["active_robots"] = len(robots)
        else:
            health["qdrant"] = "unavailable"
            health["active_robots"] = 0
    except Exception as e:
        health["qdrant"] = f"error: {e}"
        health["active_robots"] = 0

    # Check PostgreSQL
    try:
        from rag.postgresql_store import get_conversation_history
        get_conversation_history(limit=1)
        health["postgresql"] = "available"
    except Exception as e:
        health["postgresql"] = f"error: {e}"

    return health


# =============================================================================
# CHAT ENDPOINTS
# =============================================================================

@app.post("/chat")
async def chat(request: Request):
    """Web dashboard chat endpoint"""
    try:
        data = await request.json()
        user_message = data.get('message', '').strip()
        user_id = data.get('user_id', 'anonymous')

        print(f"\n[CHAT] Web message: {user_message[:50]}...")

        result = await handle_web_chat(user_message, user_id)

        return result

    except Exception as e:
        error = f"Error processing chat: {str(e)}"
        print(f"[CHAT ERROR] {error}")
        import traceback
        traceback.print_exc()
        return {"success": False, "response": f"Error: {error}"}


@app.post("/robot_chat")
async def robot_chat(request: Request):
    """Android app chat endpoint"""
    try:
        data = await request.json()
        user_message = data.get('message', '').strip()
        robot_id = data.get('robot_id', 'robot_01')
        user_id = data.get('user_id')

        print(f"\n[CHAT] Robot {robot_id} message: {user_message[:50]}...")

        result = await handle_robot_chat(user_message, robot_id, user_id)

        return result

    except Exception as e:
        error = f"Error processing robot chat: {str(e)}"
        print(f"[CHAT ERROR] {error}")
        return {"success": False, "response": f"Error: {error}"}


# =============================================================================
# TELEMETRY ENDPOINTS
# =============================================================================

@app.post("/telemetry")
async def telemetry(request: Request):
    """Receive robot telemetry"""
    try:
        data = await request.json()
        robot_id = data.get('robot_id', 'robot_01')
        telemetry_data = data.get('telemetry', data)

        result = await receive_telemetry(robot_id, telemetry_data)

        return result

    except Exception as e:
        error = f"Error processing telemetry: {str(e)}"
        print(f"[TELEMETRY ERROR] {error}")
        return {"success": False, "error": error}


@app.get("/telemetry/status")
async def telemetry_status(robot_id: str = None):
    """Get robot status"""
    return await get_robot_status(robot_id)


@app.get("/telemetry/history/{robot_id}")
async def telemetry_history(robot_id: str, limit: int = 10):
    """Get robot telemetry history"""
    return await get_robot_history(robot_id, limit)


# =============================================================================
# STREAMING ENDPOINTS
# =============================================================================

@app.get("/stream/postgresql")
async def stream_postgresql_endpoint():
    """Stream PostgreSQL logs"""
    return await stream_postgresql()


@app.get("/stream/qdrant")
async def stream_qdrant_endpoint():
    """Stream Qdrant telemetry"""
    return await stream_qdrant()


@app.get("/data/postgresql")
async def get_postgresql_data_endpoint():
    """Get PostgreSQL logs"""
    return await get_postgresql_data()


@app.get("/data/qdrant")
async def get_qdrant_data_endpoint():
    """Get Qdrant telemetry"""
    return await get_qdrant_data()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(f"Starting {SYSTEM_NAME}")
    print("=" * 60)
    print(f"Python version: {sys.version}")
    print(f"Visit http://{SERVER_HOST}:{SERVER_PORT}")
    print("=" * 60)
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
