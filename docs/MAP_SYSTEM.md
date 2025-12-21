# Map & Zone System

## Overview

The WayfindR-LLM map system provides:

- **Multi-floor building support**
- **Waypoint management** (navigation destinations)
- **Zone management** (blocked areas, priority paths, etc.)
- **Live map monitoring** via web interface
- **Real-time zone updates** for robot navigation

## Data Model

### Floors

Each floor represents a level in the building:

```python
@dataclass
class FloorMap:
    id: str              # Unique identifier (e.g., "floor_1")
    name: str            # Display name (e.g., "Ground Floor")
    level: int           # Floor level number
    width: float         # Map width in units
    height: float        # Map height in units
    image_path: str      # Optional floor plan image
    waypoints: Dict[str, Waypoint]
    zones: Dict[str, Zone]
```

### Waypoints

Waypoints are navigation destinations:

```python
@dataclass
class Waypoint:
    id: str                      # Unique identifier
    name: str                    # Display name
    floor_id: str                # Parent floor
    position: Coordinate         # X, Y position
    waypoint_type: WaypointType  # Type of waypoint
    description: str             # Optional description
    accessible: bool             # Whether robots can navigate here
    connections: List[str]       # Connected waypoint IDs (for pathfinding)
```

**Waypoint Types:**

| Type | Description |
|------|-------------|
| `destination` | General navigation destination |
| `charging` | Charging station |
| `elevator` | Elevator access point |
| `stairs` | Stairway access point |
| `entrance` | Building entrance |
| `junction` | Pathfinding node (not a destination) |

### Zones

Zones define areas with special properties:

```python
@dataclass
class Zone:
    id: str                     # Unique identifier
    name: str                   # Display name
    floor_id: str               # Parent floor
    zone_type: ZoneType         # Type of zone
    polygon: List[Coordinate]   # Polygon vertices
    active: bool                # Whether zone is active
    reason: str                 # Why zone exists
    created_at: datetime
    expires_at: Optional[datetime]  # Auto-expiration
```

**Zone Types:**

| Type | Description | Robot Behavior |
|------|-------------|----------------|
| `blocked` | No-go zone | Avoid completely |
| `priority` | Preferred path | Higher navigation weight |
| `slow` | Speed limit area | Reduce speed |
| `restricted` | Authorized only | Check permissions |

## Map Manager

The `MapManager` class provides a singleton interface for map operations:

```python
from core.map_config import get_map_manager

manager = get_map_manager()

# Get all floors
floors = manager.get_all_floors()

# Get waypoints for a floor
waypoints = manager.get_all_waypoints(floor_id="floor_1")

# Check if point is in blocked zone
is_blocked = manager.is_point_in_blocked_zone(x=150, y=200, floor_id="floor_1")

# Create a blocked zone
zone = manager.create_blocked_zone(
    name="Maintenance Area",
    floor_id="floor_1",
    polygon=[(100, 100), (200, 100), (200, 200), (100, 200)],
    reason="Floor cleaning",
    expires_at="2024-01-15T14:00:00"
)
```

## Live Map Monitoring

### Web Interface

Access the live map at `/map`:

```
http://localhost:8000/map
```

**Features:**

- Floor selector dropdown
- Robot position visualization
- Zone display with color coding
- Click-to-select robots
- Zone drawing tools
- Auto-refresh (3-second intervals)

### Zone Drawing

The map interface allows operators to draw new blocked zones:

1. Click "Add Blocked Zone" button
2. Enter zone name when prompted
3. Click on map to add polygon vertices
4. Double-click to complete polygon
5. Zone is immediately active

### Zone Colors

