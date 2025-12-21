"""
Qdrant Store - Robot Telemetry Storage
For WayfindR-LLM Tour Guide Robot System

Handles time-series telemetry data (position, battery, sensors, status)
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

# Import config
try:
    from core.config import QDRANT_HOST, QDRANT_PORT, TELEMETRY_COLLECTION
except ImportError:
    QDRANT_HOST = "localhost"
    QDRANT_PORT = 6333
    TELEMETRY_COLLECTION = "robot_telemetry"

VECTOR_DIM = 384  # MiniLM embedding size

# Initialize
model = SentenceTransformer("all-MiniLM-L6-v2")
qdrant_client = None


def init_qdrant(retries=5, delay=2):
    """Initialize Qdrant client and collections"""
    global qdrant_client

    for attempt in range(retries):
        try:
            qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

            # Create Telemetry collection if not exists
            try:
                qdrant_client.get_collection(TELEMETRY_COLLECTION)
                print(f"[Qdrant] Connected to collection '{TELEMETRY_COLLECTION}'")
            except:
                qdrant_client.create_collection(
                    collection_name=TELEMETRY_COLLECTION,
                    vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
                )
                print(f"[Qdrant] Created collection '{TELEMETRY_COLLECTION}'")

            return True

        except Exception as e:
            print(f"[Qdrant] Waiting for Qdrant... ({attempt + 1}/{retries}): {e}")
            time.sleep(delay)

    print("[Qdrant] Failed to connect after multiple attempts")
    return False


def _normalize_timestamp(ts: Any) -> str:
    """Normalize timestamp to ISO format string"""
    if isinstance(ts, str):
        return ts if ts else datetime.now().isoformat()
    elif isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts).isoformat()
        except:
            return datetime.now().isoformat()
    elif isinstance(ts, datetime):
        return ts.isoformat()
    else:
        return datetime.now().isoformat()


def add_telemetry(robot_id: str, telemetry: Dict[str, Any]) -> Optional[str]:
    """
    Add robot telemetry to Qdrant

    Args:
        robot_id: Robot identifier (e.g., "robot_01")
        telemetry: Dictionary with:
            - position: {x, y} or current location name
            - battery: Battery percentage
            - status: "idle" | "navigating" | "stuck" | "charging"
            - current_location: Current waypoint/area
            - destination: Target waypoint (if navigating)
            - sensors: Sensor readings (lidar, ultrasonic, etc.)
            - timestamp: ISO format timestamp

    Returns:
        Point ID if successful, None otherwise
    """
    if not qdrant_client:
        print("[Qdrant] Client not initialized")
        return None

    try:
        # Create searchable text summary
        status = telemetry.get('status', 'unknown')
        battery = telemetry.get('battery', 0)
        location = telemetry.get('current_location', 'unknown')
        destination = telemetry.get('destination', '')

        text = f"Robot {robot_id} at {location} - Status: {status}, Battery: {battery}%"
        if destination:
            text += f", navigating to {destination}"

        # Generate embedding
        embedding = model.encode([text])[0].tolist()

        # Create point ID
        point_id = str(uuid.uuid4())

        # Normalize timestamp
        timestamp = _normalize_timestamp(telemetry.get('timestamp', datetime.now()))

        # Prepare payload
        payload = {
            "robot_id": robot_id,
            "timestamp": timestamp,
            "text": text,
            "status": status,
            "battery": battery,
            "current_location": location,
            "destination": destination,
            **{k: v for k, v in telemetry.items()
               if k not in ['timestamp', 'status', 'battery', 'current_location', 'destination']}
        }

        # Insert into Qdrant
        qdrant_client.upsert(
            collection_name=TELEMETRY_COLLECTION,
            points=[PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            )]
        )

        return point_id

    except Exception as e:
        print(f"[Qdrant] Error adding telemetry: {e}")
        return None


def get_robot_telemetry_history(robot_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent telemetry for a robot

    Args:
        robot_id: Robot identifier
        limit: Number of recent entries to retrieve

    Returns:
        List of telemetry records, newest first
    """
    if not qdrant_client:
        print("[Qdrant] Client not initialized")
        return []

    try:
        results = qdrant_client.scroll(
            collection_name=TELEMETRY_COLLECTION,
            scroll_filter={
                "must": [
                    {
                        "key": "robot_id",
                        "match": {"value": robot_id}
                    }
                ]
            },
            limit=limit * 2,
            with_payload=True,
            with_vectors=False
        )[0]

        # Normalize timestamps
        for point in results:
            if 'timestamp' in point.payload:
                point.payload['timestamp'] = _normalize_timestamp(point.payload['timestamp'])

        # Sort by timestamp (newest first)
        try:
            sorted_results = sorted(
                results,
                key=lambda x: x.payload.get('timestamp', ''),
                reverse=True
            )[:limit]
        except:
            sorted_results = results[:limit]

        return [point.payload for point in sorted_results]

    except Exception as e:
        print(f"[Qdrant] Error retrieving telemetry history: {e}")
        return []


