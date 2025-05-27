import os
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from uuid import uuid4
from datetime import datetime, timedelta
import json

# Configuration
VECTOR_DIM = 384
EMBED_MODEL = "all-MiniLM-L6-v2"
TELEMETRY_COLLECTION = "robot_telemetry"

DB_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

qdrant_client = QdrantClient(host="localhost", port=6333)
model = SentenceTransformer(EMBED_MODEL)

def init_stores():
    """Initialize PostgreSQL tables and Qdrant collections"""
    # PostgreSQL - Chat messages only
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                
                # Simple chat messages table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        user_id TEXT,
                        metadata JSONB
                    );
                """)
                
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_timestamp ON chat_messages(timestamp DESC);")
        print("✅ PostgreSQL ready.")
    except Exception as e:
        print(f"❌ PostgreSQL init failed: {e}")
        raise

    # Qdrant - Telemetry vectors only
    if not qdrant_client.collection_exists(TELEMETRY_COLLECTION):
        qdrant_client.recreate_collection(
            collection_name=TELEMETRY_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
        )
        print(f"✅ Qdrant collection '{TELEMETRY_COLLECTION}' created.")

# ── CHAT FUNCTIONS (PostgreSQL) ──────────────────────────
def store_chat_message(role: str, content: str, user_id: str = None, metadata: dict = None):
    """Store chat message in PostgreSQL"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_messages (role, content, user_id, metadata)
                    VALUES (%s, %s, %s, %s) RETURNING id;
                """, (role, content, user_id, Json(metadata) if metadata else None))
                message_id = cur.fetchone()[0]
            conn.commit()
            return str(message_id)
    except Exception as e:
        print(f"❌ Error storing chat message: {e}")
        return None

def get_recent_chat_messages(limit: int = 10, user_id: str = None):
    """Get recent chat messages for context"""
    try:
        with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                if user_id:
                    cur.execute("""
                        SELECT role, content, timestamp, metadata
                        FROM chat_messages 
                        WHERE user_id = %s OR user_id IS NULL
                        ORDER BY timestamp DESC 
                        LIMIT %s;
                    """, (user_id, limit))
                else:
                    cur.execute("""
                        SELECT role, content, timestamp, metadata
                        FROM chat_messages 
                        ORDER BY timestamp DESC 
                        LIMIT %s;
                    """, (limit,))
                
                return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ Error getting chat messages: {e}")
        return []

# ── TELEMETRY FUNCTIONS (Qdrant) ─────────────────────────
def store_telemetry_vector(robot_id: str, telemetry_data: dict):
    """Store telemetry data as vector in Qdrant"""
    try:
        # Create searchable text from telemetry
        searchable_text = f"""
        Robot {robot_id} at position ({telemetry_data.get('position', {}).get('x', 0):.2f}, {telemetry_data.get('position', {}).get('y', 0):.2f})
        Status: {telemetry_data.get('navigation_status', 'unknown')}
        Speed: {telemetry_data.get('movement_speed', 0):.2f} m/s
        Waypoint: {telemetry_data.get('current_waypoint', 'none')} -> {telemetry_data.get('target_waypoint', 'none')}
        Stuck: {telemetry_data.get('is_stuck', False)}
        """.strip()
        
        # Generate vector embedding
        vector = model.encode(searchable_text).tolist()
        
        # Store in Qdrant
        point_id = str(uuid4())
        qdrant_client.upsert(
            collection_name=TELEMETRY_COLLECTION,
            points=[PointStruct(
                id=point_id, 
                vector=vector, 
                payload={
                    "robot_id": robot_id,
                    "timestamp": telemetry_data.get("timestamp", datetime.now().isoformat()),
                    "searchable_text": searchable_text,
                    "telemetry": telemetry_data
                }
            )]
        )
        
        return point_id
    except Exception as e:
        print(f"❌ Error storing telemetry vector: {e}")
        return None

def search_telemetry_context(query: str, robot_id: str = None, limit: int = 5):
    """Search telemetry vectors for relevant context"""
    try:
        vector = model.encode(query).tolist()
        
        # Add robot_id filter if specified
        query_filter = None
        if robot_id:
            query_filter = {"must": [{"key": "robot_id", "match": {"value": robot_id}}]}
        
        results = qdrant_client.search(
            collection_name=TELEMETRY_COLLECTION,
            query_vector=vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=0.3
        )
        
        return [
            {
                "robot_id": r.payload.get("robot_id"),
                "timestamp": r.payload.get("timestamp"),
                "score": r.score,
                "telemetry": r.payload.get("telemetry", {}),
                "context": r.payload.get("searchable_text")
            }
            for r in results
        ]
    except Exception as e:
        print(f"❌ Error searching telemetry: {e}")
        return []

# ── CONTEXT BUILDING ─────────────────────────────────────
def build_conversation_context(query: str, user_id: str = None, robot_id: str = None):
    """Build complete context for LLM from both chat and telemetry"""
    context = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "chat_history": [],
        "telemetry_context": []
    }
    
    # Get recent chat messages
    context["chat_history"] = get_recent_chat_messages(limit=5, user_id=user_id)
    
    # Get relevant telemetry context
    context["telemetry_context"] = search_telemetry_context(query, robot_id=robot_id, limit=3)
    
    return context

# Add these utility functions to rag_store.py:

def get_chat_statistics() -> dict:
    """Get chat message statistics"""
    try:
        with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_messages,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(CASE WHEN role = 'user' THEN 1 END) as user_messages,
                        COUNT(CASE WHEN role = 'assistant' THEN 1 END) as assistant_messages,
                        MAX(timestamp) as last_message,
                        MIN(timestamp) as first_message
                    FROM chat_messages;
                """)
                return dict(cur.fetchone())
    except Exception as e:
        print(f"❌ Error getting chat statistics: {e}")
        return {}

