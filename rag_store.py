import os
import asyncio
import psycopg2
from psycopg2.extras import Json
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from uuid import uuid4
import nest_asyncio
from datetime import datetime, timedelta
import json
import numpy as np

nest_asyncio.apply()

# ─── CONFIG ────────────────────────────────────────────
VECTOR_DIM = 384
EMBED_MODEL = "all-MiniLM-L6-v2"
QDRANT_COLLECTION = "telemetry_data"
CHAT_COLLECTION = "chat_context"

DB_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

qdrant_client = QdrantClient(host="localhost", port=6333)
model = SentenceTransformer(EMBED_MODEL)

# ─── INIT QDRANT + POSTGRES ───────────────────────────
def init_stores():
    """Initialize PostgreSQL tables and Qdrant collections"""
    # Init PostgreSQL tables and extensions
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                
                # Agent relationships table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS agent_relationships (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        agent_id TEXT NOT NULL,
                        relationship JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # MCP message chains table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS mcp_message_chains (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        message_chain JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Robot telemetry summary table for structured queries
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS robot_telemetry (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        robot_id TEXT NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        position_x REAL,
                        position_y REAL,
                        expected_x REAL,
                        expected_y REAL,
                        movement_speed REAL,
                        distance_traveled REAL,
                        is_stuck BOOLEAN DEFAULT FALSE,
                        current_waypoint TEXT,
                        target_waypoint TEXT,
                        navigation_status TEXT,
                        sensor_data JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Index for efficient queries
                cur.execute("CREATE INDEX IF NOT EXISTS idx_robot_telemetry_robot_timestamp ON robot_telemetry(robot_id, timestamp DESC);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_robot_telemetry_stuck ON robot_telemetry(robot_id, is_stuck) WHERE is_stuck = TRUE;")
                
        print("✅ PostgreSQL ready.")
    except Exception as e:
        print("❌ PostgreSQL init failed:", e)
        raise

    # Init Qdrant collections
    collections_to_create = [
        (QDRANT_COLLECTION, "Robot telemetry and sensor data"),
        (CHAT_COLLECTION, "Chat messages and context")
    ]
    
    for collection_name, description in collections_to_create:
        if not qdrant_client.collection_exists(collection_name):
            qdrant_client.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
            )
            print(f"✅ Qdrant collection '{collection_name}' created for {description}.")

# ─── ROBOT TELEMETRY FUNCTIONS ─────────────────────────
def add_robot_telemetry(robot_id, telemetry_data):
    """
    Add robot telemetry data to both PostgreSQL (structured) and Qdrant (vector search)
    
    Expected telemetry_data structure:
    {
        "timestamp": "2024-01-01T12:00:00",
        "position": {"x": 1.5, "y": 2.3},
        "expected_position": {"x": 1.6, "y": 2.4},
        "movement_speed": 0.5,
        "distance_traveled": 0.1,
        "is_stuck": False,
        "current_waypoint": "entrance",
        "target_waypoint": "reception",
        "navigation_status": "navigating",
        "sensor_summary": {
            "obstacles_detected": 2,
            "closest_obstacle_distance": 1.2,
            "imu_stable": True,
            "wheel_encoder_error": 0.05
        }
    }
    """
    telemetry_id = str(uuid4())
    timestamp = datetime.fromisoformat(telemetry_data.get("timestamp", datetime.now().isoformat()))
    
    # Extract position data
    pos = telemetry_data.get("position", {})
    expected_pos = telemetry_data.get("expected_position", {})
    
    # Store structured data in PostgreSQL
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO robot_telemetry (
                        id, robot_id, timestamp, position_x, position_y, 
                        expected_x, expected_y, movement_speed, distance_traveled,
                        is_stuck, current_waypoint, target_waypoint, navigation_status,
                        sensor_data
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    telemetry_id, robot_id, timestamp,
                    pos.get("x"), pos.get("y"),
                    expected_pos.get("x"), expected_pos.get("y"),
                    telemetry_data.get("movement_speed"),
                    telemetry_data.get("distance_traveled"),
                    telemetry_data.get("is_stuck", False),
                    telemetry_data.get("current_waypoint"),
                    telemetry_data.get("target_waypoint"),
                    telemetry_data.get("navigation_status"),
                    Json(telemetry_data.get("sensor_summary", {}))
                ))
            conn.commit()
    except Exception as e:
        print(f"❌ Failed to store telemetry in PostgreSQL: {e}")
        raise
    
    # Create searchable text for vector storage
    searchable_text = create_telemetry_search_text(robot_id, telemetry_data)
    
    # Store in Qdrant for semantic search
    try:
        vector = model.encode(searchable_text).tolist()
        qdrant_client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[PointStruct(
                id=telemetry_id,
                vector=vector,
                payload={
                    "robot_id": robot_id,
                    "timestamp": timestamp.isoformat(),
                    "type": "telemetry",
                    "searchable_text": searchable_text,
                    **telemetry_data
                }
            )]
        )
    except Exception as e:
        print(f"❌ Failed to store telemetry in Qdrant: {e}")
        raise
    
    print(f"✅ Telemetry stored for {robot_id} at {timestamp}")
    return telemetry_id

