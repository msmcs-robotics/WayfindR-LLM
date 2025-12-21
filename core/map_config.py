"""
Map and Zone Configuration for WayfindR-LLM
Handles floor maps, waypoints, zones (blocked/priority), and live updates

This module provides:
- Multi-floor map definitions
- Waypoint management with coordinates
- Zone management (blocked, priority)
- Live zone updates (construction, maintenance)
- Path routing preferences
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class ZoneType(Enum):
    """Types of zones on the map"""
    BLOCKED = "blocked"      # No-go zones (construction, danger)
    PRIORITY = "priority"    # Preferred paths for routing
    SLOW = "slow"            # Areas where robots should slow down
    RESTRICTED = "restricted"  # Authorized access only


class WaypointType(Enum):
    """Types of waypoints"""
    DESTINATION = "destination"  # Places visitors can go
    WAYPOINT = "waypoint"        # Navigation nodes
    CHARGING = "charging"        # Charging stations
    ELEVATOR = "elevator"        # Floor transitions
    ENTRANCE = "entrance"        # Building entrances


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Coordinate:
    """2D coordinate on a floor map"""
    x: float
    y: float

    def to_dict(self) -> Dict:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: Dict) -> "Coordinate":
        return cls(x=data.get("x", 0), y=data.get("y", 0))


@dataclass
class Waypoint:
    """A navigable point on the map"""
    id: str
    name: str
    floor_id: str
    position: Coordinate
    waypoint_type: WaypointType = WaypointType.DESTINATION
    description: str = ""
    accessible: bool = True  # Can be temporarily blocked
    connections: List[str] = field(default_factory=list)  # Connected waypoint IDs

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "floor_id": self.floor_id,
            "position": self.position.to_dict(),
            "waypoint_type": self.waypoint_type.value,
            "description": self.description,
            "accessible": self.accessible,
            "connections": self.connections
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Waypoint":
        return cls(
            id=data["id"],
            name=data["name"],
            floor_id=data["floor_id"],
            position=Coordinate.from_dict(data["position"]),
            waypoint_type=WaypointType(data.get("waypoint_type", "destination")),
            description=data.get("description", ""),
            accessible=data.get("accessible", True),
            connections=data.get("connections", [])
        )


@dataclass
class Zone:
    """A zone on the map (blocked, priority, etc.)"""
    id: str
    name: str
    floor_id: str
    zone_type: ZoneType
    polygon: List[Coordinate]  # Vertices of the zone polygon
    active: bool = True
    reason: str = ""  # Why is this zone set (e.g., "Construction until Dec 25")
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None  # Auto-expire blocked zones

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "floor_id": self.floor_id,
            "zone_type": self.zone_type.value,
            "polygon": [p.to_dict() for p in self.polygon],
            "active": self.active,
            "reason": self.reason,
            "created_at": self.created_at,
            "expires_at": self.expires_at
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Zone":
        return cls(
            id=data["id"],
            name=data["name"],
            floor_id=data["floor_id"],
            zone_type=ZoneType(data["zone_type"]),
            polygon=[Coordinate.from_dict(p) for p in data["polygon"]],
            active=data.get("active", True),
            reason=data.get("reason", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            expires_at=data.get("expires_at")
        )

    def is_expired(self) -> bool:
        """Check if zone has expired"""
        if not self.expires_at:
            return False
        try:
            return datetime.fromisoformat(self.expires_at) < datetime.now()
        except:
            return False


@dataclass
class FloorMap:
    """A floor in the building"""
    id: str
    name: str
    level: int  # Floor number (0 = ground, -1 = basement, etc.)
    image_url: Optional[str] = None  # URL/path to floor plan image
    width: float = 100.0  # Map dimensions (meters or arbitrary units)
    height: float = 100.0
    waypoints: Dict[str, Waypoint] = field(default_factory=dict)
    zones: Dict[str, Zone] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "image_url": self.image_url,
            "width": self.width,
            "height": self.height,
            "waypoints": {k: v.to_dict() for k, v in self.waypoints.items()},
            "zones": {k: v.to_dict() for k, v in self.zones.items()}
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "FloorMap":
        floor = cls(
            id=data["id"],
            name=data["name"],
            level=data.get("level", 0),
            image_url=data.get("image_url"),
            width=data.get("width", 100.0),
            height=data.get("height", 100.0)
        )
        for wp_id, wp_data in data.get("waypoints", {}).items():
            floor.waypoints[wp_id] = Waypoint.from_dict(wp_data)
        for zone_id, zone_data in data.get("zones", {}).items():
            floor.zones[zone_id] = Zone.from_dict(zone_data)
        return floor


# =============================================================================
# MAP MANAGER
# =============================================================================

class MapManager:
    """
    Manages building maps, waypoints, and zones

    Provides live updates for zone management and path routing
    """

    def __init__(self, config_path: str = None):
        self.floors: Dict[str, FloorMap] = {}
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "..", "data", "map_config.json"
        )
        self._load_default_map()

    def _load_default_map(self):
        """Load default building configuration"""
        # Try to load from file first
        if os.path.exists(self.config_path):
            try:
                self.load_from_file(self.config_path)
                return
            except Exception as e:
                print(f"[MAP] Error loading config: {e}, using defaults")

        # Create default single-floor building
        ground_floor = FloorMap(
            id="floor_1",
            name="Ground Floor",
            level=0,
            width=100.0,
            height=80.0
        )

        # Add default waypoints
        default_waypoints = [
            ("reception", "Reception", 10, 10, WaypointType.ENTRANCE),
            ("lobby", "Lobby", 30, 10, WaypointType.WAYPOINT),
            ("cafeteria", "Cafeteria", 70, 10, WaypointType.DESTINATION),
            ("meeting_room_a", "Meeting Room A", 30, 40, WaypointType.DESTINATION),
            ("meeting_room_b", "Meeting Room B", 50, 40, WaypointType.DESTINATION),
            ("conference_hall", "Conference Hall", 70, 40, WaypointType.DESTINATION),
            ("elevator", "Elevator", 50, 70, WaypointType.ELEVATOR),
            ("restroom", "Restroom", 10, 40, WaypointType.DESTINATION),
            ("exit", "Exit", 90, 10, WaypointType.ENTRANCE),
            ("main_hall", "Main Hall", 50, 25, WaypointType.WAYPOINT),
            ("office_wing_a", "Office Wing A", 10, 70, WaypointType.DESTINATION),
            ("office_wing_b", "Office Wing B", 90, 70, WaypointType.DESTINATION),
            ("charging_station", "Charging Station", 5, 75, WaypointType.CHARGING),
        ]

        for wp_id, name, x, y, wp_type in default_waypoints:
            ground_floor.waypoints[wp_id] = Waypoint(
                id=wp_id,
                name=name,
                floor_id="floor_1",
                position=Coordinate(x, y),
                waypoint_type=wp_type
            )

        # Add connections (simplified graph)
        connections = {
            "reception": ["lobby"],
            "lobby": ["reception", "main_hall", "cafeteria"],
            "cafeteria": ["lobby", "exit"],
            "main_hall": ["lobby", "meeting_room_a", "meeting_room_b", "restroom", "elevator"],
            "meeting_room_a": ["main_hall", "meeting_room_b"],
            "meeting_room_b": ["meeting_room_a", "main_hall", "conference_hall"],
            "conference_hall": ["meeting_room_b"],
            "restroom": ["main_hall"],
            "elevator": ["main_hall", "office_wing_a", "office_wing_b"],
            "office_wing_a": ["elevator", "charging_station"],
            "office_wing_b": ["elevator"],
            "exit": ["cafeteria"],
            "charging_station": ["office_wing_a"],
        }

        for wp_id, conns in connections.items():
            if wp_id in ground_floor.waypoints:
                ground_floor.waypoints[wp_id].connections = conns

        self.floors["floor_1"] = ground_floor

    # =========================================================================
    # FLOOR MANAGEMENT
    # =========================================================================

    def get_floor(self, floor_id: str) -> Optional[FloorMap]:
        """Get a floor by ID"""
        return self.floors.get(floor_id)

    def get_all_floors(self) -> List[Dict]:
        """Get all floors (summary)"""
        return [
            {
                "id": f.id,
                "name": f.name,
                "level": f.level,
                "waypoint_count": len(f.waypoints),
                "zone_count": len(f.zones)
            }
            for f in sorted(self.floors.values(), key=lambda x: x.level)
        ]

    def add_floor(self, floor: FloorMap) -> bool:
        """Add a new floor"""
        if floor.id in self.floors:
            return False
        self.floors[floor.id] = floor
        self._save_config()
        return True

    # =========================================================================
    # WAYPOINT MANAGEMENT
    # =========================================================================

    def get_waypoint(self, waypoint_id: str, floor_id: str = None) -> Optional[Waypoint]:
        """Get a waypoint by ID"""
        if floor_id:
            floor = self.floors.get(floor_id)
            return floor.waypoints.get(waypoint_id) if floor else None

        # Search all floors
        for floor in self.floors.values():
            if waypoint_id in floor.waypoints:
                return floor.waypoints[waypoint_id]
        return None

    def get_all_waypoints(self, floor_id: str = None, accessible_only: bool = True) -> List[Dict]:
        """Get all waypoints, optionally filtered"""
        result = []
        floors = [self.floors[floor_id]] if floor_id and floor_id in self.floors else self.floors.values()

        for floor in floors:
            for wp in floor.waypoints.values():
                if accessible_only and not wp.accessible:
                    continue
                result.append(wp.to_dict())

        return result

    def get_destination_waypoints(self, floor_id: str = None) -> List[str]:
        """Get list of destination waypoint names (for navigation)"""
        waypoints = self.get_all_waypoints(floor_id, accessible_only=True)
        return [
            wp["name"] for wp in waypoints
            if wp["waypoint_type"] in ["destination", "entrance", "elevator"]
        ]

    def set_waypoint_accessible(self, waypoint_id: str, accessible: bool, reason: str = "") -> bool:
        """Enable/disable a waypoint (for temporary blocks)"""
        wp = self.get_waypoint(waypoint_id)
        if not wp:
            return False
        wp.accessible = accessible
        self._save_config()
        print(f"[MAP] Waypoint '{waypoint_id}' accessible={accessible}: {reason}")
        return True

    def add_waypoint(self, waypoint: Waypoint) -> bool:
        """Add a new waypoint"""
        floor = self.floors.get(waypoint.floor_id)
        if not floor:
            return False
        if waypoint.id in floor.waypoints:
            return False
        floor.waypoints[waypoint.id] = waypoint
        self._save_config()
        return True

    def update_waypoint(self, waypoint_id: str, updates: Dict) -> bool:
        """Update waypoint properties"""
        wp = self.get_waypoint(waypoint_id)
        if not wp:
            return False

        for key, value in updates.items():
            if hasattr(wp, key):
                setattr(wp, key, value)

        self._save_config()
        return True

    def delete_waypoint(self, waypoint_id: str) -> bool:
        """Delete a waypoint"""
        for floor in self.floors.values():
            if waypoint_id in floor.waypoints:
                del floor.waypoints[waypoint_id]
                # Remove from connections
                for wp in floor.waypoints.values():
                    if waypoint_id in wp.connections:
                        wp.connections.remove(waypoint_id)
                self._save_config()
                return True
        return False

    # =========================================================================
    # ZONE MANAGEMENT
    # =========================================================================

    def get_zone(self, zone_id: str, floor_id: str = None) -> Optional[Zone]:
        """Get a zone by ID"""
        if floor_id:
            floor = self.floors.get(floor_id)
            return floor.zones.get(zone_id) if floor else None

        for floor in self.floors.values():
            if zone_id in floor.zones:
                return floor.zones[zone_id]
        return None

    def get_all_zones(self, floor_id: str = None, active_only: bool = True, zone_type: ZoneType = None) -> List[Dict]:
        """Get all zones, optionally filtered"""
        result = []
        floors = [self.floors[floor_id]] if floor_id and floor_id in self.floors else self.floors.values()

        for floor in floors:
            for zone in floor.zones.values():
                # Skip expired zones
                if zone.is_expired():
                    zone.active = False

                if active_only and not zone.active:
                    continue
                if zone_type and zone.zone_type != zone_type:
                    continue

                result.append(zone.to_dict())

        return result

    def get_blocked_zones(self, floor_id: str = None) -> List[Dict]:
        """Get all active blocked zones"""
        return self.get_all_zones(floor_id, active_only=True, zone_type=ZoneType.BLOCKED)

    def add_zone(self, zone: Zone) -> bool:
        """Add a new zone"""
        floor = self.floors.get(zone.floor_id)
        if not floor:
            return False
        floor.zones[zone.id] = zone
        self._save_config()
        print(f"[MAP] Added {zone.zone_type.value} zone '{zone.name}': {zone.reason}")
        return True

    def create_blocked_zone(
        self,
        name: str,
        floor_id: str,
        polygon: List[Tuple[float, float]],
        reason: str = "",
        expires_at: str = None
    ) -> Optional[Zone]:
        """Quick helper to create a blocked zone"""
        import uuid
        zone = Zone(
            id=f"blocked_{uuid.uuid4().hex[:8]}",
            name=name,
            floor_id=floor_id,
            zone_type=ZoneType.BLOCKED,
            polygon=[Coordinate(x, y) for x, y in polygon],
            reason=reason,
            expires_at=expires_at
        )
        if self.add_zone(zone):
            return zone
        return None

    def update_zone(self, zone_id: str, updates: Dict) -> bool:
        """Update zone properties"""
        zone = self.get_zone(zone_id)
        if not zone:
            return False

        for key, value in updates.items():
            if key == "zone_type" and isinstance(value, str):
                value = ZoneType(value)
            if key == "polygon":
                value = [Coordinate.from_dict(p) if isinstance(p, dict) else p for p in value]
            if hasattr(zone, key):
                setattr(zone, key, value)

        self._save_config()
        return True

    def delete_zone(self, zone_id: str) -> bool:
        """Delete a zone"""
        for floor in self.floors.values():
            if zone_id in floor.zones:
                del floor.zones[zone_id]
                self._save_config()
                return True
        return False

    def deactivate_zone(self, zone_id: str) -> bool:
        """Deactivate a zone (soft delete)"""
        return self.update_zone(zone_id, {"active": False})

    def activate_zone(self, zone_id: str) -> bool:
        """Reactivate a zone"""
        return self.update_zone(zone_id, {"active": True})

    # =========================================================================
    # ROUTING HELPERS
    # =========================================================================

    def is_point_in_blocked_zone(self, x: float, y: float, floor_id: str) -> bool:
        """Check if a point is inside any blocked zone"""
        blocked_zones = self.get_blocked_zones(floor_id)
        for zone in blocked_zones:
            if self._point_in_polygon(x, y, zone["polygon"]):
                return True
        return False

    def _point_in_polygon(self, x: float, y: float, polygon: List[Dict]) -> bool:
        """Ray casting algorithm for point-in-polygon test"""
        n = len(polygon)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]["x"], polygon[i]["y"]
            xj, yj = polygon[j]["x"], polygon[j]["y"]

            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

    def get_accessible_waypoints_for_robot(self, robot_position: Tuple[float, float], floor_id: str) -> List[str]:
        """Get list of waypoints a robot can reach (not blocked)"""
        accessible = []
        floor = self.floors.get(floor_id)
        if not floor:
            return accessible

        for wp in floor.waypoints.values():
            if not wp.accessible:
                continue
            if self.is_point_in_blocked_zone(wp.position.x, wp.position.y, floor_id):
                continue
            accessible.append(wp.id)

        return accessible

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def _save_config(self):
        """Save current configuration to file"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {
                "floors": {fid: f.to_dict() for fid, f in self.floors.items()},
                "updated_at": datetime.now().isoformat()
            }
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[MAP] Error saving config: {e}")

    def load_from_file(self, path: str):
        """Load configuration from file"""
        with open(path, 'r') as f:
            data = json.load(f)

        self.floors = {}
        for floor_id, floor_data in data.get("floors", {}).items():
            self.floors[floor_id] = FloorMap.from_dict(floor_data)

        print(f"[MAP] Loaded {len(self.floors)} floors from {path}")

    def export_config(self) -> Dict:
        """Export current configuration as dict"""
        return {
            "floors": {fid: f.to_dict() for fid, f in self.floors.items()},
            "exported_at": datetime.now().isoformat()
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_map_manager: Optional[MapManager] = None

def get_map_manager() -> MapManager:
    """Get the global MapManager instance"""
    global _map_manager
    if _map_manager is None:
        _map_manager = MapManager()
    return _map_manager


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_waypoint_names() -> List[str]:
    """Get list of all waypoint names (for backwards compatibility)"""
    manager = get_map_manager()
    return manager.get_destination_waypoints()


def is_waypoint_accessible(waypoint_id: str) -> bool:
    """Check if a waypoint is currently accessible"""
    manager = get_map_manager()
    wp = manager.get_waypoint(waypoint_id)
    return wp.accessible if wp else False


def block_waypoint(waypoint_id: str, reason: str = "Blocked by operator") -> bool:
    """Block a waypoint"""
    manager = get_map_manager()
    return manager.set_waypoint_accessible(waypoint_id, False, reason)


def unblock_waypoint(waypoint_id: str) -> bool:
    """Unblock a waypoint"""
    manager = get_map_manager()
    return manager.set_waypoint_accessible(waypoint_id, True)


__all__ = [
    'ZoneType',
    'WaypointType',
    'Coordinate',
    'Waypoint',
    'Zone',
    'FloorMap',
    'MapManager',
    'get_map_manager',
    'get_waypoint_names',
    'is_waypoint_accessible',
    'block_waypoint',
    'unblock_waypoint'
]
