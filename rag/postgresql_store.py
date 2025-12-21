"""
PostgreSQL Store - Chat Messages and Conversation Storage
For WayfindR-LLM Tour Guide Robot System
"""
import psycopg2
from psycopg2.extras import Json
from sentence_transformers import SentenceTransformer
import time
from datetime import datetime

# Import config
try:
    from core.config import DB_CONFIG
except ImportError:
    DB_CONFIG = {
        "dbname": "wayfind_db",
        "user": "postgres",
        "password": "password",
        "host": "localhost",
        "port": "5435"
    }

VECTOR_DIM = 384  # MiniLM = 384 dimensions
model = SentenceTransformer("all-MiniLM-L6-v2")


# --- DATABASE INIT ---
def init_db(retries=5, delay=3):
    """Initialize PostgreSQL database with required tables"""
    for attempt in range(retries):
        try:
            # Create extensions separately
            try:
                with psycopg2.connect(**DB_CONFIG) as conn:
                    conn.autocommit = True
                    with conn.cursor() as cur:
                        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
            except psycopg2.errors.UniqueViolation:
                pass

            # Create tables
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS logs (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            text TEXT NOT NULL,
                            metadata JSONB,
                            embedding vector({VECTOR_DIM}),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)

                    # Create indexes
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_logs_source
                        ON logs ((metadata->>'source'));
                    """)

                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_logs_message_type
                        ON logs ((metadata->>'message_type'));
                    """)

                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_logs_robot_id
                        ON logs ((metadata->>'robot_id'));
                    """)

                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_logs_timestamp
                        ON logs ((metadata->>'timestamp'));
                    """)

                conn.commit()
            print("[PostgreSQL] Database initialized successfully")
            return
        except psycopg2.OperationalError:
            print(f"[PostgreSQL] Waiting for database... ({attempt + 1}/{retries})")
            time.sleep(delay)
        except Exception as e:
            print(f"[PostgreSQL] Failed to initialize: {e}")
            raise

    raise RuntimeError("PostgreSQL not available after multiple attempts")


# --- ADD LOG ---
def add_log(log_text, metadata=None, robot_id=None, log_id=None):
    """
    Add a message log to PostgreSQL

    Args:
        log_text: Message content
        metadata: Dictionary with:
            - source: "user" | "llm" | "robot_01" | "web" | ...
            - message_type: "command" | "response" | "notification" | "error"
            - robot_id: Optional robot identifier
            - conversation_id: Optional conversation tracking
            - timestamp: ISO format timestamp
        robot_id: Legacy parameter (adds to metadata if provided)
        log_id: Ignored (UUID auto-generated)

    Returns:
        Inserted UUID
    """
    if metadata is None:
        metadata = {}

    # Add robot_id to metadata if provided separately
    if robot_id and 'robot_id' not in metadata:
        metadata['robot_id'] = robot_id

    # Ensure required fields exist
    if 'source' not in metadata:
        metadata['source'] = 'system'

    if 'message_type' not in metadata:
        metadata['message_type'] = 'notification'

    if 'timestamp' not in metadata:
        metadata['timestamp'] = datetime.now().isoformat()

    # Generate embedding
    embedding = model.encode([log_text])[0].tolist()

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO logs (text, metadata, embedding)
                VALUES (%s, %s, %s)
                RETURNING id;
            """, (log_text, Json(metadata), embedding))
            inserted_id = cur.fetchone()[0]
        conn.commit()

    return inserted_id


# --- RETRIEVE SIMILAR LOGS ---
def retrieve_relevant(query, k=3):
    """Retrieve logs similar to query using vector search"""
    query_vec = model.encode([query])[0].tolist()

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, text, metadata, created_at
                FROM logs
                ORDER BY embedding <-> %s::vector
                LIMIT %s;
            """, (str(query_vec), k))
            results = cur.fetchall()

    return [
        {
            "id": row[0],
            "text": row[1],
            "metadata": row[2],
            "created_at": row[3],
            "source": row[2].get("source") if row[2] else None,
            "message_type": row[2].get("message_type") if row[2] else None
        }
        for row in results
    ]


# --- GET MESSAGES BY SOURCE ---
def get_messages_by_source(source, limit=50):
    """Get messages from a specific source (user, llm, robot_id, etc.)"""
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, text, metadata, created_at
                FROM logs
                WHERE metadata->>'source' = %s
                ORDER BY created_at DESC
                LIMIT %s;
            """, (source, limit))
            return [
                {
                    "id": row[0],
                    "text": row[1],
                    "metadata": row[2],
                    "created_at": row[3]
                }
                for row in cur.fetchall()
            ]


# --- GET MESSAGES BY TYPE ---
def get_messages_by_type(message_type, limit=50):
    """Get messages by type (command, response, notification, error)"""
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, text, metadata, created_at
                FROM logs
                WHERE metadata->>'message_type' = %s
                ORDER BY created_at DESC
                LIMIT %s;
            """, (message_type, limit))
            return [
                {
                    "id": row[0],
                    "text": row[1],
                    "metadata": row[2],
                    "created_at": row[3]
                }
                for row in cur.fetchall()
            ]


# --- GET ROBOT ERRORS ---
def get_robot_errors(robot_id=None, limit=50):
    """Get error messages, optionally filtered by robot"""
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            if robot_id:
                cur.execute("""
                    SELECT id, text, metadata, created_at
                    FROM logs
                    WHERE metadata->>'message_type' = 'error'
                    AND metadata->>'robot_id' = %s
                    ORDER BY created_at DESC
                    LIMIT %s;
                """, (robot_id, limit))
            else:
                cur.execute("""
                    SELECT id, text, metadata, created_at
                    FROM logs
                    WHERE metadata->>'message_type' = 'error'
                    ORDER BY created_at DESC
                    LIMIT %s;
                """, (limit,))

            return [
                {
                    "id": row[0],
                    "text": row[1],
                    "metadata": row[2],
                    "created_at": row[3]
                }
                for row in cur.fetchall()
            ]


# --- GET CONVERSATION HISTORY ---
def get_conversation_history(conversation_id=None, limit=100):
    """Get user/LLM conversation history"""
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            if conversation_id:
                cur.execute("""
                    SELECT id, text, metadata, created_at
                    FROM logs
                    WHERE metadata->>'conversation_id' = %s
                    ORDER BY created_at ASC
                    LIMIT %s;
                """, (conversation_id, limit))
            else:
                cur.execute("""
                    SELECT id, text, metadata, created_at
                    FROM logs
                    WHERE metadata->>'source' IN ('user', 'llm')
                    ORDER BY created_at DESC
                    LIMIT %s;
                """, (limit,))

            return [
                {
                    "id": row[0],
                    "text": row[1],
                    "metadata": row[2],
                    "created_at": row[3],
                    "role": row[2].get("source") if row[2] else None
                }
                for row in cur.fetchall()
            ]


# --- GET LOGS BY ROBOT ---
def get_logs_by_robot(robot_id, limit=50):
    """Get all logs for a specific robot"""
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, text, metadata, created_at FROM logs
                WHERE metadata->>'robot_id' = %s
                ORDER BY created_at DESC
                LIMIT %s;
            """, (robot_id, limit))
            return [
                {
                    "id": row[0],
                    "text": row[1],
                    "metadata": row[2],
                    "created_at": row[3]
                }
                for row in cur.fetchall()
            ]


# --- CLEAR STORE ---
def clear_store():
    """Clear all data from logs table"""
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM logs;")
        conn.commit()


# Initialize on import
init_db()
