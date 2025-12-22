"""
PostgreSQL Store - Chat Messages and Conversation Storage
For WayfindR-LLM Tour Guide Robot System

Stores conversation logs with optional semantic search via Ollama embeddings.
All AI/LLM work is offloaded to the HPC cluster via Ollama.
"""
import psycopg2
from psycopg2.extras import Json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import ollama

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

# Embedding model configuration
# Uses Ollama through SSH tunnel to HPC
OLLAMA_HOST = "http://localhost:11434"
EMBEDDING_MODEL = "all-minilm:l6-v2"
VECTOR_DIM = 384

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
                print(f"[PostgreSQL] Ollama embeddings available ({EMBEDDING_MODEL})")
                return True
        else:
            print(f"[PostgreSQL] Embedding model {EMBEDDING_MODEL} not found")
            print(f"[PostgreSQL] Semantic search will use keyword fallback")

    except Exception as e:
        print(f"[PostgreSQL] Ollama embeddings not available: {e}")
        print(f"[PostgreSQL] Using keyword search fallback")

    embeddings_available = False
    return False


def _get_embedding(text: str) -> Optional[List[float]]:
    """
    Get embedding vector for text using Ollama

    Returns None if embeddings not available
    """
    if embeddings_available and ollama_client:
        try:
            response = ollama_client.embeddings(model=EMBEDDING_MODEL, prompt=text)
            if response and 'embedding' in response:
                return response['embedding']
        except Exception as e:
            print(f"[PostgreSQL] Embedding failed: {e}")

    return None


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
                        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                        # Enable pgvector extension for semantic search
                        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            except psycopg2.errors.UniqueViolation:
                pass
            except Exception as e:
                # pgvector might not be installed, that's ok
                if "vector" in str(e).lower():
                    print(f"[PostgreSQL] pgvector not available, using keyword search")

            # Create tables
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    # Check if vector extension is available
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_extension WHERE extname = 'vector'
                        );
                    """)
                    has_vector = cur.fetchone()[0]

                    if has_vector:
                        # Create table with vector column for embeddings
                        cur.execute(f"""
                            CREATE TABLE IF NOT EXISTS logs (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                text TEXT NOT NULL,
                                metadata JSONB,
                                embedding vector({VECTOR_DIM}),
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                        """)
                        print("[PostgreSQL] Created table with vector support")
                    else:
                        # Create table without vector column
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS logs (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                text TEXT NOT NULL,
                                metadata JSONB,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                        """)
                        print("[PostgreSQL] Created table without vector support")

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

                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_logs_conversation_id
                        ON logs ((metadata->>'conversation_id'));
                    """)

                    # Create vector index if available
                    if has_vector:
                        try:
                            cur.execute("""
                                CREATE INDEX IF NOT EXISTS idx_logs_embedding
                                ON logs USING ivfflat (embedding vector_cosine_ops)
                                WITH (lists = 100);
                            """)
                        except Exception as e:
                            # IVFFlat requires data to create, will be created later
                            pass

                conn.commit()

            # Initialize Ollama for embeddings
            _init_ollama()

            print("[PostgreSQL] Database initialized successfully")
            return
        except psycopg2.OperationalError:
            print(f"[PostgreSQL] Waiting for database... ({attempt + 1}/{retries})")
            time.sleep(delay)
        except Exception as e:
            print(f"[PostgreSQL] Failed to initialize: {e}")
            raise

    raise RuntimeError("PostgreSQL not available after multiple attempts")


def _has_embedding_column() -> bool:
    """Check if the logs table has an embedding column"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'logs' AND column_name = 'embedding';
                """)
                return cur.fetchone() is not None
    except:
        return False


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

    # Generate embedding if available
    embedding = _get_embedding(log_text) if embeddings_available else None
    has_embedding_col = _has_embedding_column()

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            if embedding and has_embedding_col:
                cur.execute("""
                    INSERT INTO logs (text, metadata, embedding)
                    VALUES (%s, %s, %s)
                    RETURNING id;
                """, (log_text, Json(metadata), embedding))
            else:
                cur.execute("""
                    INSERT INTO logs (text, metadata)
                    VALUES (%s, %s)
                    RETURNING id;
                """, (log_text, Json(metadata)))
            inserted_id = cur.fetchone()[0]
        conn.commit()

    return inserted_id


# --- SEMANTIC SEARCH LOGS ---
def search_logs(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search logs by semantic similarity or keyword fallback

    Uses Ollama embeddings for semantic search when available,
    falls back to case-insensitive text search otherwise.

    Args:
        query: Search query (natural language)
        limit: Number of results

    Returns:
        List of matching log entries
    """
    # Try semantic search first if embeddings available
    if embeddings_available and _has_embedding_column():
        query_embedding = _get_embedding(query)
        if query_embedding:
            try:
                with psycopg2.connect(**DB_CONFIG) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT id, text, metadata, created_at,
                                   1 - (embedding <=> %s::vector) as similarity
                            FROM logs
                            WHERE embedding IS NOT NULL
                            ORDER BY embedding <=> %s::vector
                            LIMIT %s;
                        """, (query_embedding, query_embedding, limit))
                        results = cur.fetchall()

                return [
                    {
                        "id": row[0],
                        "text": row[1],
                        "metadata": row[2],
                        "created_at": row[3],
                        "similarity": row[4],
                        "source": row[2].get("source") if row[2] else None,
                        "message_type": row[2].get("message_type") if row[2] else None
                    }
                    for row in results
                ]
            except Exception as e:
                print(f"[PostgreSQL] Semantic search failed, using fallback: {e}")

    # Fallback: keyword search
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, text, metadata, created_at
                FROM logs
                WHERE text ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s;
            """, (f'%{query}%', limit))
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


# --- GET RECENT LOGS ---
def get_recent_logs(limit=50):
    """Get most recent logs"""
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, text, metadata, created_at
                FROM logs
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


# --- CLEAR STORE ---
def clear_store():
    """Clear all data from logs table"""
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM logs;")
        conn.commit()


# Backwards compatibility alias
def retrieve_relevant(query, k=3):
    """Alias for search_logs (backwards compatibility)"""
    return search_logs(query, limit=k)


# Initialize on import
init_db()