def create_telemetry_search_text(robot_id, telemetry_data):
    """Create searchable text representation of telemetry data"""
    pos = telemetry_data.get("position", {})
    expected_pos = telemetry_data.get("expected_position", {})
    
    text_parts = [
        f"Robot {robot_id}",
        f"at position ({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f})",
        f"expected position ({expected_pos.get('x', 0):.2f}, {expected_pos.get('y', 0):.2f})",
        f"speed {telemetry_data.get('movement_speed', 0):.2f} m/s",
    ]
    
    if telemetry_data.get("is_stuck"):
        text_parts.append("STUCK and needs assistance")
    
    if telemetry_data.get("current_waypoint"):
        text_parts.append(f"currently at waypoint {telemetry_data['current_waypoint']}")
    
    if telemetry_data.get("target_waypoint"):
        text_parts.append(f"navigating to {telemetry_data['target_waypoint']}")
    
    text_parts.append(f"status: {telemetry_data.get('navigation_status', 'unknown')}")
    
    # Add sensor summary
    sensor_summary = telemetry_data.get("sensor_summary", {})
    if sensor_summary.get("obstacles_detected", 0) > 0:
        text_parts.append(f"detected {sensor_summary['obstacles_detected']} obstacles")
        closest_dist = sensor_summary.get("closest_obstacle_distance")
        if closest_dist:
            text_parts.append(f"closest obstacle {closest_dist:.2f}m away")
    
    return " ".join(text_parts)

# ─── TELEMETRY RETRIEVAL AND CONTEXT ──────────────────
def get_recent_telemetry_context(robot_id=None, hours_back=1, max_entries=10):
    """Get recent telemetry data for RAG context"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                since_time = datetime.now() - timedelta(hours=hours_back)
                
                if robot_id:
                    cur.execute("""
                        SELECT robot_id, timestamp, position_x, position_y, expected_x, expected_y,
                               movement_speed, is_stuck, current_waypoint, target_waypoint, 
                               navigation_status, sensor_data
                        FROM robot_telemetry 
                        WHERE robot_id = %s AND timestamp >= %s
                        ORDER BY timestamp DESC 
                        LIMIT %s;
                    """, (robot_id, since_time, max_entries))
                else:
                    cur.execute("""
                        SELECT robot_id, timestamp, position_x, position_y, expected_x, expected_y,
                               movement_speed, is_stuck, current_waypoint, target_waypoint, 
                               navigation_status, sensor_data
                        FROM robot_telemetry 
                        WHERE timestamp >= %s
                        ORDER BY timestamp DESC 
                        LIMIT %s;
                    """, (since_time, max_entries))
                
                return cur.fetchall()
    except Exception as e:
        print(f"❌ Error retrieving telemetry context: {e}")
        return []

def get_stuck_robots():
    """Get list of robots that are currently stuck"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                # Get most recent status for each robot
                cur.execute("""
                    WITH latest_status AS (
                        SELECT DISTINCT ON (robot_id) robot_id, timestamp, is_stuck, 
                               position_x, position_y, current_waypoint, target_waypoint
                        FROM robot_telemetry 
                        ORDER BY robot_id, timestamp DESC
                    )
                    SELECT * FROM latest_status WHERE is_stuck = TRUE;
                """)
                
                return cur.fetchall()
    except Exception as e:
        print(f"❌ Error getting stuck robots: {e}")
        return []

def search_telemetry_context(query, k=5):
    """Search telemetry data using semantic similarity"""
    try:
        vector = model.encode(query).tolist()
        results = qdrant_client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=vector,
            limit=k,
            score_threshold=0.3  # Only return reasonably similar results
        )
        
        return [
            {
                "id": r.id,
                "score": r.score,
                "robot_id": r.payload.get("robot_id"),
                "timestamp": r.payload.get("timestamp"),
                "text": r.payload.get("searchable_text"),
                "data": {k: v for k, v in r.payload.items() if k not in ["searchable_text", "type"]}
            }
            for r in results
        ]
    except Exception as e:
        print(f"❌ Error searching telemetry: {e}")
        return []

