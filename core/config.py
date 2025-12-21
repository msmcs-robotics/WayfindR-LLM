"""
Shared configuration constants for WayfindR-LLM Tour Guide Robot System.
"""

# =============================================================================
# SYSTEM INFO
# =============================================================================

SYSTEM_NAME = "WayfindR Tour Guide Robot"
SYSTEM_VERSION = "1.0.0"

# =============================================================================
# ROBOT CONFIGURATION
# =============================================================================

# Available waypoints in the building
WAYPOINTS = [
    "reception",
    "lobby",
    "cafeteria",
    "meeting_room_a",
    "meeting_room_b",
    "conference_hall",
    "elevator",
    "restroom",
    "exit",
    "main_hall",
    "office_wing_a",
    "office_wing_b",
]

# Stuck detection threshold (seconds without movement)
STUCK_THRESHOLD_SECONDS = 60

# Context update interval (seconds)
CONTEXT_UPDATE_INTERVAL = 60

# Telemetry retention (hours)
TELEMETRY_RETENTION_HOURS = 24

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

DB_CONFIG = {
    "dbname": "wayfind_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5435"  # Non-standard port to avoid conflicts
}

# =============================================================================
# QDRANT CONFIGURATION
# =============================================================================

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
TELEMETRY_COLLECTION = "robot_telemetry"

# =============================================================================
# API ENDPOINTS
# =============================================================================

MCP_API_URL = "http://localhost:5000"

# =============================================================================
# LLM CONFIGURATION
# =============================================================================

# Imported from llm_config.py - these are defaults if that module is unavailable
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_LLM_MODEL = "llama3.3:70b-instruct-q5_K_M"

# =============================================================================
# SERVER CONFIGURATION
# =============================================================================

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5000

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_waypoint_list() -> list:
    """Return list of available waypoints"""
    return WAYPOINTS.copy()

def is_valid_waypoint(waypoint: str) -> bool:
    """Check if waypoint is valid"""
    return waypoint.lower() in [w.lower() for w in WAYPOINTS]
