# rag_store.py - Updated for Raspberry Pi SLAM Navigation System
import os
import asyncio
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
from uuid import uuid4
import nest_asyncio
from datetime import datetime, timedelta
import json
import logging
from typing import Dict, List, Optional, Any
import numpy as np

nest_asyncio.apply()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── CONFIGURATION ────────────────────────────────────────────
VECTOR_DIM = 384
EMBED_MODEL = "all-MiniLM-L6-v2"
QDRANT_COLLECTION = "slam_telemetry"
QDRANT_CHAT_COLLECTION = "chat_embeddings"  # Optional for semantic chat search

DB_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres", 
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

# Initialize clients
qdrant_client = QdrantClient(host="localhost", port=6333)
model = SentenceTransformer(EMBED_MODEL)

# ─── INITIALIZATION ───────────────────────────────────────────
def init_stores():
    """Initialize both PostgreSQL and Qdrant for hybrid storage"""
    try:
        # Initialize PostgreSQL tables
        with psycopg2.connect(**DB_CONFIG) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Enable required extensions
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS btree_gin;")
                
                # Chat and MCP message storage (PostgreSQL)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS mcp_message_chains (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        message_chain JSONB NOT NULL,
                        message_type VARCHAR(50) NOT NULL DEFAULT 'general',
                        robot_id VARCHAR(100),
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX gin_message_chain ON mcp_message_chains USING gin(message_chain)
                    );
                """)
                
                # Robot state and relationships (PostgreSQL)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS robot_relationships (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        robot_id VARCHAR(100) NOT NULL,
                        relationship_type VARCHAR(50) NOT NULL,
                        relationship_data JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Navigation commands and responses (PostgreSQL)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS navigation_commands (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        robot_id VARCHAR(100) NOT NULL,
                        command_type VARCHAR(50) NOT NULL,
                        command_data JSONB NOT NULL,
                        status VARCHAR(50) DEFAULT 'pending',
                        response_data JSONB,
                        issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        INDEX idx_robot_commands ON navigation_commands(robot_id, issued_at),
                        INDEX gin_command_data ON navigation_commands USING gin(command_data)
                    );
                """)
                
                # SLAM map data and waypoints (PostgreSQL) 
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS slam_map_data (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        robot_id VARCHAR(100) NOT NULL,
                        map_name VARCHAR(200),
                        map_data JSONB NOT NULL,
                        waypoints JSONB,
                        obstacles JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create indexes for better performance
                cur.execute("CREATE INDEX IF NOT EXISTS idx_mcp_robot_id ON mcp_message_chains(robot_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_mcp_timestamp ON mcp_message_chains(timestamp);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_mcp_type ON mcp_message_chains(message_type);")
                
        logger.info("✅ PostgreSQL tables initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ PostgreSQL initialization failed: {e}")
        raise

    try:
        # Initialize Qdrant collections
        # Main telemetry collection
        if not qdrant_client.collection_exists(QDRANT_COLLECTION):
            qdrant_client.recreate_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
            )
            logger.info(f"✅ Qdrant collection '{QDRANT_COLLECTION}' created")
        
        # Optional chat embeddings collection for semantic search
        if not qdrant_client.collection_exists(QDRANT_CHAT_COLLECTION):
            qdrant_client.recreate_collection(
                collection_name=QDRANT_CHAT_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
            )
            logger.info(f"✅ Qdrant collection '{QDRANT_CHAT_COLLECTION}' created")
            
    except Exception as e:
        logger.error(f"❌ Qdrant initialization failed: {e}")
        raise

