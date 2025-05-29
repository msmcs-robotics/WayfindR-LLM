# db_manager.py - Fixed async/sync issues
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
import uuid

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from config_manager import get_config
import traceback

class DatabaseManager:
    """Centralized database operations for both PostgreSQL and Qdrant"""
    
    def __init__(self):
        self.config = get_config()
        self._postgres_pool = None
        self._qdrant_client = None
        self._embedding_model = None
        
    def initialize(self):
        """Initialize all database connections"""
        self._init_postgres()
        self._init_qdrant()
        self._init_embeddings()
        self._create_tables()
        print("✅ All database systems initialized")

    # ─── Postgres Operations ──────────────────────────────────────────
    
    def _init_postgres(self):
        """Initialize PostgreSQL connection pool"""
        self._postgres_pool = pool.ThreadedConnectionPool(
            minconn=self.config.database.postgres_pool_min,
            maxconn=self.config.database.postgres_pool_max,
            host=self.config.database.postgres_host,
            port=self.config.database.postgres_port,
            database=self.config.database.postgres_database,
            user=self.config.database.postgres_username,
            password=self.config.database.postgres_password
        )
        print("✅ PostgreSQL connection pool initialized")

    def _create_tables(self):
        """Ensure required tables exist"""
        with self.postgres_connection() as conn:
            with conn.cursor() as cur:
                # Chat messages table
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
                    CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_messages(conversation_id, timestamp);
                    CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, timestamp);
                """)
                conn.commit()

    @contextmanager
    def postgres_connection(self, dict_cursor: bool = False):
        """Get PostgreSQL connection from pool"""
        conn = None
        try:
            conn = self._postgres_pool.getconn()
            if dict_cursor:
                conn.cursor_factory = RealDictCursor
            yield conn
        finally:
            if conn:
                self._postgres_pool.putconn(conn)

    # ─── Chat Operations ──────────────────────────────────────────────
    
    async def store_chat_message(self, role: str, content: str, conversation_id: str, 
                           user_type: str, user_id: str) -> Optional[str]:
        """Store a chat message in PostgreSQL - FIXED SYNC VERSION"""
        try:
            print(f"💾 Storing chat message: role={role}, conv_id={conversation_id}")
            with self.postgres_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO chat_messages (role, content, conversation_id, user_type, user_id)
                        VALUES (%s, %s, %s, %s, %s) RETURNING id;
                    """, (role, content, conversation_id, user_type, user_id))
                    row = cur.fetchone()
                    if row is None:
                        print("❌ Error: No row returned from INSERT.")
                        return None
                    
                    message_id = row[0] if isinstance(row, tuple) else row.get("id")
                    conn.commit()
                    print(f"✅ Message stored with ID: {message_id}")
                    return str(message_id)
        except Exception as e:
            print("❌ Error storing chat message!")
            print(f"   Exception: {repr(e)}")
            traceback.print_exc()
            return None

    async def get_conversation_history(self, conversation_id: str, limit: int = 20) -> List[Dict]:
        """Get conversation history from PostgreSQL - FIXED SYNC VERSION"""
        try:
            print(f"📖 Getting conversation history for: {conversation_id}")
            with self.postgres_connection(dict_cursor=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT role, content, timestamp, user_type, user_id
                        FROM chat_messages 
                        WHERE conversation_id = %s
                        ORDER BY timestamp ASC 
                        LIMIT %s;
                    """, (conversation_id, limit))
                    result = [dict(row) for row in cur.fetchall()]
                    print(f"✅ Found {len(result)} messages in conversation")
                    return result
        except Exception as e:
            print(f"❌ Error getting conversation history: {e}")
            print(f"   Exception: {repr(e)}")
            traceback.print_exc()
            return []

    # ─── Qdrant Operations ────────────────────────────────────────────
    
    def _init_qdrant(self):
        """Initialize Qdrant client and collections"""
        self._qdrant_client = QdrantClient(
            host=self.config.database.qdrant_host,
            port=self.config.database.qdrant_port
        )
        
        # Create collection if it doesn't exist
        if not self._qdrant_client.collection_exists(self.config.database.qdrant_collection):
            self._qdrant_client.recreate_collection(
                collection_name=self.config.database.qdrant_collection,
                vectors_config=VectorParams(
                    size=self.config.llm.vector_dimension,
                    distance=Distance.COSINE
                )
            )
        print("✅ Qdrant client initialized")

    def _init_embeddings(self):
        """Initialize embedding model"""
        self._embedding_model = SentenceTransformer(self.config.llm.embedding_model)
        print(f"✅ Embedding model loaded: {self.config.llm.embedding_model}")

    def store_telemetry(self, robot_id: str, telemetry_data: dict) -> Optional[str]:
        """Store robot telemetry in Qdrant"""
        try:
            # Generate searchable text
            searchable_text = self._generate_telemetry_text(robot_id, telemetry_data)
            vector = self._embedding_model.encode(searchable_text).tolist()
            
            # Create and store point
            point_id = str(uuid.uuid4())
            self._qdrant_client.upsert(
                collection_name=self.config.database.qdrant_collection,
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
            return point_id
        except Exception as e:
            print(f"❌ Error storing telemetry: {e}")
            print(f"   Exception: {repr(e)}")
            traceback.print_exc()
            return None

    def _generate_telemetry_text(self, robot_id: str, data: dict) -> str:
        """Generate searchable text from telemetry data"""
        pos = data.get('position', {})
        return f"""
        Robot {robot_id} at position ({pos.get('x', 0):.1f}, {pos.get('y', 0):.1f})
        Navigation status: {data.get('navigation_status', 'unknown')}
        Stuck: {data.get('is_stuck', False)}
        Current waypoint: {data.get('current_waypoint', 'none')}
        Battery: {data.get('battery_level', 'unknown')}%
        """.strip()

    def get_active_robots(self, hours: int = 24) -> Set[str]:
        """Get set of active robot IDs from Qdrant"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            active_robots = set()
            
            scroll_result = self._qdrant_client.scroll(
                collection_name=self.config.database.qdrant_collection,
                limit=1000,
                with_payload=True
            )
            
            for point in scroll_result[0]:
                payload = point.payload
                if payload and payload.get("timestamp"):
                    try:
                        timestamp = datetime.fromisoformat(payload["timestamp"].replace('Z', '+00:00'))
                        if timestamp > cutoff_time:
                            active_robots.add(payload["robot_id"])
                    except ValueError:
                        continue
            
            return active_robots
        except Exception as e:
            print(f"❌ Error getting active robots: {e}")
            return set()

    async def get_robot_telemetry(self, robot_id: str, limit: int = 1) -> List[Dict]:
        """Get recent telemetry for a specific robot"""
        try:
            scroll_result = self._qdrant_client.scroll(
                collection_name=self.config.database.qdrant_collection,
                limit=limit,
                with_payload=True,
                query_filter={
                    "must": [{
                        "key": "robot_id",
                        "match": {"value": robot_id}
                    }]
                }
            )
            
            return [
                {
                    "robot_id": point.payload["robot_id"],
                    "timestamp": point.payload["timestamp"],
                    "telemetry": point.payload["telemetry"]
                }
                for point in scroll_result[0]
                if point.payload
            ]
        except Exception as e:
            print(f"❌ Error getting telemetry for {robot_id}: {e}")
            print(f"   Exception: {repr(e)}")
            traceback.print_exc()
            return []

    def get_recent_chat_logs(self, limit: int = 20) -> List[Dict]:
        """Get recent chat logs from PostgreSQL"""
        try:
            print(f"📖 Getting recent chat logs (limit: {limit})")
            with self.postgres_connection(dict_cursor=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT role, content, timestamp, conversation_id, user_type, user_id
                        FROM chat_messages
                        ORDER BY timestamp DESC
                        LIMIT %s;
                    """, (limit,))
                    result = [dict(row) for row in cur.fetchall()]
                    print(f"✅ Retrieved {len(result)} recent chat logs")
                    return result
        except Exception as e:
            print(f"❌ Error getting recent chat logs: {e}")
            traceback.print_exc()
            return []

    def get_recent_telemetry_logs(self, limit: int = 20) -> List[Dict]:
        """Get recent telemetry logs from Qdrant"""
        try:
            print(f"📡 Getting recent telemetry logs (limit: {limit})")
            scroll_result = self._qdrant_client.scroll(
                collection_name=self.config.database.qdrant_collection,
                limit=limit,
                with_payload=True
            )
            
            logs = []
            for point in scroll_result[0]:
                if point.payload:
                    logs.append({
                        "id": point.id,
                        "payload": point.payload
                    })
            
            # Sort by timestamp (newest first)
            logs.sort(key=lambda x: x.get("payload", {}).get("timestamp", ""), reverse=True)
            print(f"✅ Retrieved {len(logs)} recent telemetry logs")
            return logs[:limit]
        except Exception as e:
            print(f"❌ Error getting recent telemetry logs: {e}")
            traceback.print_exc()
            return []
            
    # ─── System Health ────────────────────────────────────────────────
    
    def check_system_health(self) -> Dict:
        """Check health of all database systems"""
        health = {"timestamp": datetime.now().isoformat()}
        
        # PostgreSQL health
        try:
            with self.postgres_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM chat_messages;")
                    health["postgres_messages"] = cur.fetchone()[0]
                    health["postgres_status"] = "healthy"
        except Exception as e:
            health["postgres_status"] = f"error: {str(e)}"
        
        # Qdrant health
        try:
            collection_info = self._qdrant_client.get_collection(self.config.database.qdrant_collection)
            health["qdrant_vectors"] = collection_info.vectors_count
            health["qdrant_status"] = "healthy"
        except Exception as e:
            health["qdrant_status"] = f"error: {str(e)}"
        
        health["overall_status"] = (
            "healthy" if "error" not in health["postgres_status"] 
            and "error" not in health["qdrant_status"] 
            else "degraded"
        )
        
        return health

# Global instance
_db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get global database manager instance"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.initialize()
    return _db_manager