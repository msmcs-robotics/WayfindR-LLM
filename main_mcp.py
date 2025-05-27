from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastmcp import FastMCP
import uvicorn
import sys
from datetime import datetime

# Import our modular components
from chat_handler_mcp import ChatHandler
from telemetry_handler_mcp import TelemetryHandler
from rag_store import init_stores, get_system_health

# Initialize stores on startup
init_stores()

# Create FastAPI app and MCP server
app = FastAPI(title="Robot Guidance System", version="1.0.0")
mcp = FastMCP("Robot Guidance and Navigation", app=app)

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

# Initialize handlers with error handling
try:
    chat_handler = ChatHandler(mcp)
    telemetry_handler = TelemetryHandler()
    print("✅ All handlers initialized successfully")
except Exception as e:
    print(f"❌ Handler initialization failed: {e}")
    # You might want to exit or use fallback handlers
    raise

# ─── ERROR HANDLING WRAPPER ────────────────────────────

async def handle_endpoint_error(endpoint_func, *args, **kwargs):
    """Generic error handler for endpoints"""
    try:
        return await endpoint_func(*args, **kwargs)
    except Exception as e:
        print(f"[ENDPOINT ERROR] {endpoint_func.__name__}: {e}")
        return {"error": f"Internal server error in {endpoint_func.__name__}", "details": str(e)}

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
    """Enhanced health check endpoint"""
    try:
        system_health = get_system_health()
        
        return {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "chat_handler": "online",
                "telemetry_handler": "online", 
                "mcp_server": "online"
            },
            "system_health": system_health
        }
    except Exception as e:
        return {
            "status": "partial",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "components": {
                "chat_handler": "unknown",
                "telemetry_handler": "unknown",
                "mcp_server": "online"
            }
        }

@app.get("/test")
async def test():
    return {"message": "Robot Guidance System is running!"}

# ─── CHAT ENDPOINTS ────────────────────────────────────

@app.post("/chat")
async def chat(request: Request):
    """Main chat endpoint for user interactions"""
    return await handle_endpoint_error(chat_handler.handle_chat, request)

@app.post("/llm_command")
async def llm_command(request: Request):
    """Process natural language commands for robot navigation"""
    return await handle_endpoint_error(chat_handler.handle_llm_command, request)

@app.post("/robot_message")
async def robot_message(request: Request):
    """Handle messages from robots requesting assistance"""
    return await handle_endpoint_error(chat_handler.handle_robot_message, request)

@app.get("/logs")
async def get_logs():
    """Get chat and command logs"""
    return await handle_endpoint_error(chat_handler.get_logs)

@app.get("/log_count")
async def log_count():
    """Get current log count"""
    return await handle_endpoint_error(chat_handler.get_log_count)

# ─── TELEMETRY ENDPOINTS ───────────────────────────────

@app.post("/telemetry")
async def receive_telemetry(request: Request):
    """Receive and store robot telemetry data"""
    return await handle_endpoint_error(telemetry_handler.receive_telemetry, request)

@app.get("/telemetry/status")
async def get_telemetry_status():
    """Get current status of all robots"""
    return await handle_endpoint_error(telemetry_handler.get_telemetry_status)

@app.get("/telemetry/robot/{robot_id}")
async def get_robot_telemetry(robot_id: str, hours: int = 1):
    """Get telemetry history for specific robot"""
    return await handle_endpoint_error(telemetry_handler.get_robot_telemetry, robot_id, hours)

@app.get("/qdrant_logs")
async def get_qdrant_logs():
    """Get Qdrant vector database logs"""
    return await handle_endpoint_error(telemetry_handler.get_qdrant_logs)

@app.get("/postgres_logs")
async def get_postgres_logs():
    """Get PostgreSQL database logs"""
    return await handle_endpoint_error(telemetry_handler.get_postgres_logs)

# ─── NAVIGATION CONTROL ENDPOINTS ──────────────────────

@app.post("/control/pause")
async def pause_simulation():
    """Pause robot navigation (if using simulation)"""
    return await handle_endpoint_error(chat_handler.pause_simulation)

@app.post("/control/continue")
async def continue_simulation():
    """Resume robot navigation (if using simulation)"""
    return await handle_endpoint_error(chat_handler.continue_simulation)

@app.get("/simulation_info")
async def get_simulation_info():
    """Get robot and navigation system information"""
    return await handle_endpoint_error(chat_handler.get_simulation_info)

# ─── MCP TOOL REGISTRATION ─────────────────────────────

# Register MCP tools through handlers
@mcp.tool()
async def navigate(waypoint_name: str) -> dict:
    """Navigate robot to a single waypoint"""
    return await chat_handler.navigate_to_waypoint(waypoint_name)

@mcp.tool()
async def nav_points(waypoints: list) -> dict:
    """Navigate robot through multiple waypoints in sequence"""
    return await chat_handler.navigate_multiple_waypoints(waypoints)

@mcp.tool()
async def get_robot_status() -> dict:
    """Get current status of all robots"""
    return await telemetry_handler.get_current_robot_status()

@mcp.tool()
async def emergency_stop(robot_id: str = None) -> dict:
    """Emergency stop for specified robot or all robots"""
    return await chat_handler.emergency_stop(robot_id)

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