# ─── TELEMETRY DATA STORAGE (QDRANT) ─────────────────────────
def add_slam_telemetry(robot_id: str, telemetry_data: Dict[str, Any]) -> str:
    """Store SLAM navigation telemetry in Qdrant with vector embeddings"""
    try:
        # Create rich text representation for embedding
        telemetry_text = format_telemetry_for_embedding(robot_id, telemetry_data)
        
        # Generate vector embedding
        vector = model.encode(telemetry_text).tolist()
        
        # Prepare metadata for Qdrant
        metadata = {
            "robot_id": robot_id,
            "timestamp": telemetry_data.get("timestamp", datetime.now().isoformat()),
            "position_x": float(telemetry_data.get("position", {}).get("x", 0)),
            "position_y": float(telemetry_data.get("position", {}).get("y", 0)),
            "heading": float(telemetry_data.get("position", {}).get("heading", 0)),
            "status": telemetry_data.get("status", "unknown"),
            "battery_level": float(telemetry_data.get("battery_level", 0)),
            "obstacle_distance": float(telemetry_data.get("obstacle_distance", 0)),
            "navigation_status": telemetry_data.get("navigation_status", "idle"),
            "target_waypoint": telemetry_data.get("target_waypoint", ""),
            "slam_quality": float(telemetry_data.get("slam_quality", 0)),
            "localization_confidence": float(telemetry_data.get("localization_confidence", 0)),
            "data_type": "slam_telemetry"
        }
        
        # Add LIDAR data if available
        if "lidar_data" in telemetry_data:
            lidar = telemetry_data["lidar_data"]
            metadata.update({
                "lidar_min_distance": float(lidar.get("min_distance", 0)),
                "lidar_max_distance": float(lidar.get("max_distance", 0)),
                "lidar_avg_distance": float(lidar.get("avg_distance", 0)),
                "lidar_points_count": int(lidar.get("points_count", 0))
            })
        
        # Add navigation data if available
        if "navigation" in telemetry_data:
            nav = telemetry_data["navigation"]
            metadata.update({
                "waypoints_remaining": int(nav.get("waypoints_remaining", 0)),
                "path_length": float(nav.get("path_length", 0)),
                "eta_seconds": float(nav.get("eta_seconds", 0))
            })
            
        telemetry_id = str(uuid4())
        
        # Store in Qdrant
        qdrant_client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[PointStruct(id=telemetry_id, vector=vector, payload=metadata)]
        )
        
        logger.info(f"📊 SLAM telemetry stored for {robot_id}: {telemetry_id}")
        return telemetry_id
        
    except Exception as e:
        logger.error(f"❌ Failed to store SLAM telemetry: {e}")
        raise

def format_telemetry_for_embedding(robot_id: str, data: Dict[str, Any]) -> str:
    """Format telemetry data into rich text for vector embedding"""
    position = data.get("position", {})
    
    text = f"""SLAM Navigation Telemetry Report
Robot: {robot_id}
Timestamp: {data.get('timestamp', 'unknown')}
Location: ({position.get('x', 0):.2f}, {position.get('y', 0):.2f}) meters, heading {position.get('heading', 0):.1f}°
Status: {data.get('status', 'unknown')}
Navigation: {data.get('navigation_status', 'idle')}
Target: {data.get('target_waypoint', 'none')}
Battery: {data.get('battery_level', 0):.1f}%
Nearest obstacle: {data.get('obstacle_distance', 0):.2f}m
SLAM quality: {data.get('slam_quality', 0):.2f}
Localization confidence: {data.get('localization_confidence', 0):.2f}"""

    # Add LIDAR summary
    if "lidar_data" in data:
        lidar = data["lidar_data"]
        text += f"""
LIDAR scan: {lidar.get('points_count', 0)} points, distances {lidar.get('min_distance', 0):.1f}-{lidar.get('max_distance', 0):.1f}m"""

    # Add navigation details
    if "navigation" in data:
        nav = data["navigation"]
        text += f"""
Navigation: {nav.get('waypoints_remaining', 0)} waypoints remaining, ETA {nav.get('eta_seconds', 0):.0f}s"""

    # Add map information
    if "map_info" in data:
        map_info = data["map_info"]
        text += f"""
Map: {map_info.get('name', 'unknown')}, explored {map_info.get('exploration_percent', 0):.1f}%"""

    return text

# ─── CHAT MESSAGE STORAGE (POSTGRESQL) ───────────────────────
def add_mcp_message(message_data: Dict[str, Any]) -> str:
    """Store MCP chat messages in PostgreSQL"""
    try:
        message_id = str(uuid4())
        
        # Determine message type
        message_type = determine_message_type(message_data)
        robot_id = message_data.get("robot_id") or message_data.get("agent_id")
        
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO mcp_message_chains (id, message_chain, message_type, robot_id, timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    message_id,
                    Json(message_data),
                    message_type,
                    robot_id,
                    message_data.get("timestamp", datetime.now().isoformat())
                ))
            conn.commit()
        
        logger.info(f"💬 MCP message stored: {message_id} (type: {message_type})")
        return message_id
        
    except Exception as e:
        logger.error(f"❌ Failed to store MCP message: {e}")
        raise

def determine_message_type(message_data: Dict[str, Any]) -> str:
    """Determine the type of message for categorization"""
    source = message_data.get("source", "")
    role = message_data.get("role", "")
    
    if "command" in message_data:
        return "navigation_command"
    elif role == "user":
        return "user_query"  
    elif role == "assistant":
        return "assistant_response"
    elif source == "mcp":
        return "mcp_action"
    elif "error" in message_data:
        return "error_log"
    else:
        return "general"