# ─── ENHANCED MESSAGE HANDLING ─────────────────────────
def add_mcp_message(message_data):
    """Enhanced MCP message logging with vector storage"""
    chain_id = str(uuid4())
    timestamp = datetime.now().isoformat()
    
    # Store in PostgreSQL
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO mcp_message_chains (id, message_chain, created_at)
                    VALUES (%s, %s, %s);
                """, (chain_id, Json(message_data), timestamp))
            conn.commit()
    except Exception as e:
        print(f"❌ Failed to store MCP message in PostgreSQL: {e}")
        raise
    
    # Create searchable text and store in Qdrant
    try:
        searchable_text = create_message_search_text(message_data)
        vector = model.encode(searchable_text).tolist()
        
        qdrant_client.upsert(
            collection_name=CHAT_COLLECTION,
            points=[PointStruct(
                id=chain_id,
                vector=vector,
                payload={
                    "timestamp": timestamp,
                    "type": "chat_message",
                    "searchable_text": searchable_text,
                    **message_data
                }
            )]
        )
    except Exception as e:
        print(f"❌ Failed to store MCP message in Qdrant: {e}")
        # Don't raise here, PostgreSQL storage succeeded
    
    print(f"✅ MCP message logged with ID: {chain_id}")
    return chain_id

def create_message_search_text(message_data):
    """Create searchable text from message data"""
    text_parts = []
    
    role = message_data.get("role", "unknown")
    source = message_data.get("source", "unknown")
    
    text_parts.append(f"{role} {source}")
    
    # Add message content
    for key in ["message", "command", "response"]:
        if message_data.get(key):
            text_parts.append(message_data[key])
    
    # Add agent/robot context
    if message_data.get("agent_id"):
        text_parts.append(f"from {message_data['agent_id']}")
    
    return " ".join(text_parts)

def get_relevant_chat_context(query, k=5):
    """Get relevant chat history for a query"""
    try:
        vector = model.encode(query).tolist()
        results = qdrant_client.search(
            collection_name=CHAT_COLLECTION,
            query_vector=vector,
            limit=k,
            score_threshold=0.3
        )
        
        return [
            {
                "id": r.id,
                "score": r.score,
                "timestamp": r.payload.get("timestamp"),
                "text": r.payload.get("searchable_text"),
                "role": r.payload.get("role"),
                "source": r.payload.get("source")
            }
            for r in results
        ]
    except Exception as e:
        print(f"❌ Error searching chat context: {e}")
        return []

# ─── CONTEXT BUILDING FOR LLM ──────────────────────────
def build_comprehensive_context(user_query, robot_id=None):
    """Build comprehensive context for LLM including telemetry and chat history"""
    context = {
        "query": user_query,
        "timestamp": datetime.now().isoformat(),
        "robot_telemetry": [],
        "stuck_robots": [],
        "relevant_chat": [],
        "recent_activity": []
    }
    
    # Get relevant telemetry based on query
    telemetry_results = search_telemetry_context(user_query, k=5)
    context["robot_telemetry"] = telemetry_results
    
    # Get stuck robots (always important for navigation queries)
    stuck_robots = get_stuck_robots()
    context["stuck_robots"] = [
        {
            "robot_id": row[0],
            "position": {"x": row[2], "y": row[3]},
            "current_waypoint": row[4],
            "target_waypoint": row[5]
        }
        for row in stuck_robots
    ]
    
    # Get relevant chat history
    chat_results = get_relevant_chat_context(user_query, k=3)
    context["relevant_chat"] = chat_results
    
    # Get recent telemetry for specified robot or all robots
    recent_telemetry = get_recent_telemetry_context(robot_id, hours_back=0.5, max_entries=5)
    context["recent_activity"] = [
        {
            "robot_id": row[0],
            "timestamp": row[1].isoformat(),
            "position": {"x": row[2], "y": row[3]},
            "expected_position": {"x": row[4], "y": row[5]},
            "speed": row[6],
            "stuck": row[7],
            "current_waypoint": row[8],
            "target_waypoint": row[9],
            "status": row[10]
        }
        for row in recent_telemetry
    ]
    
    return context

# ─── LEGACY COMPATIBILITY ──────────────────────────────
def add_telemetry_data(data_text, metadata=None):
    """Legacy function for backward compatibility"""
    if metadata is None:
        metadata = {}
    
    data_id = str(uuid4())
    vector = model.encode(data_text).tolist()
    
    qdrant_client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=[PointStruct(id=data_id, vector=vector, payload=metadata)]
    )
    
    return data_id

def retrieve_telemetry(query, k=3):
    """Legacy function for backward compatibility"""
    return search_telemetry_context(query, k)

def add_agent_relationship(agent_id, relationship):
    """Store agent relationship data"""
    relationship_id = str(uuid4())
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agent_relationships (id, agent_id, relationship)
                VALUES (%s, %s, %s);
            """, (relationship_id, agent_id, Json(relationship)))
        conn.commit()
    
    return relationship_id

def add_mcp_message_chain(message_chain):
    """Legacy function - use add_mcp_message instead"""
    return add_mcp_message(message_chain)