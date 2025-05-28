from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn
import sys
from datetime import datetime

# Import streamlined components
from chat_handler import ChatHandler
from telemetry_handler import TelemetryHandler
from rag_store import init_stores, get_system_health, get_recent_telemetry_logs, get_recent_chat_logs

# Initialize stores on startup
init_stores()

# Create FastAPI app
app = FastAPI(title="Robot Guidance System", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize handlers
try:
    chat_handler = ChatHandler()
    telemetry_handler = TelemetryHandler()
    print("✅ All handlers initialized successfully")
except Exception as e:
    print(f"❌ Handler initialization failed: {e}")
    raise

# ─── CORE ENDPOINTS ────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main chat interface"""
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        error_msg = f"ERROR: Could not render template 'index.html': {e}"
        print(error_msg)
        return HTMLResponse(content=f"<html><body>{error_msg}</body></html>", status_code=500)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        system_health = get_system_health()
        return {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "system_health": system_health
        }
    except Exception as e:
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

# ─── CHAT ENDPOINTS ────────────────────────────────────

@app.post("/chat")
async def web_user_chat(request: Request):
    """Chat endpoint for web users"""
    return await chat_handler.handle_web_chat(request)

@app.post("/llm_command")
async def llm_command(request: Request):
    """Handle LLM commands from web interface (same as /chat but different name for JS compatibility)"""
    return await chat_handler.handle_web_chat(request)

@app.post("/robot_chat")
async def robot_user_chat(request: Request):
    """Chat endpoint for robot users (via Android app)"""
    return await chat_handler.handle_robot_chat(request)

@app.get("/chat/history/{conversation_id}")
async def get_conversation_history(conversation_id: str):
    """Get conversation history by ID"""
    return await chat_handler.get_conversation_history(conversation_id)

# ─── LOG STREAMING ENDPOINTS ───────────────────────────

@app.get("/qdrant_logs")
async def get_qdrant_logs():
    """Get recent Qdrant telemetry logs"""
    try:
        logs = get_recent_telemetry_logs(limit=20)
        return {
            "status": "success",
            "records": logs,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"❌ Qdrant logs error: {e}")
        return {
            "status": "error", 
            "error": str(e),
            "records": []
        }

@app.get("/postgres_logs")
async def get_postgres_logs():
    """Get recent PostgreSQL chat logs"""
    try:
        logs = get_recent_chat_logs(limit=20)
        return {
            "status": "success",
            "message_chains": logs,
            "relationships": [],  # Keep for JS compatibility
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"❌ Postgres logs error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message_chains": [],
            "relationships": []
        }

# ─── TELEMETRY ENDPOINTS ───────────────────────────────

@app.post("/telemetry")
async def receive_telemetry(request: Request):
    """Receive and store robot telemetry data"""
    return await telemetry_handler.receive_telemetry(request)

@app.get("/telemetry/status")
async def get_telemetry_status(robot_id: str = None):
    """Get current status of robots"""
    return await telemetry_handler.get_robot_status(robot_id)

# ─── ROBOT COMMAND ENDPOINTS ───────────────────────────

@app.post("/robot/{robot_id}/alert")
async def create_robot_alert(robot_id: str, request: Request):
    """Create alert when robot needs assistance"""
    try:
        data = await request.json()
        message = data.get('message', 'Robot needs assistance')
        return await chat_handler.create_stuck_alert(robot_id, message)
    except Exception as e:
        return {"error": str(e), "success": False}

@app.post("/robot/{robot_id}/navigate")
async def send_navigation_command(robot_id: str, request: Request):
    """Send navigation command to robot"""
    try:
        data = await request.json()
        waypoints = data.get('waypoints', [])
        if not waypoints:
            return {"error": "No waypoints provided", "success": False}
        return await chat_handler.send_navigation_command(robot_id, waypoints)
    except Exception as e:
        return {"error": str(e), "success": False}

# ─── STARTUP ───────────────────────────────────────────

if __name__ == "__main__":
    print("🤖 Starting Robot Guidance System...")
    print(f"Python version: {sys.version}")
    print("🌐 Web interface: http://127.0.0.1:5000")
    print("📡 API endpoints: http://127.0.0.1:5000/docs")
    print("📊 Health check: http://127.0.0.1:5000/health")
    
    uvicorn.run(
        app, 
        host="127.0.0.1", 
        port=5000,
        log_level="info"
    )