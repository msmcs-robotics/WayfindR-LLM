# main_mcp.py - Clean integration with proper async/sync handling
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import asyncio
from datetime import datetime

from config_manager import get_config
from db_manager import get_db_manager
from chat_handler import ChatHandler
from telemetry_handler import TelemetryHandler
from context_manager import get_context_manager
from utils import success_response, error_response

# Load and validate configuration
config = get_config()
if not config.validate():
    raise RuntimeError("Configuration validation failed")

# Create FastAPI app
app = FastAPI(title=config.system.name, version=config.system.version)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global handlers
chat_handler = None
telemetry_handler = None
db_manager = None
context_manager = None

@app.on_event("startup")
async def startup_event():
    """Initialize services in proper order"""
    global chat_handler, telemetry_handler, db_manager, context_manager
    
    try:
        print(f"🚀 Starting {config.system.name} v{config.system.version}")
        
        # Initialize database manager first
        db_manager = get_db_manager()
        print("✅ Database manager ready")
        
        # Initialize context manager
        context_manager = get_context_manager()
        await context_manager.start_background_updates()
        print("✅ Context manager ready")
        
        # Initialize handlers
        chat_handler = ChatHandler()
        telemetry_handler = TelemetryHandler()
        print("✅ All handlers initialized")
        
        print("🎉 System startup complete!")
        
    except Exception as e:
        print(f"❌ Startup failed: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown"""
    print("🛑 Shutting down gracefully...")

# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main chat interface"""
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        error_msg = f"ERROR: Could not render template 'index.html': {e}"
        print(error_msg)
        return HTMLResponse(content=f"<html><body><h1>Template Error</h1><p>{error_msg}</p></body></html>", status_code=500)

# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH & STATUS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """Health check endpoint - matches frontend expectations"""
    print("🔍 Health check requested")
    try:
        # Get system health from database manager
        system_health = db_manager.check_system_health()
        
        # Get active robots count
        active_robots = await context_manager.get_active_robots()
        
        health_data = {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "system_health": system_health,
            "active_robots": {
                "count": len(active_robots),
                "robot_ids": active_robots
            },
            "components": {
                "postgres": system_health.get("postgres_status", "unknown"),
                "qdrant": system_health.get("qdrant_status", "unknown"),
                "context_manager": "healthy" if context_manager else "not_initialized"
            }
        }
        
        print(f"✅ Health check successful: {len(active_robots)} active robots")
        return success_response(health_data)
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return error_response(f"Health check failed: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════════
# CHAT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/chat")
async def web_user_chat(request: Request):
    """Web user chat endpoint - matches frontend POST expectations"""
    try:
        print("💭 Web chat request received")
        result = await chat_handler.handle_web_chat(request)
        print(f"📤 Web chat response: {result.get('success', False)}")
        return result
    except Exception as e:
        print(f"❌ Web chat error: {e}")
        return error_response(f"Chat processing failed: {str(e)}")

@app.post("/robot_chat")
async def robot_user_chat(request: Request):
    """Robot user chat endpoint"""
    try:
        print("🤖 Robot chat request received")
        return await chat_handler.handle_robot_chat(request)
    except Exception as e:
        print(f"❌ Robot chat error: {e}")
        return error_response(f"Robot chat failed: {str(e)}")

@app.get("/chat/history/{conversation_id}")  
async def get_conversation_history(conversation_id: str):
    """Get conversation history"""
    try:
        return await chat_handler.get_conversation_history(conversation_id)
    except Exception as e:
        print(f"❌ Error getting conversation history: {e}")
        return error_response(f"Failed to get conversation history: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════════
# TELEMETRY ENDPOINTS  
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/telemetry")
async def receive_telemetry(request: Request):
    """Receive telemetry data from robots"""
    try:
        return await telemetry_handler.receive_telemetry(request)
    except Exception as e:
        print(f"❌ Telemetry reception error: {e}")
        return error_response(f"Telemetry processing failed: {str(e)}")

@app.get("/telemetry/status")
async def get_telemetry_status(robot_id: str = None):
    """Get robot telemetry status"""
    try:
        return await telemetry_handler.get_robot_status(robot_id)
    except Exception as e:
        print(f"❌ Telemetry status error: {e}")
        return error_response(f"Failed to get telemetry status: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════════
# LOG ENDPOINTS - Matches frontend JavaScript expectations
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/qdrant_logs")
async def get_qdrant_logs():
    """Get recent Qdrant telemetry logs - matches frontend format"""
    try:
        print("📡 Fetching Qdrant logs...")
        
        # Get recent telemetry logs from database manager
        logs = db_manager.get_recent_telemetry_logs(limit=20)
        
        # Format for frontend expectations
        records = []
        for log in logs:
            # Extract the payload data 
            if 'payload' in log:
                records.append({
                    'id': log.get('id', 'unknown'),
                    'payload': log['payload']
                })
            else:
                # Direct format
                records.append(log)
        
        print(f"✅ Retrieved {len(records)} Qdrant records")
        
        # Frontend expects: {status: "success", records: [...]}
        return {
            "status": "success", 
            "records": records
        }
        
    except Exception as e:
        print(f"❌ Qdrant logs error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/postgres_logs") 
async def get_postgres_logs():
    """Get recent PostgreSQL chat logs - matches frontend format"""
    try:
        print("💾 Fetching PostgreSQL logs...")
        
        # Get recent chat logs from database manager
        logs = db_manager.get_recent_chat_logs(limit=20)
        
        # Format logs for frontend
        # Frontend expects arrays: [id, content, details, timestamp]
        message_chains = []
        relationships = []  # For future relationship data
        
        for log in logs:
            # Create array format expected by frontend
            log_array = [
                str(log.get('conversation_id', 'unknown')),  # ID
                log.get('content', ''),                      # Content  
                {                                            # Details object
                    'role': log.get('role', 'unknown'),
                    'user_type': log.get('user_type', 'unknown'),
                    'user_id': log.get('user_id', 'unknown')
                },
                log.get('timestamp', datetime.now().isoformat())  # Timestamp
            ]
            message_chains.append(log_array)
        
        print(f"✅ Retrieved {len(message_chains)} PostgreSQL records")
        
        # Frontend expects: {status: "success", relationships: [...], message_chains: [...]}
        return {
            "status": "success",
            "relationships": relationships,
            "message_chains": message_chains
        }
        
    except Exception as e:
        print(f"❌ PostgreSQL logs error: {e}")
        return {
            "status": "error", 
            "error": str(e)
        }

# ═══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return HTMLResponse(
        content="<html><body><h1>404 - Page Not Found</h1></body></html>",
        status_code=404
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    print(f"❌ Internal server error: {exc}")
    return HTMLResponse(
        content="<html><body><h1>500 - Internal Server Error</h1></body></html>",
        status_code=500
    )

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"🤖 Starting {config.system.name} v{config.system.version}")
    print(f"🌐 Server will be available at: http://{config.server.host}:{config.server.port}")
    
    uvicorn.run(
        app, 
        host=config.server.host, 
        port=config.server.port,
        log_level="info"
    )