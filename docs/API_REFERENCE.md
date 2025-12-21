# WayfindR-LLM API Reference

## Base URL

```
http://localhost:8000
```

## Authentication

Currently no authentication required. Plan to add API keys or JWT tokens for production.

---

## Chat Endpoints

### POST /chat

Operator console chat endpoint. Used by the web dashboard for fleet management.

**Request:**
```json
{
    "message": "What is the status of robot_01?",
    "user_id": "operator_001"
}
```

**Response:**
```json
{
    "success": true,
    "response": "Robot 01 is currently idle at the lobby. Battery level is at 85%. Last telemetry received 30 seconds ago.",
    "intent": "get_robot_status",
    "context": {
        "robot_id": "robot_01",
        "battery": 85,
        "status": "idle"
    }
}
```

---

### POST /robot_chat

Visitor chat endpoint. Used by Android tablets on robots.

**Request:**
```json
{
    "message": "Where is the cafeteria?",
    "robot_id": "robot_01",
    "user_id": "visitor_123"
}
```

**Response:**
```json
{
    "success": true,
    "response": "The cafeteria is located on Floor 2. I can guide you there! Would you like me to take you?",
    "intent": "get_directions",
    "suggested_destination": "cafeteria"
}
```

---

## Telemetry Endpoints

### POST /telemetry

Receive telemetry from robots. Robots self-register by sending telemetry.

**Request:**
```json
{
    "robot_id": "robot_01",
    "telemetry": {
        "battery": 85,
        "status": "idle",
        "current_location": "lobby",
        "destination": null,
        "floor_id": "floor_1",
        "position": {
            "x": 150.5,
            "y": 200.3
        },
        "sensors": {
            "imu": {
                "pitch": 0.5,
                "roll": -0.2,
                "yaw": 45.0
            },
            "lidar": {
                "front": 2.5,
                "left": 1.8,
                "right": 3.2
            },
            "temperature": 42.5
        }
    }
}
```

**Response:**
```json
{
    "success": true,
    "message": "Telemetry received for robot_01"
}
```

---

### GET /telemetry/status

Get current status of all robots or a specific robot.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| robot_id | string | No | Filter by specific robot |

**Response:**
```json
{
    "success": true,
    "robots": {
        "robot_01": {
            "status": "idle",
            "battery": 85,
            "current_location": "lobby",
            "last_update": "2024-01-15T10:30:00"
        },
        "robot_02": {
            "status": "navigating",
            "battery": 72,
            "current_location": "hallway_a",
            "destination": "room_101",
            "last_update": "2024-01-15T10:29:45"
        }
    }
}
```

---

### GET /telemetry/history/{robot_id}

Get telemetry history for a specific robot.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| robot_id | string | Yes | Robot identifier |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | integer | 10 | Max records to return |

**Response:**
```json
{
    "success": true,
    "robot_id": "robot_01",
    "history": [
        {
            "timestamp": "2024-01-15T10:30:00",
            "battery": 85,
            "status": "idle",
            "current_location": "lobby"
        },
        {
            "timestamp": "2024-01-15T10:25:00",
            "battery": 86,
            "status": "navigating",
            "current_location": "hallway_b"
        }
    ]
}
```

---

## Robot Monitoring Endpoints

### GET /robots

List all registered robots in the system.

**Response:**
```json
{
    "success": true,
    "count": 2,
    "robots": [
        {
            "robot_id": "robot_01",
            "status": "idle",
            "battery": 85,
            "location": "lobby",
            "last_seen": "2024-01-15T10:30:00"
        },
        {
            "robot_id": "robot_02",
            "status": "navigating",
            "battery": 72,
            "location": "hallway_a",
            "last_seen": "2024-01-15T10:29:45"
        }
    ]
}
```

---

### GET /robots/{robot_id}

Get detailed information for a specific robot.

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| robot_id | string | Yes | Robot identifier |

