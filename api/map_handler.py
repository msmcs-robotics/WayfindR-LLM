"""
Map and Zone API Handler for WayfindR-LLM
Provides endpoints for map viewing, zone management, and live updates
"""
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import map manager
try:
    from core.map_config import (
        get_map_manager,
        ZoneType,
        WaypointType,
        Waypoint,
        Zone,
        Coordinate,
        FloorMap
    )
    MAP_AVAILABLE = True
except ImportError as e:
    print(f"[MAP API] Map config not available: {e}")
    MAP_AVAILABLE = False
    get_map_manager = None


# =============================================================================
# FLOOR ENDPOINTS
# =============================================================================

async def get_floors() -> Dict[str, Any]:
    """Get all floors in the building"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        floors = manager.get_all_floors()
        return {
            "success": True,
            "floors": floors,
            "count": len(floors)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_floor_details(floor_id: str) -> Dict[str, Any]:
    """Get detailed floor information including waypoints and zones"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        floor = manager.get_floor(floor_id)

        if not floor:
            return {"success": False, "error": f"Floor '{floor_id}' not found"}

        return {
            "success": True,
            "floor": floor.to_dict()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# WAYPOINT ENDPOINTS
# =============================================================================

async def get_waypoints(floor_id: str = None, accessible_only: bool = True) -> Dict[str, Any]:
    """Get all waypoints"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        waypoints = manager.get_all_waypoints(floor_id, accessible_only)
        return {
            "success": True,
            "waypoints": waypoints,
            "count": len(waypoints)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_waypoint(waypoint_id: str) -> Dict[str, Any]:
    """Get a specific waypoint"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        waypoint = manager.get_waypoint(waypoint_id)

        if not waypoint:
            return {"success": False, "error": f"Waypoint '{waypoint_id}' not found"}

        return {
            "success": True,
            "waypoint": waypoint.to_dict()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_waypoint(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new waypoint"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        required = ["id", "name", "floor_id", "x", "y"]
        for field in required:
            if field not in data:
                return {"success": False, "error": f"Missing required field: {field}"}

        waypoint = Waypoint(
            id=data["id"],
            name=data["name"],
            floor_id=data["floor_id"],
            position=Coordinate(data["x"], data["y"]),
            waypoint_type=WaypointType(data.get("waypoint_type", "destination")),
            description=data.get("description", ""),
            accessible=data.get("accessible", True),
            connections=data.get("connections", [])
        )

        manager = get_map_manager()
        if manager.add_waypoint(waypoint):
            return {
                "success": True,
                "message": f"Waypoint '{waypoint.name}' created",
                "waypoint": waypoint.to_dict()
            }
        else:
            return {"success": False, "error": "Failed to create waypoint (may already exist)"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def update_waypoint(waypoint_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a waypoint"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()

        # Handle position update
        if "x" in updates and "y" in updates:
            updates["position"] = Coordinate(updates.pop("x"), updates.pop("y"))

        if manager.update_waypoint(waypoint_id, updates):
            waypoint = manager.get_waypoint(waypoint_id)
            return {
                "success": True,
                "message": f"Waypoint '{waypoint_id}' updated",
                "waypoint": waypoint.to_dict() if waypoint else None
            }
        else:
            return {"success": False, "error": f"Waypoint '{waypoint_id}' not found"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def delete_waypoint(waypoint_id: str) -> Dict[str, Any]:
    """Delete a waypoint"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        if manager.delete_waypoint(waypoint_id):
            return {"success": True, "message": f"Waypoint '{waypoint_id}' deleted"}
        else:
            return {"success": False, "error": f"Waypoint '{waypoint_id}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def block_waypoint(waypoint_id: str, reason: str = "Blocked by operator") -> Dict[str, Any]:
    """Block a waypoint (make it inaccessible)"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        if manager.set_waypoint_accessible(waypoint_id, False, reason):
            return {
                "success": True,
                "message": f"Waypoint '{waypoint_id}' blocked: {reason}"
            }
        else:
            return {"success": False, "error": f"Waypoint '{waypoint_id}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def unblock_waypoint(waypoint_id: str) -> Dict[str, Any]:
    """Unblock a waypoint"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        if manager.set_waypoint_accessible(waypoint_id, True):
            return {
                "success": True,
                "message": f"Waypoint '{waypoint_id}' unblocked"
            }
        else:
            return {"success": False, "error": f"Waypoint '{waypoint_id}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# ZONE ENDPOINTS
# =============================================================================

async def get_zones(floor_id: str = None, active_only: bool = True, zone_type: str = None) -> Dict[str, Any]:
    """Get all zones"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        zt = ZoneType(zone_type) if zone_type else None
        zones = manager.get_all_zones(floor_id, active_only, zt)
        return {
            "success": True,
            "zones": zones,
            "count": len(zones)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_blocked_zones(floor_id: str = None) -> Dict[str, Any]:
    """Get all active blocked zones"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        zones = manager.get_blocked_zones(floor_id)
        return {
            "success": True,
            "blocked_zones": zones,
            "count": len(zones)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_zone(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new zone"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        required = ["name", "floor_id", "zone_type", "polygon"]
        for field in required:
            if field not in data:
                return {"success": False, "error": f"Missing required field: {field}"}

        # Parse polygon
        polygon = []
        for point in data["polygon"]:
            if isinstance(point, dict):
                polygon.append(Coordinate(point["x"], point["y"]))
            elif isinstance(point, (list, tuple)):
                polygon.append(Coordinate(point[0], point[1]))

        import uuid
        zone = Zone(
            id=data.get("id", f"{data['zone_type']}_{uuid.uuid4().hex[:8]}"),
            name=data["name"],
            floor_id=data["floor_id"],
            zone_type=ZoneType(data["zone_type"]),
            polygon=polygon,
            reason=data.get("reason", ""),
            expires_at=data.get("expires_at")
        )

        manager = get_map_manager()
        if manager.add_zone(zone):
            return {
                "success": True,
                "message": f"Zone '{zone.name}' created",
                "zone": zone.to_dict()
            }
        else:
            return {"success": False, "error": "Failed to create zone"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_blocked_zone(
    name: str,
    floor_id: str,
    polygon: List[Dict[str, float]],
    reason: str = "",
    expires_at: str = None
) -> Dict[str, Any]:
    """Quick helper to create a blocked zone"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        polygon_tuples = [(p["x"], p["y"]) for p in polygon]
        zone = manager.create_blocked_zone(name, floor_id, polygon_tuples, reason, expires_at)

        if zone:
            return {
                "success": True,
                "message": f"Blocked zone '{name}' created",
                "zone": zone.to_dict()
            }
        else:
            return {"success": False, "error": "Failed to create blocked zone"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def update_zone(zone_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a zone"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        if manager.update_zone(zone_id, updates):
            zone = manager.get_zone(zone_id)
            return {
                "success": True,
                "message": f"Zone '{zone_id}' updated",
                "zone": zone.to_dict() if zone else None
            }
        else:
            return {"success": False, "error": f"Zone '{zone_id}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def delete_zone(zone_id: str) -> Dict[str, Any]:
    """Delete a zone"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        if manager.delete_zone(zone_id):
            return {"success": True, "message": f"Zone '{zone_id}' deleted"}
        else:
            return {"success": False, "error": f"Zone '{zone_id}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def activate_zone(zone_id: str) -> Dict[str, Any]:
    """Activate a zone"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        if manager.activate_zone(zone_id):
            return {"success": True, "message": f"Zone '{zone_id}' activated"}
        else:
            return {"success": False, "error": f"Zone '{zone_id}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def deactivate_zone(zone_id: str) -> Dict[str, Any]:
    """Deactivate a zone"""
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()
        if manager.deactivate_zone(zone_id):
            return {"success": True, "message": f"Zone '{zone_id}' deactivated"}
        else:
            return {"success": False, "error": f"Zone '{zone_id}' not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# MAP STATE FOR ROBOTS
# =============================================================================

async def get_map_state_for_robot(robot_id: str, floor_id: str = None) -> Dict[str, Any]:
    """
    Get current map state for a robot

    This is what robots should query to understand the current map:
    - Active blocked zones
    - Accessible waypoints
    - Current route restrictions
    """
    if not MAP_AVAILABLE:
        return {"success": False, "error": "Map system not available"}

    try:
        manager = get_map_manager()

        # Default to first floor if not specified
        if not floor_id:
            floors = manager.get_all_floors()
            floor_id = floors[0]["id"] if floors else None

        if not floor_id:
            return {"success": False, "error": "No floors configured"}

        floor = manager.get_floor(floor_id)
        if not floor:
            return {"success": False, "error": f"Floor '{floor_id}' not found"}

        # Get accessible waypoints
        accessible_waypoints = []
        blocked_waypoints = []
        for wp in floor.waypoints.values():
            if wp.accessible and not manager.is_point_in_blocked_zone(wp.position.x, wp.position.y, floor_id):
                accessible_waypoints.append({
                    "id": wp.id,
                    "name": wp.name,
                    "position": wp.position.to_dict(),
                    "type": wp.waypoint_type.value,
                    "connections": wp.connections
                })
            else:
                blocked_waypoints.append(wp.id)

        # Get blocked zones
        blocked_zones = manager.get_blocked_zones(floor_id)

        return {
            "success": True,
            "robot_id": robot_id,
            "floor_id": floor_id,
            "floor_name": floor.name,
            "timestamp": datetime.now().isoformat(),
            "accessible_waypoints": accessible_waypoints,
            "blocked_waypoints": blocked_waypoints,
            "blocked_zones": blocked_zones,
            "map_dimensions": {
                "width": floor.width,
                "height": floor.height
            }
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# MAP IMAGE CONFIGURATION
# =============================================================================

async def get_map_image_config(map_name: str = "first_map") -> Dict[str, Any]:
    """
    Get the map image configuration for displaying in the browser

    Returns:
    - image_url: Path to the PNG map image
    - resolution: Meters per pixel (from ROS2 map YAML)
    - origin: [x, y, theta] origin in world coordinates
    - dimensions: Pixel dimensions of the image
    """
    import os
    import yaml

    try:
        # Look for map files in static/maps directory
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        maps_dir = os.path.join(base_path, "static", "maps")
        yaml_path = os.path.join(maps_dir, f"{map_name}.yaml")
        png_path = os.path.join(maps_dir, f"{map_name}.png")

        if not os.path.exists(yaml_path):
            return {"success": False, "error": f"Map '{map_name}' not found"}

        # Read map YAML
        with open(yaml_path, 'r') as f:
            map_yaml = yaml.safe_load(f)

        # Get image dimensions if PNG exists
        width, height = 0, 0
        if os.path.exists(png_path):
            try:
                from PIL import Image
                with Image.open(png_path) as img:
                    width, height = img.size
            except ImportError:
                # PIL not available, estimate from file
                pass

        return {
            "success": True,
            "map_name": map_name,
            "image_url": f"/static/maps/{map_name}.png",
            "resolution": map_yaml.get("resolution", 0.05),  # meters per pixel
            "origin": map_yaml.get("origin", [0, 0, 0]),  # [x, y, theta] in meters
            "occupied_thresh": map_yaml.get("occupied_thresh", 0.65),
            "free_thresh": map_yaml.get("free_thresh", 0.25),
            "negate": map_yaml.get("negate", 0),
            "image_width": width,
            "image_height": height
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def list_available_maps() -> Dict[str, Any]:
    """List all available map files"""
    import os
    import glob

    try:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        maps_dir = os.path.join(base_path, "static", "maps")

        if not os.path.exists(maps_dir):
            return {"success": True, "maps": [], "count": 0}

        # Find all YAML files (each YAML represents a map)
        yaml_files = glob.glob(os.path.join(maps_dir, "*.yaml"))
        maps = []

        for yaml_file in yaml_files:
            map_name = os.path.splitext(os.path.basename(yaml_file))[0]
            png_exists = os.path.exists(os.path.join(maps_dir, f"{map_name}.png"))
            maps.append({
                "name": map_name,
                "yaml_file": f"{map_name}.yaml",
                "image_available": png_exists
            })

        return {
            "success": True,
            "maps": maps,
            "count": len(maps)
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


__all__ = [
    'get_floors',
    'get_floor_details',
    'get_waypoints',
    'get_waypoint',
    'create_waypoint',
    'update_waypoint',
    'delete_waypoint',
    'block_waypoint',
    'unblock_waypoint',
    'get_zones',
    'get_blocked_zones',
    'create_zone',
    'create_blocked_zone',
    'update_zone',
    'delete_zone',
    'activate_zone',
    'deactivate_zone',
    'get_map_state_for_robot',
    'get_map_image_config',
    'list_available_maps'
]