def get_all_robots(limit: int = 50) -> List[str]:
    """
    Get list of all known robot IDs from telemetry

    Returns:
        List of unique robot IDs
    """
    if not qdrant_client:
        return []

    try:
        results = qdrant_client.scroll(
            collection_name=TELEMETRY_COLLECTION,
            limit=limit * 10,  # Get more to find unique robots
            with_payload=True,
            with_vectors=False
        )[0]

        robot_ids = set()
        for point in results:
            robot_id = point.payload.get('robot_id')
            if robot_id:
                robot_ids.add(robot_id)

        return list(robot_ids)[:limit]

    except Exception as e:
        print(f"[Qdrant] Error getting robot list: {e}")
        return []


def get_latest_telemetry(robot_id: str = None) -> Dict[str, Any]:
    """
    Get latest telemetry for a robot or all robots

    Args:
        robot_id: Optional robot filter. If None, returns latest for all robots.

    Returns:
        Dictionary of robot_id -> latest telemetry
    """
    if not qdrant_client:
        return {}

    try:
        scroll_filter = None
        if robot_id:
            scroll_filter = {
                "must": [{"key": "robot_id", "match": {"value": robot_id}}]
            }

        results = qdrant_client.scroll(
            collection_name=TELEMETRY_COLLECTION,
            scroll_filter=scroll_filter,
            limit=500,
            with_payload=True,
            with_vectors=False
        )[0]

        # Group by robot_id and get latest for each
        latest = {}
        for point in results:
            payload = point.payload
            rid = payload.get('robot_id')
            if not rid:
                continue

            ts = _normalize_timestamp(payload.get('timestamp', ''))

            if rid not in latest or ts > latest[rid].get('timestamp', ''):
                latest[rid] = payload

        return latest

    except Exception as e:
        print(f"[Qdrant] Error getting latest telemetry: {e}")
        return {}


def search_telemetry(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Semantic search through telemetry data

    Args:
        query: Search query (e.g., "robots with low battery")
        limit: Number of results

    Returns:
        List of matching telemetry records with scores
    """
    if not qdrant_client:
        return []

    try:
        query_vector = model.encode([query])[0].tolist()

        results = qdrant_client.query_points(
            collection_name=TELEMETRY_COLLECTION,
            query=query_vector,
            limit=limit,
            with_payload=True
        )

        return [
            {
                **hit.payload,
                'score': hit.score
            }
            for hit in results.points
        ]

    except Exception as e:
        print(f"[Qdrant] Error searching telemetry: {e}")
        return []


def clear_collection():
    """Clear all telemetry data"""
    if not qdrant_client:
        return

    try:
        qdrant_client.delete_collection(TELEMETRY_COLLECTION)
        print("[Qdrant] Collection cleared")
        init_qdrant()
    except Exception as e:
        print(f"[Qdrant] Error clearing collection: {e}")


# Initialize on import
init_qdrant()

__all__ = [
    'init_qdrant',
    'add_telemetry',
    'get_robot_telemetry_history',
    'get_all_robots',
    'get_latest_telemetry',
    'search_telemetry',
    'clear_collection'
]