**Response:**
```json
{
    "success": true,
    "robot_id": "robot_01",
    "current": {
        "status": "idle",
        "battery": 85,
        "location": "lobby",
        "destination": null,
        "last_update": "2024-01-15T10:30:00"
    },
    "recent_history": [
        {
            "timestamp": "2024-01-15T10:30:00",
            "status": "idle",
            "battery": 85,
            "current_location": "lobby"
        }
    ]
}
```

---

## Map & Zone Endpoints

### GET /map/floors

List all floors in the building.

**Response:**
```json
{
    "success": true,
    "count": 3,
    "floors": [
        {
            "id": "floor_1",
            "name": "Ground Floor",
            "level": 1,
            "width": 1000,
            "height": 800
        },
        {
            "id": "floor_2",
            "name": "Second Floor",
            "level": 2,
            "width": 1000,
            "height": 800
        }
    ]
}
```

---

### GET /map/floors/{floor_id}

Get detailed information for a specific floor including all waypoints and zones.

**Response:**
```json
{
    "success": true,
    "floor": {
        "id": "floor_1",
        "name": "Ground Floor",
        "level": 1,
        "width": 1000,
        "height": 800,
        "waypoints": [...],
        "zones": [...]
    }
}
```

---

### GET /map/waypoints

Get all waypoints.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| floor_id | string | null | Filter by floor |
| accessible_only | boolean | true | Only return accessible waypoints |

**Response:**
```json
{
    "success": true,
    "count": 10,
    "waypoints": [
        {
            "id": "lobby",
            "name": "Main Lobby",
            "floor_id": "floor_1",
            "position": {"x": 100, "y": 200},
            "waypoint_type": "destination",
            "accessible": true,
            "connections": ["hallway_a", "reception"]
        }
    ]
}
```

---

### GET /map/waypoints/{waypoint_id}

Get a specific waypoint.

**Response:**
```json
{
    "success": true,
    "waypoint": {
        "id": "lobby",
        "name": "Main Lobby",
        "floor_id": "floor_1",
        "position": {"x": 100, "y": 200},
        "waypoint_type": "destination",
        "description": "Main building entrance",
        "accessible": true,
        "connections": ["hallway_a", "reception"]
    }
}
```

---

### POST /map/waypoints

Create a new waypoint.

**Request:**
```json
{
    "id": "new_waypoint",
    "name": "Conference Room A",
    "floor_id": "floor_1",
    "x": 300,
    "y": 400,
    "waypoint_type": "destination",
    "description": "Large conference room",
    "connections": ["hallway_b"]
}
```

**Response:**
```json
{
    "success": true,
    "message": "Waypoint 'Conference Room A' created",
    "waypoint": {...}
}
```

---

### PUT /map/waypoints/{waypoint_id}

Update a waypoint.

**Request:**
```json
{
    "name": "Updated Name",
    "accessible": false
}
```

**Response:**
```json
{
    "success": true,
    "message": "Waypoint 'waypoint_id' updated",
    "waypoint": {...}
}
```

---

### DELETE /map/waypoints/{waypoint_id}

Delete a waypoint.

**Response:**
```json
{
    "success": true,
    "message": "Waypoint 'waypoint_id' deleted"
}
```

---

### POST /map/waypoints/{waypoint_id}/block

Block a waypoint (make inaccessible).

**Request:**
```json
{
    "reason": "Under maintenance"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Waypoint 'waypoint_id' blocked: Under maintenance"
}
```

---

### POST /map/waypoints/{waypoint_id}/unblock

Unblock a waypoint.

**Response:**
```json
{
    "success": true,
    "message": "Waypoint 'waypoint_id' unblocked"
}
```

---

### GET /map/zones

Get all zones.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| floor_id | string | null | Filter by floor |
| active_only | boolean | true | Only return active zones |
| zone_type | string | null | Filter by type (blocked, priority, slow, restricted) |

**Response:**
```json
{
    "success": true,
    "count": 3,
    "zones": [
        {
            "id": "blocked_001",
            "name": "Maintenance Area",
            "floor_id": "floor_1",
            "zone_type": "blocked",
            "polygon": [
                {"x": 100, "y": 100},
                {"x": 200, "y": 100},
                {"x": 200, "y": 200},
                {"x": 100, "y": 200}
            ],
            "active": true,
            "reason": "Floor cleaning in progress",
            "expires_at": "2024-01-15T12:00:00"
        }
    ]
}
```