# ─── NAVIGATION COMMAND STORAGE ──────────────────────────────
def add_navigation_command(robot_id: str, command_type: str, command_data: Dict[str, Any]) -> str:
    """Store navigation commands with status tracking"""
    try:
        command_id = str(uuid4())
        
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO navigation_commands (id, robot_id, command_type, command_data, status)
                    VALUES (%s, %s, %s, %s, %s)
                """, (command_id, robot_id, command_type, Json(command_data), "pending"))
            conn.commit()
            
        logger.info(f"🎯 Navigation command stored: {command_id} for {robot_id}")
        return command_id
        
    except Exception as e:
        logger.error(f"❌ Failed to store navigation command: {e}")
        raise

def update_command_status(command_id: str, status: str, response_data: Optional[Dict[str, Any]] = None):
    """Update navigation command status and response"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                if response_data:
                    cur.execute("""
                        UPDATE navigation_commands 
                        SET status = %s, response_data = %s, completed_at = %s
                        WHERE id = %s
                    """, (status, Json(response_data), datetime.now(), command_id))
                else:
                    cur.execute("""
                        UPDATE navigation_commands 
                        SET status = %s, completed_at = %s
                        WHERE id = %s
                    """, (status, datetime.now(), command_id))
            conn.commit()
            
    except Exception as e:
        logger.error(f"❌ Failed to update command status: {e}")

# ─── SLAM MAP DATA STORAGE ───────────────────────────────────
def store_slam_map(robot_id: str, map_name: str, map_data: Dict[str, Any], 
                   waypoints: Optional[List[Dict]] = None, obstacles: Optional[List[Dict]] = None) -> str:
    """Store SLAM map data and waypoints"""
    try:
        map_id = str(uuid4())
        
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO slam_map_data (id, robot_id, map_name, map_data, waypoints, obstacles)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    map_id, robot_id, map_name, 
                    Json(map_data), Json(waypoints or []), Json(obstacles or [])
                ))
            conn.commit()
            
        logger.info(f"🗺️  SLAM map stored: {map_id} for {robot_id}")
        return map_id
        
    except Exception as e:
        logger.error(f"❌ Failed to store SLAM map: {e}")
        raise

# ─── RETRIEVAL FUNCTIONS ─────────────────────────────────────
def retrieve_slam_telemetry(query: str, robot_id: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """Retrieve SLAM telemetry using vector similarity search"""
    try:
        query_vector = model.encode(query).tolist()
        
        # Build filter if robot_id specified
        query_filter = None
        if robot_id:
            query_filter = Filter(
                must=[FieldCondition(key="robot_id", match=MatchValue(value=robot_id))]
            )
        
        results = qdrant_client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter
        )
        
        return [{"id": r.id, "score": r.score, "payload": r.payload} for r in results]
        
    except Exception as e:
        logger.error(f"❌ Failed to retrieve SLAM telemetry: {e}")
        return []

def get_recent_chat_messages(robot_id: Optional[str] = None, message_type: Optional[str] = None, 
                           limit: int = 50) -> List[Dict]:
    """Retrieve recent chat messages from PostgreSQL"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM mcp_message_chains WHERE 1=1"
                params = []
                
                if robot_id:
                    query += " AND robot_id = %s"
                    params.append(robot_id)
                    
                if message_type:
                    query += " AND message_type = %s" 
                    params.append(message_type)
                    
                query += " ORDER BY timestamp DESC LIMIT %s"
                params.append(limit)
                
                cur.execute(query, params)
                rows = cur.fetchall()
                
                return [dict(row) for row in rows]
                
    except Exception as e:
        logger.error(f"❌ Failed to retrieve chat messages: {e}")
        return []

def get_navigation_commands(robot_id: str, status: Optional[str] = None, limit: int = 20) -> List[Dict]:
    """Get navigation commands for a robot"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if status:
                    cur.execute("""
                        SELECT * FROM navigation_commands 
                        WHERE robot_id = %s AND status = %s
                        ORDER BY issued_at DESC LIMIT %s
                    """, (robot_id, status, limit))
                else:
                    cur.execute("""
                        SELECT * FROM navigation_commands 
                        WHERE robot_id = %s
                        ORDER BY issued_at DESC LIMIT %s
                    """, (robot_id, limit))
                    
                rows = cur.fetchall()
                return [dict(row) for row in rows]
                
    except Exception as e:
        logger.error(f"❌ Failed to retrieve navigation commands: {e}")
        return []

