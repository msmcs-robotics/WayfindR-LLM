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
    # PostgreSQL - Simplified chat messages table
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        conversation_id TEXT NOT NULL,
                        user_type TEXT NOT NULL,
                        user_id TEXT NOT NULL
                    );
                """)
                
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_messages(conversation_id, timestamp);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, timestamp);")
        print("✅ PostgreSQL ready.")
    except Exception as e:
        print(f"❌ PostgreSQL init failed: {e}")
        raise

    # Qdrant - Telemetry vectors
    if not qdrant_client.collection_exists(TELEMETRY_COLLECTION):
        qdrant_client.recreate_collection(
            collection_name=TELEMETRY_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
        )
        print(f"✅ Qdrant collection '{TELEMETRY_COLLECTION}' created.")

# ── CHAT FUNCTIONS ──────────────────────────────────────
def store_chat_message(role: str, content: str, conversation_id: str, user_type: str, user_id: str):
    """Store chat message with simplified schema"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_messages (role, content, conversation_id, user_type, user_id)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id;
                """, (role, content, conversation_id, user_type, user_id))
                message_id = cur.fetchone()[0]
            conn.commit()
            print(f"💾 Stored {role} message: {conversation_id}")
            return str(message_id)
    except Exception as e:
        print(f"❌ Error storing chat message: {e}")
        return None

def get_conversation_history(conversation_id: str, limit: int = 20):
    """Get messages for a specific conversation"""
    try:
        with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT role, content, timestamp
                    FROM chat_messages 
                    WHERE conversation_id = %s
                    ORDER BY timestamp ASC 
                    LIMIT %s;
                """, (conversation_id, limit))
                
                return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ Error getting conversation history: {e}")
        return []

def get_recent_chat_context(user_id: str, limit: int = 5):
    """Get recent chat context for user across conversations"""
    try:
        with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT role, content, timestamp, conversation_id
                    FROM chat_messages 
                    WHERE user_id = %s
                    ORDER BY timestamp DESC 
                    LIMIT %s;
                """, (user_id, limit))
                
                return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ Error getting chat context: {e}")
        return []

def get_recent_chat_logs(limit: int = 20):
    """Get recent chat messages for web interface display"""
    try:
        with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, role, content, timestamp, conversation_id, user_type, user_id
                    FROM chat_messages 
                    ORDER BY timestamp DESC 
                    LIMIT %s;
                """, (limit,))
                
                messages = []
                for row in cur.fetchall():
                    messages.append([
                        str(row['id']),
                        {
                            'role': row['role'],
                            'content': row['content'][:200] + '...' if len(row['content']) > 200 else row['content'],
                            'conversation_id': row['conversation_id'],
                            'user_type': row['user_type'],
                            'user_id': row['user_id']
                        },
                        None,  # Placeholder for compatibility
                        row['timestamp'].isoformat() if row['timestamp'] else None
                    ])
                return messages
    except Exception as e:
        print(f"❌ Error getting recent chat logs: {e}")
        return []

# ── TELEMETRY FUNCTIONS ─────────────────────────────────
def store_telemetry_vector(robot_id: str, telemetry_data: dict):
    """Store simplified telemetry data as vector"""
    try:
        # Simple searchable text
        pos = telemetry_data.get('position', {})
        searchable_text = f"""
        Robot {robot_id} position ({pos.get('x', 0):.1f}, {pos.get('y', 0):.1f})
        Status: {telemetry_data.get('navigation_status', 'unknown')}
        Stuck: {telemetry_data.get('is_stuck', False)}
        Waypoint: {telemetry_data.get('current_waypoint', 'none')}
        """.strip()
        
        vector = model.encode(searchable_text).tolist()
        
        point_id = str(uuid4())
        qdrant_client.upsert(
            collection_name=TELEMETRY_COLLECTION,
            points=[PointStruct(
                id=point_id, 
                vector=vector, 
                payload={
                    "robot_id": robot_id,
                    "timestamp": telemetry_data.get("timestamp", datetime.now().isoformat()),
                    "telemetry": telemetry_data,
                    "searchable_text": searchable_text
                }
            )]
        )
        
        print(f"📊 Stored telemetry vector for {robot_id}")
        return point_id
    except Exception as e:
        print(f"❌ Error storing telemetry: {e}")
        return None

def get_robot_status(robot_id: str = None):
    """Get current robot status from recent telemetry"""
    try:
        # Simple search for recent telemetry
        query_vector = model.encode(f"robot {robot_id or ''} status").tolist()
        
        filter_condition = None
        if robot_id:
            filter_condition = {"must": [{"key": "robot_id", "match": {"value": robot_id}}]}
        
        results = qdrant_client.search(
            collection_name=TELEMETRY_COLLECTION,
            query_vector=query_vector,
            query_filter=filter_condition,
            limit=10
        )
        
        # Get most recent per robot
        robot_status = {}
        for result in results:
            rid = result.payload.get("robot_id")
            timestamp = result.payload.get("timestamp")
            
            if rid not in robot_status or timestamp > robot_status[rid]["last_seen"]:
                robot_status[rid] = {
                    "robot_id": rid,
                    "last_seen": timestamp,
                    "telemetry": result.payload.get("telemetry", {})
                }
        
        return list(robot_status.values())
        
    except Exception as e:
        print(f"❌ Error getting robot status: {e}")
        return []

def get_recent_telemetry_logs(limit: int = 20):
    """Get recent telemetry records for web interface display"""
    try:
        # Get recent points from Qdrant
        results = qdrant_client.scroll(
            collection_name=TELEMETRY_COLLECTION,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )
        
        records = []
        if results[0]:  # Check if we have points
            for point in results[0]:
                records.append({
                    "id": point.id,
                    "payload": point.payload
                })
        
        # Sort by timestamp (most recent first)
        records.sort(key=lambda x: x["payload"].get("timestamp", ""), reverse=True)
        return records[:limit]
        
    except Exception as e:
        print(f"❌ Error getting recent telemetry logs: {e}")
        return []

# ── CONTEXT BUILDING ────────────────────────────────────
def build_conversation_context(conversation_id: str, user_id: str, query: str = ""):
    """Build context for LLM from conversation and telemetry"""
    context = {
        "conversation_history": get_conversation_history(conversation_id, limit=10),
        "recent_context": get_recent_chat_context(user_id, limit=3),
        "robot_status": get_robot_status() if user_id.startswith('robot_') else []
    }
    
    # Convert timestamps to strings for JSON serialization
    for section in ['conversation_history', 'recent_context']:
        for msg in context[section]:
            if isinstance(msg.get('timestamp'), datetime):
                msg['timestamp'] = msg['timestamp'].isoformat()
    
    return context

# ── SIMPLE STATS ───────────────────────────────────────
def get_system_health():
    """Basic system health check"""
    try:
        # Test PostgreSQL
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM chat_messages;")
                message_count = cur.fetchone()[0]
        
        # Test Qdrant
        collection_info = qdrant_client.get_collection(TELEMETRY_COLLECTION)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "postgres_messages": message_count,
            "qdrant_vectors": collection_info.vectors_count,
            "status": "healthy"
        }
    except Exception as e:
        return {
            "timestamp": datetime.now().isoformat(), 
            "status": "error",
            "error": str(e)
        }