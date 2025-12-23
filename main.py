#!/usr/bin/env python3
"""
WayfindR-LLM Main Application
FastAPI server for tour guide robot system
"""
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn
import sys
import asyncio
import json
from datetime import datetime
from typing import List

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
from api.map_handler import (
    get_floors,
    get_floor_details,
    get_waypoints,
    get_waypoint,
    create_waypoint,
    update_waypoint,
    delete_waypoint,
    block_waypoint,
    unblock_waypoint,
    get_zones,
    get_blocked_zones,
    create_zone,
    create_blocked_zone,
    update_zone,
    delete_zone,
    activate_zone,
    deactivate_zone,
    get_map_state_for_robot,
    get_map_image_config,
    list_available_maps
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


@app.get("/diagnostics/{robot_id}", response_class=HTMLResponse)
async def robot_diagnostics(request: Request, robot_id: str):
    """Serve robot diagnostics page"""
    try:
        return templates.TemplateResponse("diagnostics.html", {
            "request": request,
            "robot_id": robot_id
        })
    except Exception as e:
        error_msg = f"ERROR: Could not render diagnostics template: {e}"
        print(error_msg)
        return HTMLResponse(content=f"<html><body>{error_msg}</body></html>", status_code=500)


@app.get("/map", response_class=HTMLResponse)
async def map_view(request: Request):
    """Serve live map monitoring page"""
    try:
        return templates.TemplateResponse("map.html", {"request": request})
    except Exception as e:
        error_msg = f"ERROR: Could not render map template: {e}"
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
# ROBOT MONITORING ENDPOINTS
# =============================================================================

@app.get("/robots")
async def list_robots():
    """
    List all registered robots in the system
    Robots are auto-registered when they send telemetry
    """
    try:
        from rag.qdrant_store import get_latest_telemetry
        all_telemetry = get_latest_telemetry()

        robots = []
        for robot_id, telemetry in all_telemetry.items():
            robots.append({
                "robot_id": robot_id,
                "status": telemetry.get("status", "unknown"),
                "battery": telemetry.get("battery", "N/A"),
                "location": telemetry.get("current_location", "N/A"),
                "last_seen": telemetry.get("timestamp", "N/A")
            })

        return {
            "success": True,
            "count": len(robots),
            "robots": robots
        }
    except Exception as e:
        return {"success": False, "error": str(e), "robots": []}


@app.get("/robots/{robot_id}")
async def get_robot(robot_id: str):
    """
    Get details for a specific robot
    """
    try:
        from rag.qdrant_store import get_robot_telemetry_history, get_latest_telemetry

        # Get latest status
        all_telemetry = get_latest_telemetry(robot_id)
        if robot_id not in all_telemetry:
            return {"success": False, "error": f"Robot {robot_id} not found"}

        latest = all_telemetry[robot_id]

        # Get recent history
        history = get_robot_telemetry_history(robot_id, limit=5)

        return {
            "success": True,
            "robot_id": robot_id,
            "current": {
                "status": latest.get("status", "unknown"),
                "battery": latest.get("battery", "N/A"),
                "location": latest.get("current_location", "N/A"),
                "destination": latest.get("destination", None),
                "last_update": latest.get("timestamp", "N/A")
            },
            "recent_history": history
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# MAP AND ZONE ENDPOINTS
# =============================================================================

@app.get("/map/floors")
async def list_floors():
    """Get all floors in the building"""
    return await get_floors()


@app.get("/map/floors/{floor_id}")
async def get_floor(floor_id: str):
    """Get detailed floor information"""
    return await get_floor_details(floor_id)


@app.get("/map/waypoints")
async def list_waypoints(floor_id: str = None, accessible_only: bool = True):
    """Get all waypoints"""
    return await get_waypoints(floor_id, accessible_only)


@app.get("/map/waypoints/{waypoint_id}")
async def get_single_waypoint(waypoint_id: str):
    """Get a specific waypoint"""
    return await get_waypoint(waypoint_id)


@app.post("/map/waypoints")
async def add_waypoint(request: Request):
    """Create a new waypoint"""
    data = await request.json()
    return await create_waypoint(data)


@app.put("/map/waypoints/{waypoint_id}")
async def modify_waypoint(waypoint_id: str, request: Request):
    """Update a waypoint"""
    updates = await request.json()
    return await update_waypoint(waypoint_id, updates)


@app.delete("/map/waypoints/{waypoint_id}")
async def remove_waypoint(waypoint_id: str):
    """Delete a waypoint"""
    return await delete_waypoint(waypoint_id)


@app.post("/map/waypoints/{waypoint_id}/block")
async def block_single_waypoint(waypoint_id: str, request: Request):
    """Block a waypoint (make inaccessible)"""
    data = await request.json()
    reason = data.get("reason", "Blocked by operator")
    return await block_waypoint(waypoint_id, reason)


@app.post("/map/waypoints/{waypoint_id}/unblock")
async def unblock_single_waypoint(waypoint_id: str):
    """Unblock a waypoint"""
    return await unblock_waypoint(waypoint_id)


@app.get("/map/zones")
async def list_zones(floor_id: str = None, active_only: bool = True, zone_type: str = None):
    """Get all zones"""
    return await get_zones(floor_id, active_only, zone_type)


@app.get("/map/zones/blocked")
async def list_blocked_zones(floor_id: str = None):
    """Get all blocked zones"""
    return await get_blocked_zones(floor_id)


@app.post("/map/zones")
async def add_zone(request: Request):
    """Create a new zone"""
    data = await request.json()
    return await create_zone(data)


@app.post("/map/zones/blocked")
async def add_blocked_zone(request: Request):
    """Quick create a blocked zone"""
    data = await request.json()
    return await create_blocked_zone(
        name=data.get("name", "Blocked Area"),
        floor_id=data.get("floor_id", "floor_1"),
        polygon=data.get("polygon", []),
        reason=data.get("reason", ""),
        expires_at=data.get("expires_at")
    )


@app.put("/map/zones/{zone_id}")
async def modify_zone(zone_id: str, request: Request):
    """Update a zone"""
    updates = await request.json()
    return await update_zone(zone_id, updates)


@app.delete("/map/zones/{zone_id}")
async def remove_zone(zone_id: str):
    """Delete a zone"""
    return await delete_zone(zone_id)


@app.post("/map/zones/{zone_id}/activate")
async def activate_single_zone(zone_id: str):
    """Activate a zone"""
    return await activate_zone(zone_id)


@app.post("/map/zones/{zone_id}/deactivate")
async def deactivate_single_zone(zone_id: str):
    """Deactivate a zone"""
    return await deactivate_zone(zone_id)


@app.get("/map/state/{robot_id}")
async def get_robot_map_state(robot_id: str, floor_id: str = None):
    """
    Get current map state for a robot
    Returns accessible waypoints, blocked zones, etc.
    """
    return await get_map_state_for_robot(robot_id, floor_id)


@app.get("/map/image/config")
async def get_map_config(map_name: str = "first_map"):
    """
    Get map image configuration for browser display
    Returns resolution, origin, and image URL
    """
    return await get_map_image_config(map_name)


@app.get("/map/image/list")
async def get_available_maps():
    """List all available map files"""
    return await list_available_maps()


@app.get("/map/robots/positions")
async def get_robot_positions_on_map(map_name: str = "first_map"):
    """
    Get all robot positions converted to pixel coordinates for map display

    Returns robot positions in both world coordinates (meters) and pixel coordinates
    """
    try:
        from rag.qdrant_store import get_latest_telemetry

        # Get map config for coordinate conversion
        map_config = await get_map_image_config(map_name)
        if not map_config.get("success"):
            return {"success": False, "error": "Map not found"}

        resolution = map_config.get("resolution", 0.05)  # meters per pixel
        origin = map_config.get("origin", [0, 0, 0])  # [x, y, theta] in meters
        img_width = map_config.get("image_width", 0)
        img_height = map_config.get("image_height", 0)

        # Get all robot telemetry
        all_telemetry = get_latest_telemetry()

        robots = []
        for robot_id, telemetry in all_telemetry.items():
            # Get world coordinates
            world_x = telemetry.get("x", 0)
            world_y = telemetry.get("y", 0)

            # Convert world coordinates to pixel coordinates
            # Formula: pixel = (world - origin) / resolution
            # Y axis is flipped in image coordinates
            pixel_x = int((world_x - origin[0]) / resolution)
            pixel_y = int(img_height - (world_y - origin[1]) / resolution)

            robots.append({
                "robot_id": robot_id,
                "status": telemetry.get("status", "unknown"),
                "battery": telemetry.get("battery", 0),
                "location": telemetry.get("current_location", "unknown"),
                "destination": telemetry.get("destination", ""),
                "world_position": {"x": world_x, "y": world_y},
                "pixel_position": {"x": pixel_x, "y": pixel_y},
                "last_seen": telemetry.get("timestamp", "")
            })

        return {
            "success": True,
            "map_name": map_name,
            "map_dimensions": {"width": img_width, "height": img_height},
            "resolution": resolution,
            "origin": origin,
            "robots": robots,
            "count": len(robots)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# SEMANTIC SEARCH ENDPOINTS
# =============================================================================

@app.get("/search/telemetry")
async def search_telemetry(q: str, limit: int = 10):
    """
    Semantic search over robot telemetry

    Examples:
    - /search/telemetry?q=robots with low battery
    - /search/telemetry?q=stuck robots
    - /search/telemetry?q=robots in lobby
    """
    try:
        from rag.qdrant_store import search_telemetry as qdrant_search
        results = qdrant_search(q, limit=limit)
        return {
            "success": True,
            "query": q,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/search/messages")
async def search_messages(q: str, limit: int = 10):
    """
    Semantic search over chat messages and logs

    Examples:
    - /search/messages?q=navigation commands
    - /search/messages?q=error reports
    - /search/messages?q=visitor questions about cafeteria
    """
    try:
        from rag.postgresql_store import search_logs
        results = search_logs(q, limit=limit)
        return {
            "success": True,
            "query": q,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# TELEMETRY MANAGEMENT ENDPOINTS
# =============================================================================

@app.get("/telemetry/stats")
async def get_telemetry_statistics():
    """Get telemetry collection statistics"""
    try:
        from rag.qdrant_store import get_telemetry_stats
        stats = get_telemetry_stats()
        return {"success": True, **stats}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/telemetry/cleanup")
async def cleanup_telemetry(hours: int = 24):
    """
    Clean up old telemetry data

    Args:
        hours: Delete telemetry older than this many hours (default 24)
    """
    try:
        from rag.qdrant_store import cleanup_old_telemetry
        deleted = cleanup_old_telemetry(hours=hours)
        return {
            "success": True,
            "deleted_count": deleted,
            "message": f"Deleted {deleted} telemetry records older than {hours} hours"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


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
# WEBSOCKET ENDPOINTS
# =============================================================================

class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


# Global connection manager
ws_manager = ConnectionManager()


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """
    WebSocket endpoint for real-time telemetry updates

    Clients receive:
    - Robot position updates
    - Status changes
    - Battery alerts
    """
    await ws_manager.connect(websocket)

    try:
        # Send initial data
        from rag.qdrant_store import get_latest_telemetry
        initial_data = get_latest_telemetry()
        await websocket.send_json({
            "type": "initial",
            "robots": {rid: tel for rid, tel in initial_data.items()}
        })

        # Keep connection alive and send periodic updates
        while True:
            try:
                # Wait for client ping or timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)

                # If client sends 'ping', respond with current data
                if data == 'ping':
                    current_data = get_latest_telemetry()
                    await websocket.send_json({
                        "type": "update",
                        "robots": {rid: tel for rid, tel in current_data.items()},
                        "timestamp": datetime.now().isoformat()
                    })

            except asyncio.TimeoutError:
                # Send periodic updates even without ping
                current_data = get_latest_telemetry()
                await websocket.send_json({
                    "type": "update",
                    "robots": {rid: tel for rid, tel in current_data.items()},
                    "timestamp": datetime.now().isoformat()
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error: {e}")
        ws_manager.disconnect(websocket)


async def broadcast_telemetry_update(robot_id: str, telemetry: dict):
    """Called when new telemetry is received to broadcast to all clients"""
    if ws_manager.active_connections:
        await ws_manager.broadcast({
            "type": "robot_update",
            "robot_id": robot_id,
            "telemetry": telemetry,
            "timestamp": datetime.now().isoformat()
        })


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