---

### GET /map/zones/blocked

Get all active blocked zones (shortcut).

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| floor_id | string | null | Filter by floor |

**Response:**
```json
{
    "success": true,
    "count": 1,
    "blocked_zones": [...]
}
```

---

### POST /map/zones

Create a new zone.

**Request:**
```json
{
    "name": "Construction Zone",
    "floor_id": "floor_1",
    "zone_type": "blocked",
    "polygon": [
        {"x": 100, "y": 100},
        {"x": 200, "y": 100},
        {"x": 200, "y": 200},
        {"x": 100, "y": 200}
    ],
    "reason": "Building renovation",
    "expires_at": "2024-01-20T18:00:00"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Zone 'Construction Zone' created",
    "zone": {...}
}
```

---

### POST /map/zones/blocked

Quick helper to create a blocked zone.

**Request:**
```json
{
    "name": "Temporary Blockade",
    "floor_id": "floor_1",
    "polygon": [
        {"x": 100, "y": 100},
        {"x": 200, "y": 100},
        {"x": 200, "y": 200},
        {"x": 100, "y": 200}
    ],
    "reason": "Wet floor",
    "expires_at": "2024-01-15T14:00:00"
}
```

---

### PUT /map/zones/{zone_id}

Update a zone.

**Request:**
```json
{
    "name": "Updated Zone Name",
    "reason": "Updated reason"
}
```

---

### DELETE /map/zones/{zone_id}

Delete a zone.

---

### POST /map/zones/{zone_id}/activate

Activate a zone.

---

### POST /map/zones/{zone_id}/deactivate

Deactivate a zone (keeps it in the system but inactive).

---

### GET /map/state/{robot_id}

Get current map state for robot navigation. This is what robots should query to understand accessible areas.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| floor_id | string | null | Floor to get state for (defaults to first floor) |

**Response:**
```json
{
    "success": true,
    "robot_id": "robot_01",
    "floor_id": "floor_1",
    "floor_name": "Ground Floor",
    "timestamp": "2024-01-15T10:30:00",
    "accessible_waypoints": [
        {
            "id": "lobby",
            "name": "Main Lobby",
            "position": {"x": 100, "y": 200},
            "type": "destination",
            "connections": ["hallway_a", "reception"]
        }
    ],
    "blocked_waypoints": ["maintenance_room"],
    "blocked_zones": [
        {
            "id": "blocked_001",
            "name": "Cleaning Area",
            "polygon": [...],
            "reason": "Floor cleaning"
        }
    ],
    "map_dimensions": {
        "width": 1000,
        "height": 800
    }
}
```

---

## Streaming Endpoints

### GET /stream/postgresql

Server-Sent Events stream of PostgreSQL logs (conversation history).

**Response:** SSE stream

```
event: message
data: {"timestamp": "...", "robot_id": "...", "message": "..."}

event: message
data: {"timestamp": "...", "robot_id": "...", "message": "..."}
```

---

### GET /stream/qdrant

Server-Sent Events stream of Qdrant telemetry updates.

**Response:** SSE stream

```
event: telemetry
data: {"robot_id": "robot_01", "battery": 85, "status": "idle"}
```

---

## Data Endpoints

### GET /data/postgresql

Get recent PostgreSQL logs (non-streaming).

---

### GET /data/qdrant

Get recent Qdrant telemetry (non-streaming).

---

## Health Check

### GET /health

Check system health.

**Response:**
```json
{
    "mcp_server": "online",
    "llm": "ready",
    "qdrant": "available",
    "postgresql": "available",
    "active_robots": 2,
    "timestamp": "2024-01-15T10:30:00"
}
```

---

## Error Responses

All endpoints return consistent error format:

```json
{
    "success": false,
    "error": "Error message description"
}
```

Common HTTP status codes:
- `200` - Success
- `400` - Bad request (invalid parameters)
- `404` - Resource not found
- `500` - Internal server error
