# WayfindR-LLM Architecture

## Overview

WayfindR-LLM follows a modular architecture designed for scalability and maintainability. The system is built around three core concepts:

1. **Separation of concerns**: Each component handles a specific responsibility
2. **Self-registration**: Robots automatically appear when they send telemetry
3. **Dual-mode operation**: Distinct interfaces for operators and visitors

## Component Architecture

### 1. FastAPI Application Layer (`main.py`)

The main application serves as the entry point and route dispatcher.

```
main.py
├── Template Routes (HTML pages)
│   ├── GET /              → Dashboard
│   ├── GET /map           → Live map monitoring
│   └── GET /diagnostics/{robot_id} → Robot diagnostics
│
├── Chat Routes
│   ├── POST /chat         → Operator chat
│   └── POST /robot_chat   → Visitor/robot chat
│
├── Telemetry Routes
│   ├── POST /telemetry    → Receive robot telemetry
│   ├── GET /telemetry/status → Get robot statuses
│   └── GET /telemetry/history/{robot_id} → Get history
│
├── Robot Monitoring Routes
│   ├── GET /robots        → List all robots
│   └── GET /robots/{robot_id} → Get robot details
│
├── Map/Zone Routes
│   ├── GET /map/floors    → List floors
│   ├── GET /map/waypoints → List waypoints
│   ├── GET /map/zones     → List zones
│   └── GET /map/state/{robot_id} → Robot navigation state
│
└── Streaming Routes
    ├── GET /stream/postgresql → SSE log stream
    └── GET /stream/qdrant     → SSE telemetry stream
```

### 2. Agent System (`agents/`)

The LLM-powered agent system processes natural language and executes commands.

```
┌──────────────────────────────────────────────────────────────────┐
│                        Agent Pipeline                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  User Message                                                     │
│       │                                                           │
│       ▼                                                           │
│  ┌─────────────────┐                                              │
│  │  Intent Parser  │  ← Determines what user wants                │
│  │  (LLM Call #1)  │    Returns: intent, entities, confidence     │
│  └────────┬────────┘                                              │
│           │                                                       │
│           ▼                                                       │
│  ┌─────────────────────┐                                          │
│  │ Function Executor   │  ← Executes robot commands               │
│  │ (if action needed)  │    Calls Qdrant/PostgreSQL               │
│  └────────┬────────────┘                                          │
│           │                                                       │
│           ▼                                                       │
│  ┌─────────────────────┐                                          │
│  │ Response Generator  │  ← Creates natural language response     │
│  │   (LLM Call #2)     │    Includes context and results          │
│  └────────┬────────────┘                                          │
│           │                                                       │
│           ▼                                                       │
│     Final Response                                                │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

#### Intent Parser (`intent_parser.py`)

Analyzes user messages to determine intent:

```python
# Operator intents
OPERATOR_INTENTS = [
    "get_robot_status",      # Check robot status
    "send_robot_command",    # Send command to robot
    "get_fleet_overview",    # Fleet-wide status
    "manage_zones",          # Zone management
    "system_health",         # System diagnostics
    "general_query"          # General questions
]

# Visitor intents
VISITOR_INTENTS = [
    "get_directions",        # Navigation help
    "location_info",         # Info about locations
    "general_help",          # General assistance
    "greeting",              # Hello/goodbye
    "feedback"               # Comments/complaints
]
```

#### Function Executor (`function_executor.py`)

Maps intents to executable functions:

```python
AVAILABLE_FUNCTIONS = {
    "get_robot_status": get_robot_status_fn,
    "get_all_robot_status": get_all_robot_status_fn,
    "send_navigation_command": send_navigation_command_fn,
    "generate_system_report": generate_system_report_fn,
    "get_conversation_history": get_conversation_history_fn,
}
```

#### Response Generator (`response_generator.py`)

Generates contextual responses using:
- Original user message
- Parsed intent
- Function execution results
- System context (telemetry, etc.)

### 3. API Handlers (`api/`)

#### Chat Handler (`chat_handler.py`)

```python
async def handle_web_chat(message: str, user_id: str) -> Dict:
    """
    Operator chat flow:
    1. Parse intent (operator context)
    2. Execute functions if needed
    3. Generate operator-appropriate response
    4. Log to PostgreSQL
    """

async def handle_robot_chat(message: str, robot_id: str, user_id: str) -> Dict:
    """
    Visitor chat flow:
    1. Parse intent (visitor context)
    2. Get robot telemetry for context
    3. Generate visitor-friendly response
    4. Log to PostgreSQL
    """
```

#### Telemetry Handler (`telemetry_handler.py`)

```python
async def receive_telemetry(robot_id: str, telemetry_data: Dict) -> Dict:
    """
    1. Validate telemetry data
    2. Store in Qdrant (vector format)
    3. Update in-memory cache
    4. Return acknowledgment
    """
