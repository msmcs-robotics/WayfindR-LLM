import os
import asyncio
import psycopg2
from psycopg2.extras import Json
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status
from sentence_transformers import SentenceTransformer
from uuid import uuid4
import nest_asyncio
from datetime import datetime

nest_asyncio.apply()

# ─── CONFIG ────────────────────────────────────────────
VECTOR_DIM = 384
EMBED_MODEL = "all-MiniLM-L6-v2"
QDRANT_COLLECTION = "telemetry_data"

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
    # Init PostgreSQL tables and extensions
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS agent_relationships (
                        id UUID PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        relationship JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS mcp_message_chains (
                        id UUID PRIMARY KEY,
                        message_chain JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
        print("✅ PostgreSQL ready.")
    except Exception as e:
        print("❌ PostgreSQL init failed:", e)
        raise

    # Init Qdrant collection
    if not qdrant_client.collection_exists(QDRANT_COLLECTION):
        qdrant_client.recreate_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
        )
        print("✅ Qdrant collection created.")

# ─── ADD TELEMETRY DATA ────────────────────────────────
def add_telemetry_data(data_text, metadata=None):
    if metadata is None:
        metadata = {}

    data_id = str(uuid4())
    vector = model.encode(data_text).tolist()

    # Insert into Qdrant
    qdrant_client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=[PointStruct(id=data_id, vector=vector, payload=metadata)]
    )

    return data_id

# ─── ADD AGENT RELATIONSHIP ────────────────────────────
def add_agent_relationship(agent_id, relationship):
    relationship_id = str(uuid4())

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agent_relationships (id, agent_id, relationship)
                VALUES (%s, %s, %s);
            """, (relationship_id, agent_id, Json(relationship)))
        conn.commit()

    return relationship_id

# ─── ADD MCP MESSAGE CHAIN ─────────────────────────────
def add_mcp_message_chain(message_chain):
    chain_id = str(uuid4())

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mcp_message_chains (id, message_chain)
                VALUES (%s, %s);
            """, (chain_id, Json(message_chain)))
        conn.commit()

    return chain_id

def add_mcp_message(message_chain):
    """
    Logs an MCP message chain into the PostgreSQL database.
    """
    chain_id = str(uuid4())
    timestamp = datetime.now().isoformat()

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mcp_message_chains (id, message_chain, created_at)
                VALUES (%s, %s, %s);
            """, (chain_id, Json(message_chain), timestamp))
        conn.commit()

    print(f"MCP message chain logged with ID: {chain_id}")
    return chain_id

# ─── RETRIEVE TELEMETRY DATA ───────────────────────────
def retrieve_telemetry(query, k=3):
    vector = model.encode(query).tolist()
    results = qdrant_client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=vector,
        limit=k
    )
    return [{"id": r.id, "payload": r.payload} for r in results]

# ─── MAIN ──────────────────────────────────────────────
async def initialize_rag():
    rag = LightRAG(
        working_dir="./rag_data",
        llm_model_func=None,  # Replace with your LLM function if needed
        embedding_func=EmbeddingFunc(
            embedding_dim=VECTOR_DIM,
            func=lambda texts: model.encode(texts).tolist()
        ),
        kv_storage="PostgreSQLStorage",
        vector_storage="QdrantVectorDBStorage",
    )

    await rag.initialize_storages()
    await initialize_pipeline_status()

    return rag