def get_telemetry_statistics() -> dict:
    """Get telemetry statistics from Qdrant"""
    try:
        collection_info = qdrant_client.get_collection(TELEMETRY_COLLECTION)
        
        # Get recent telemetry for robot count
        recent_telemetry = qdrant_client.search(
            collection_name=TELEMETRY_COLLECTION,
            query_vector=[0.0] * VECTOR_DIM,  # Dummy vector
            limit=100,
            score_threshold=0.0
        )
        
        # Count unique robots
        unique_robots = set()
        for point in recent_telemetry:
            robot_id = point.payload.get("robot_id")
            if robot_id:
                unique_robots.add(robot_id)
        
        return {
            "total_points": collection_info.vectors_count,
            "unique_robots": len(unique_robots),
            "collection_status": collection_info.status.value if hasattr(collection_info.status, 'value') else str(collection_info.status)
        }
    except Exception as e:
        print(f"❌ Error getting telemetry statistics: {e}")
        return {}

def get_system_health() -> dict:
    """Get overall system health status"""
    chat_stats = get_chat_statistics()
    telemetry_stats = get_telemetry_statistics()
    
    return {
        "timestamp": datetime.now().isoformat(),
        "postgres": {
            "status": "healthy" if chat_stats else "error",
            "stats": chat_stats
        },
        "qdrant": {
            "status": "healthy" if telemetry_stats else "error", 
            "stats": telemetry_stats
        }
    }

# Improve context building with better error handling
def build_conversation_context(query: str, user_id: str = None, robot_id: str = None):
    """Build complete context for LLM from both chat and telemetry"""
    context = {
        "query": query,
        "timestamp": datetime.now().isoformat(),  # Already a string
        "chat_history": [],
        "telemetry_context": [],
        "context_summary": ""
    }
    
    try:
        # Get recent chat messages and convert timestamps to strings
        chat_history = get_recent_chat_messages(limit=5, user_id=user_id)
        for message in chat_history:
            if 'timestamp' in message and isinstance(message['timestamp'], datetime):
                message['timestamp'] = message['timestamp'].isoformat()
        context["chat_history"] = chat_history
    except Exception as e:
        print(f"⚠️ Could not load chat history: {e}")
    
    try:
        # Get relevant telemetry context and convert timestamps to strings
        telemetry_context = search_telemetry_context(query, robot_id=robot_id, limit=3)
        for point in telemetry_context:
            if 'timestamp' in point and isinstance(point['timestamp'], str):
                try:
                    # If it's already a string, parse and re-format to ensure consistency
                    dt = datetime.fromisoformat(point['timestamp'])
                    point['timestamp'] = dt.isoformat()
                except ValueError:
                    pass
        context["telemetry_context"] = telemetry_context
    except Exception as e:
        print(f"⚠️ Could not load telemetry context: {e}")
    
    # Create summary
    chat_count = len(context["chat_history"])
    telemetry_count = len(context["telemetry_context"])
    context["context_summary"] = f"Context: {chat_count} chat messages, {telemetry_count} telemetry points"
    
    return context