```

#### Map Handler (`map_handler.py`)

Provides CRUD operations for:
- Floors (building levels)
- Waypoints (navigation destinations)
- Zones (blocked areas, priority paths, etc.)

### 4. Storage Layer (`rag/`)

#### Qdrant Store (`qdrant_store.py`)

Vector database for telemetry:

```python
# Collection structure
TELEMETRY_COLLECTION = "robot_telemetry"

# Vector payload
{
    "robot_id": "robot_01",
    "timestamp": "2024-01-15T10:30:00",
    "battery": 85,
    "status": "idle",
    "current_location": "lobby",
    "destination": null,
    "sensors": {...}
}

# Key functions
def store_telemetry(robot_id, telemetry_data) -> bool
def get_latest_telemetry(robot_id=None) -> Dict
def get_robot_telemetry_history(robot_id, limit=10) -> List
```

#### PostgreSQL Store (`postgresql_store.py`)

Relational database for conversations:

```python
# Table: conversations
{
    "id": "uuid",
    "robot_id": "robot_01",
    "user_id": "visitor_123",
    "user_message": "Where is the cafeteria?",
    "assistant_response": "The cafeteria is on floor 2...",
    "intent": "get_directions",
    "timestamp": "2024-01-15T10:30:00"
}

# Key functions
def log_conversation(robot_id, user_id, message, response, intent) -> bool
def get_conversation_history(robot_id=None, limit=50) -> List
```

### 5. Map System (`core/map_config.py`)

Data models for spatial management:

```python
@dataclass
class Waypoint:
    id: str
    name: str
    floor_id: str
    position: Coordinate
    waypoint_type: WaypointType  # destination, charging, elevator, etc.
    accessible: bool
    connections: List[str]

@dataclass
class Zone:
    id: str
    name: str
    floor_id: str
    zone_type: ZoneType  # blocked, priority, slow, restricted
    polygon: List[Coordinate]
    active: bool
    expires_at: Optional[datetime]

class MapManager:
    """Singleton manager for live map updates"""

    def is_point_in_blocked_zone(x, y, floor_id) -> bool
    def get_accessible_waypoints(floor_id) -> List[Waypoint]
    def create_blocked_zone(name, floor_id, polygon, reason) -> Zone
```

## Data Flow

### Robot Telemetry Flow

```
Robot (ROS 2)
    │
    │ POST /telemetry
    │ {robot_id, battery, location, status, sensors}
    │
    ▼
Telemetry Handler
    │
    │ validate + normalize
    │
    ▼
Qdrant Store
    │
    │ vector storage
    │
    ▼
Dashboard / Diagnostics
    │
    │ GET /robots, /telemetry/status
    │
    ▼
Real-time Display
```

### Chat Flow (Operator)

```
Operator Dashboard
    │
    │ POST /chat
    │ {message: "What's robot_01 status?", user_id: "admin"}
    │
    ▼
Chat Handler (web mode)
    │
    ▼
Intent Parser ──────────────────────┐
    │                               │
    │ intent: "get_robot_status"    │ LLM Call
    │ entities: {robot_id: "01"}    │
    │                               │
    ▼                               │
Function Executor                   │
    │                               │
    │ query Qdrant                  │
    │ get telemetry                 │
    │                               │
    ▼                               │
Response Generator ─────────────────┘
    │                               │ LLM Call
    │ "Robot 01 is idle at lobby,   │
    │  battery at 85%"              │
    │                               │
    ▼
PostgreSQL (log conversation)
    │
    ▼
Return to Dashboard
```

### Map State Flow (Robot Navigation)

```
Robot requests navigation update
    │
    │ GET /map/state/{robot_id}?floor_id=floor_1
    │
    ▼
Map Handler
    │
    ├── Get floor configuration
    │
    ├── Filter accessible waypoints
    │   (check zone blockages)
    │
    ├── Get active blocked zones
    │
    └── Return navigation state
        │
        ▼
    {
        accessible_waypoints: [...],
        blocked_waypoints: [...],
        blocked_zones: [...],
        map_dimensions: {width, height}
    }
```

## Concurrency Model

The system uses Python's `asyncio` for non-blocking operations:

- FastAPI endpoints are async
- Database operations use async drivers
- LLM calls are awaited (can be slow)
- SSE streaming uses async generators

## Configuration

### Environment Variables

```bash
# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=wayfindr
POSTGRES_USER=wayfindr
POSTGRES_PASSWORD=wayfindr

# Ollama LLM
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.3:70b
```

### Runtime Configuration

Map configuration is stored in `data/map_config.json` and loaded at startup. Changes via API are persisted automatically.

## Scalability Considerations

1. **Horizontal scaling**: FastAPI can run multiple workers
2. **Database scaling**: Qdrant and PostgreSQL can be clustered
3. **LLM scaling**: Ollama can run on dedicated HPC nodes
4. **Caching**: In-memory telemetry cache reduces database hits

## Security Notes

- CORS is currently open (`allow_origins=["*"]`) - restrict in production
- No authentication implemented yet - add for production
- Telemetry endpoint accepts any robot_id - consider validation
