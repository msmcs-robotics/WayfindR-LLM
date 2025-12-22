"""
Qdrant Store - Robot Telemetry Storage
For WayfindR-LLM Tour Guide Robot System

Handles time-series telemetry data (position, battery, sensors, status)
Uses Ollama embeddings via HPC for semantic search capability.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, models
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
import ollama

# Import config
try:
    from core.config import QDRANT_HOST, QDRANT_PORT, TELEMETRY_COLLECTION
except ImportError:
    QDRANT_HOST = "localhost"
    QDRANT_PORT = 6333
    TELEMETRY_COLLECTION = "robot_telemetry"

# Embedding model configuration
# Uses Ollama through SSH tunnel to HPC
OLLAMA_HOST = "http://localhost:11434"
EMBEDDING_MODEL = "all-minilm:l6-v2"
VECTOR_DIM = 384  # all-minilm:l6-v2 produces 384-dimensional embeddings

qdrant_client = None
ollama_client = None
embeddings_available = False


def _init_ollama():
    """Initialize Ollama client for embeddings"""
    global ollama_client, embeddings_available

    try:
        ollama_client = ollama.Client(host=OLLAMA_HOST)

        # Test if embedding model is available
        models_response = ollama_client.list()
        model_names = [m.get('name', m.get('model', '')) for m in models_response.get('models', [])]

        # Check if embedding model exists
        model_found = any(EMBEDDING_MODEL in name or name.startswith('all-minilm') for name in model_names)

        if model_found:
            # Test embedding generation
            test_embed = ollama_client.embeddings(model=EMBEDDING_MODEL, prompt="test")
            if test_embed and 'embedding' in test_embed:
                embeddings_available = True
                print(f"[Qdrant] Ollama embeddings available ({EMBEDDING_MODEL})")
                return True
        else:
            print(f"[Qdrant] Embedding model {EMBEDDING_MODEL} not found")
            print(f"[Qdrant] Available models: {model_names}")
            print(f"[Qdrant] To install: ollama pull {EMBEDDING_MODEL}")

    except Exception as e:
        print(f"[Qdrant] Ollama embeddings not available: {e}")
        print(f"[Qdrant] Falling back to payload-only storage")

    embeddings_available = False
    return False


def _get_embedding(text: str) -> List[float]:
    """
    Get embedding vector for text using Ollama

    Falls back to dummy vector if Ollama is not available
    """
    global embeddings_available

    if embeddings_available and ollama_client:
        try:
            response = ollama_client.embeddings(model=EMBEDDING_MODEL, prompt=text)
            if response and 'embedding' in response:
                return response['embedding']
        except Exception as e:
            print(f"[Qdrant] Embedding failed, using fallback: {e}")
            # Don't disable embeddings for transient errors

    # Fallback: create a simple hash-based vector
    # This allows storage to work even without Ollama
    import hashlib
    hash_bytes = hashlib.sha384(text.encode()).digest()
    return [float(b) / 255.0 for b in hash_bytes[:VECTOR_DIM]]


def init_qdrant(retries=5, delay=2):
    """Initialize Qdrant client and collections"""
    global qdrant_client

    for attempt in range(retries):
        try:
            qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

            # Create Telemetry collection if not exists
            try:
                collection_info = qdrant_client.get_collection(TELEMETRY_COLLECTION)
                # Check if collection has correct vector size
                current_size = collection_info.config.params.vectors.size
                if current_size != VECTOR_DIM:
                    print(f"[Qdrant] Collection vector size mismatch ({current_size} vs {VECTOR_DIM})")
                    print(f"[Qdrant] Recreating collection...")
                    qdrant_client.delete_collection(TELEMETRY_COLLECTION)
                    raise Exception("Recreate collection")
                print(f"[Qdrant] Connected to collection '{TELEMETRY_COLLECTION}'")
            except:
                qdrant_client.create_collection(
                    collection_name=TELEMETRY_COLLECTION,
                    vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
                )
                print(f"[Qdrant] Created collection '{TELEMETRY_COLLECTION}'")

            # Initialize Ollama for embeddings
            _init_ollama()

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
        # Extract key fields
        status = telemetry.get('status', 'unknown')
        battery = telemetry.get('battery', 0)
        location = telemetry.get('current_location', 'unknown')
        destination = telemetry.get('destination', '')

        # Create searchable text summary
        text = f"Robot {robot_id} at {location} - Status: {status}, Battery: {battery}%"
        if destination:
            text += f", navigating to {destination}"

        # Generate embedding via Ollama
        embedding = _get_embedding(text)

        # Create point ID
        point_id = str(uuid.uuid4())

        # Normalize timestamp
        timestamp = _normalize_timestamp(telemetry.get('timestamp', datetime.now()))

        # Prepare payload (store all telemetry data)
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


def search_telemetry(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Semantic search telemetry using Ollama embeddings

    Examples:
        - "robots with low battery" - finds robots with battery issues
        - "stuck robots" - finds robots that are stuck
        - "robots in lobby" - finds robots at specific location
        - "navigating to cafeteria" - finds robots heading somewhere

    Args:
        query: Natural language search query
        limit: Number of results

    Returns:
        List of matching telemetry records, ranked by relevance
    """
    if not qdrant_client:
        return []

    try:
        # Generate query embedding
        query_embedding = _get_embedding(query)

        # Search by vector similarity
        results = qdrant_client.search(
            collection_name=TELEMETRY_COLLECTION,
            query_vector=query_embedding,
            limit=limit,
            with_payload=True
        )

        return [hit.payload for hit in results]

    except Exception as e:
        print(f"[Qdrant] Error searching telemetry: {e}")
        return []


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
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="robot_id",
                        match=models.MatchValue(value=robot_id)
                    )
                ]
            ),
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
            scroll_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="robot_id",
                        match=models.MatchValue(value=robot_id)
                    )
                ]
            )

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


def filter_telemetry(
    robot_id: str = None,
    status: str = None,
    min_battery: int = None,
    max_battery: int = None,
    location: str = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Filter telemetry by various criteria (structured query)

    Args:
        robot_id: Filter by robot ID
        status: Filter by status (idle, navigating, etc.)
        min_battery: Minimum battery percentage
        max_battery: Maximum battery percentage
        location: Filter by location
        limit: Max results

    Returns:
        List of matching telemetry records
    """
    if not qdrant_client:
        return []

    try:
        conditions = []

        if robot_id:
            conditions.append(
                models.FieldCondition(
                    key="robot_id",
                    match=models.MatchValue(value=robot_id)
                )
            )

        if status:
            conditions.append(
                models.FieldCondition(
                    key="status",
                    match=models.MatchValue(value=status)
                )
            )

        if location:
            conditions.append(
                models.FieldCondition(
                    key="current_location",
                    match=models.MatchValue(value=location)
                )
            )

        if min_battery is not None:
            conditions.append(
                models.FieldCondition(
                    key="battery",
                    range=models.Range(gte=min_battery)
                )
            )

        if max_battery is not None:
            conditions.append(
                models.FieldCondition(
                    key="battery",
                    range=models.Range(lte=max_battery)
                )
            )

        scroll_filter = models.Filter(must=conditions) if conditions else None

        results = qdrant_client.scroll(
            collection_name=TELEMETRY_COLLECTION,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )[0]

        return [point.payload for point in results]

    except Exception as e:
        print(f"[Qdrant] Error filtering telemetry: {e}")
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
    'filter_telemetry',
    'search_telemetry',
    'clear_collection',
    'embeddings_available'
]