def get_slam_maps(robot_id: str) -> List[Dict]:
    """Get SLAM maps for a robot"""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM slam_map_data 
                    WHERE robot_id = %s
                    ORDER BY updated_at DESC
                """, (robot_id,))
                
                rows = cur.fetchall()
                return [dict(row) for row in rows]
                
    except Exception as e:
        logger.error(f"❌ Failed to retrieve SLAM maps: {e}")
        return []

# ─── ANALYTICS AND REPORTING ─────────────────────────────────
def get_robot_telemetry_summary(robot_id: str, hours: int = 24) -> Dict[str, Any]:
    """Get telemetry summary for a robot over specified time period"""
    try:
        since_time = datetime.now() - timedelta(hours=hours)
        
        results = qdrant_client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="robot_id", match=MatchValue(value=robot_id)),
                    FieldCondition(key="timestamp", range={"gte": since_time.isoformat()})
                ]
            ),
            limit=1000,
            with_payload=True,
            with_vectors=False
        )
        
        records = results[0]
        
        if not records:
            return {"robot_id": robot_id, "records": 0, "summary": "No data available"}
            
        # Calculate statistics
        positions = [(r.payload["position_x"], r.payload["position_y"]) for r in records]
        batteries = [r.payload["battery_level"] for r in records]
        obstacles = [r.payload["obstacle_distance"] for r in records]
        
        # Calculate total distance traveled
        total_distance = 0
        for i in range(1, len(positions)):
            x1, y1 = positions[i-1]
            x2, y2 = positions[i]
            total_distance += np.sqrt((x2-x1)**2 + (y2-y1)**2)
        
        summary = {
            "robot_id": robot_id,
            "time_period_hours": hours,
            "total_records": len(records),
            "distance_traveled_m": round(total_distance, 2),
            "battery_stats": {
                "current": batteries[-1] if batteries else 0,
                "min": min(batteries) if batteries else 0,
                "max": max(batteries) if batteries else 0,
                "avg": round(sum(batteries)/len(batteries), 1) if batteries else 0
            },
            "obstacle_stats": {
                "min_distance": round(min(obstacles), 2) if obstacles else 0,
                "avg_distance": round(sum(obstacles)/len(obstacles), 2) if obstacles else 0
            },
            "current_position": positions[-1] if positions else (0, 0),
            "status_distribution": {}
        }
        
        # Status distribution
        statuses = [r.payload["status"] for r in records]
        for status in set(statuses):
            summary["status_distribution"][status] = statuses.count(status)
            
        return summary
        
    except Exception as e:
        logger.error(f"❌ Failed to generate telemetry summary: {e}")
        return {"error": str(e)}

# ─── MAINTENANCE FUNCTIONS ───────────────────────────────────
def cleanup_old_data(days_to_keep: int = 30):
    """Clean up old data from both PostgreSQL and Qdrant"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        # Clean PostgreSQL
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                # Clean old messages
                cur.execute("""
                    DELETE FROM mcp_message_chains 
                    WHERE created_at < %s
                """, (cutoff_date,))
                
                # Clean old commands
                cur.execute("""
                    DELETE FROM navigation_commands 
                    WHERE issued_at < %s AND status IN ('completed', 'failed')
                """, (cutoff_date,))
                
            conn.commit()
        
        # Clean Qdrant (requires scrolling through all points)
        # This is a simplified approach - in production you might want batch processing
        old_points = qdrant_client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="timestamp", range={"lt": cutoff_date.isoformat()})]
            ),
            limit=1000,
            with_payload=False,
            with_vectors=False
        )[0]
        
        if old_points:
            point_ids = [p.id for p in old_points]
            qdrant_client.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=point_ids
            )
            
        logger.info(f"🧹 Cleaned up data older than {days_to_keep} days")
        
    except Exception as e:
        logger.error(f"❌ Failed to cleanup old data: {e}")

# ─── HEALTH CHECK ────────────────────────────────────────────
def health_check() -> Dict[str, Any]:
    """Check health of both storage systems"""
    try:
        # Test PostgreSQL
        pg_status = "healthy"
        pg_message = ""
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM mcp_message_chains")
                    message_count = cur.fetchone()[0]
        except Exception as e:
            pg_status = "unhealthy"
            pg_message = str(e)
            message_count = 0
            
        # Test Qdrant
        qdrant_status = "healthy"
        qdrant_message = ""
        telemetry_count = 0
        try:
            collection_info = qdrant_client.get_collection(QDRANT_COLLECTION)
            telemetry_count = collection_info.points_count
        except Exception as e:
            qdrant_status = "unhealthy" 
            qdrant_message = str(e)
            
        return {
            "timestamp": datetime.now().isoformat(),
            "postgresql": {
                "status": pg_status,
                "message": pg_message,
                "message_count": message_count
            },
            "qdrant": {
                "status": qdrant_status,
                "message": qdrant_message,
                "telemetry_count": telemetry_count
            },
            "overall_status": "healthy" if pg_status == "healthy" and qdrant_status == "healthy" else "degraded"
        }
        
    except Exception as e:
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "overall_status": "unhealthy"
        }