| Zone Type | Color |
|-----------|-------|
| Blocked | Red (#ef4444, 30% opacity) |
| Priority | Green (#22c55e, 30% opacity) |
| Slow | Yellow (#f59e0b, 30% opacity) |
| Restricted | Purple (#8b5cf6, 30% opacity) |

## Robot Integration

### Querying Map State

Robots should periodically query their navigation state:

```bash
GET /map/state/{robot_id}?floor_id=floor_1
```

**Response:**
```json
{
    "success": true,
    "robot_id": "robot_01",
    "floor_id": "floor_1",
    "accessible_waypoints": [
        {
            "id": "lobby",
            "name": "Main Lobby",
            "position": {"x": 100, "y": 200},
            "connections": ["hallway_a"]
        }
    ],
    "blocked_waypoints": ["maintenance_room"],
    "blocked_zones": [
        {
            "id": "zone_001",
            "polygon": [...]
        }
    ]
}
```

### Navigation Flow

1. Robot sends telemetry with current position
2. Robot queries map state for current floor
3. Robot receives accessible waypoints and blocked zones
4. Robot plans path avoiding blocked areas
5. Repeat periodically (recommended: every 5-10 seconds)

## Zone Expiration

Zones can be set to expire automatically:

```python
zone = manager.create_blocked_zone(
    name="Wet Floor",
    floor_id="floor_1",
    polygon=[(100, 100), (200, 200)],
    reason="Cleaning in progress",
    expires_at="2024-01-15T14:00:00"  # ISO 8601 format
)
```

Expired zones are automatically deactivated. The `MapManager` checks expiration on each query.

## Persistence

Map configuration is automatically persisted to:

```
data/map_config.json
```

Changes made via API are saved immediately. On server restart, configuration is reloaded from this file.

**Structure:**
```json
{
    "floors": {
        "floor_1": {
            "id": "floor_1",
            "name": "Ground Floor",
            "level": 1,
            "waypoints": {...},
            "zones": {...}
        }
    },
    "last_updated": "2024-01-15T10:30:00"
}
```

## Point-in-Polygon Detection

The system uses a ray-casting algorithm to determine if a point is inside a zone polygon:

```python
def is_point_in_blocked_zone(self, x: float, y: float, floor_id: str) -> bool:
    """Check if a coordinate is inside any active blocked zone"""
    floor = self.get_floor(floor_id)
    if not floor:
        return False

    for zone in floor.zones.values():
        if zone.zone_type == ZoneType.BLOCKED and zone.active:
            if zone.contains_point(x, y):
                return True
    return False
```

## Example: Setting Up a Floor

```python
from core.map_config import get_map_manager, Waypoint, Coordinate, WaypointType

manager = get_map_manager()

# Add waypoints
manager.add_waypoint(Waypoint(
    id="lobby",
    name="Main Lobby",
    floor_id="floor_1",
    position=Coordinate(100, 200),
    waypoint_type=WaypointType.ENTRANCE,
    connections=["reception", "hallway_a"]
))

manager.add_waypoint(Waypoint(
    id="reception",
    name="Reception Desk",
    floor_id="floor_1",
    position=Coordinate(150, 250),
    waypoint_type=WaypointType.DESTINATION,
    connections=["lobby"]
))

# Add a blocked zone
manager.create_blocked_zone(
    name="Private Office",
    floor_id="floor_1",
    polygon=[(300, 100), (400, 100), (400, 200), (300, 200)],
    reason="Staff only area"
)
```

## API Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/map/floors` | GET | List all floors |
| `/map/floors/{id}` | GET | Get floor details |
| `/map/waypoints` | GET | List waypoints |
| `/map/waypoints/{id}` | GET/PUT/DELETE | Waypoint CRUD |
| `/map/waypoints` | POST | Create waypoint |
| `/map/waypoints/{id}/block` | POST | Block waypoint |
| `/map/waypoints/{id}/unblock` | POST | Unblock waypoint |
| `/map/zones` | GET | List zones |
| `/map/zones` | POST | Create zone |
| `/map/zones/blocked` | GET/POST | Blocked zones shortcut |
| `/map/zones/{id}` | PUT/DELETE | Zone CRUD |
| `/map/zones/{id}/activate` | POST | Activate zone |
| `/map/zones/{id}/deactivate` | POST | Deactivate zone |
| `/map/state/{robot_id}` | GET | Robot navigation state |

## Future Enhancements

- **Path planning integration**: Use waypoint connections for A* pathfinding
- **Dynamic zone resizing**: Drag handles to resize zones
- **Zone scheduling**: Zones that activate at specific times
- **3D visualization**: Multi-floor 3D view
- **Heat maps**: Robot traffic visualization
- **Collision prediction**: Warn when robots might collide
