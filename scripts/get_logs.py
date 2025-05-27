#!/usr/bin/env python3
"""
Database inspection tool for Robot Guidance System
Displays contents of both PostgreSQL and Qdrant databases
"""

import psycopg2
from qdrant_client import QdrantClient
import json
from datetime import datetime
import argparse

# Database configurations
DB_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

QDRANT_CONFIG = {
    "host": "localhost",
    "port": 6333
}

def get_postgres_logs():
    """Fetch and display PostgreSQL logs"""
    print("=" * 60)
    print("POSTGRESQL DATABASE CONTENTS")
    print("=" * 60)
    
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                # Get table info
                cur.execute("""
                    SELECT table_name, column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name, ordinal_position;
                """)
                
                print("\n📊 DATABASE SCHEMA:")
                current_table = None
                for row in cur.fetchall():
                    table_name, column_name, data_type = row
                    if table_name != current_table:
                        print(f"\n  Table: {table_name}")
                        current_table = table_name
                    print(f"    - {column_name}: {data_type}")
                
                # Robot telemetry
                print(f"\n🤖 ROBOT TELEMETRY:")
                cur.execute("""
                    SELECT robot_id, timestamp, position_x, position_y, 
                           is_stuck, current_waypoint, target_waypoint, navigation_status
                    FROM robot_telemetry 
                    ORDER BY timestamp DESC 
                    LIMIT 20;
                """)
                
                telemetry_rows = cur.fetchall()
                if telemetry_rows:
                    print(f"  Recent {len(telemetry_rows)} entries:")
                    for row in telemetry_rows:
                        robot_id, timestamp, pos_x, pos_y, stuck, current_wp, target_wp, status = row
                        stuck_indicator = "🔴 STUCK" if stuck else "🟢"
                        print(f"    {stuck_indicator} {robot_id} @ ({pos_x:.2f}, {pos_y:.2f}) "
                              f"[{current_wp} → {target_wp}] {status} ({timestamp})")
                else:
                    print("  No telemetry data found")
                
                # MCP message chains
                print(f"\n💬 MCP MESSAGE CHAINS:")
                cur.execute("""
                    SELECT id, message_chain, created_at 
                    FROM mcp_message_chains 
                    ORDER BY created_at DESC 
                    LIMIT 15;
                """)
                
                message_rows = cur.fetchall()
                if message_rows:
                    print(f"  Recent {len(message_rows)} messages:")
                    for row in message_rows:
                        msg_id, message_data, created_at = row
                        role = message_data.get("role", "unknown")
                        source = message_data.get("source", "unknown")
                        
                        # Extract message content
                        content = ""
                        for key in ["message", "command", "response"]:
                            if message_data.get(key):
                                content = message_data[key][:60] + "..." if len(message_data[key]) > 60 else message_data[key]
                                break
                        
                        agent_id = message_data.get("agent_id", "")
                        print(f"    [{role}:{source}] {agent_id}: {content} ({created_at})")
                else:
                    print("  No message chains found")
                
                # Agent relationships
                print(f"\n🔗 AGENT RELATIONSHIPS:")
                cur.execute("""
                    SELECT agent_id, relationship, created_at 
                    FROM agent_relationships 
                    ORDER BY created_at DESC 
                    LIMIT 10;
                """)
                
                relationship_rows = cur.fetchall()
                if relationship_rows:
                    print(f"  {len(relationship_rows)} relationships:")
                    for row in relationship_rows:
                        agent_id, relationship, created_at = row
                        print(f"    {agent_id}: {json.dumps(relationship, indent=2)[:100]}... ({created_at})")
                else:
                    print("  No agent relationships found")
                
                # Summary stats
                print(f"\n📈 SUMMARY STATISTICS:")
                cur.execute("SELECT COUNT(*) FROM robot_telemetry;")
                telemetry_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM mcp_message_chains;")
                message_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM agent_relationships;")
                relationship_count = cur.fetchone()[0]
                
                print(f"  Total telemetry entries: {telemetry_count}")
                print(f"  Total message chains: {message_count}")
                print(f"  Total agent relationships: {relationship_count}")
                
    except Exception as e:
        print(f"❌ PostgreSQL Error: {e}")

def get_qdrant_logs():
    """Fetch and display Qdrant vector database contents"""
    print("\n" + "=" * 60)
    print("QDRANT VECTOR DATABASE CONTENTS")
    print("=" * 60)
    
    try:
        client = QdrantClient(**QDRANT_CONFIG)
        
        # Get collections info
        collections = client.get_collections()
        print(f"\n📚 COLLECTIONS ({len(collections.collections)}):")
        
        for collection in collections.collections:
            collection_name = collection.name
            collection_info = client.get_collection(collection_name)
            
            print(f"\n  Collection: {collection_name}")
            print(f"    Vector size: {collection_info.config.params.vectors.size}")
            print(f"    Distance metric: {collection_info.config.params.vectors.distance}")
            print(f"    Points count: {collection_info.points_count}")
            
            # Get sample points
            try:
                scroll_result = client.scroll(
                    collection_name=collection_name,
                    limit=10,
                    with_payload=True,
                    with_vectors=False
                )
                
                points = scroll_result[0]
                if points:
                    print(f"    Sample entries ({len(points)}):")
                    for point in points[:5]:  # Show first 5
                        payload = point.payload
                        
                        if collection_name == "telemetry_data":
                            robot_id = payload.get("robot_id", "unknown")
                            timestamp = payload.get("timestamp", "")
                            searchable_text = payload.get("searchable_text", "")[:80] + "..."
                            print(f"      🤖 {robot_id}: {searchable_text} ({timestamp})")
                            
                        elif collection_name == "chat_context":
                            role = payload.get("role", "unknown")
                            source = payload.get("source", "unknown")
                            searchable_text = payload.get("searchable_text", "")[:80] + "..."
                            timestamp = payload.get("timestamp", "")
                            print(f"      💬 [{role}:{source}]: {searchable_text} ({timestamp})")
                else:
                    print("    No points found")
                    
            except Exception as e:
                print(f"    ❌ Error reading points: {e}")
                
    except Exception as e:
        print(f"❌ Qdrant Error: {e}")

def get_stuck_robots():
    """Show currently stuck robots"""
    print("\n" + "=" * 60)
    print("STUCK ROBOTS ANALYSIS")
    print("=" * 60)
    
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                # Get stuck robots with details
                cur.execute("""
                    WITH latest_status AS (
                        SELECT DISTINCT ON (robot_id) 
                               robot_id, timestamp, is_stuck, position_x, position_y, 
                               current_waypoint, target_waypoint, navigation_status,
                               movement_speed, sensor_data
                        FROM robot_telemetry 
                        ORDER BY robot_id, timestamp DESC
                    )
                    SELECT * FROM latest_status WHERE is_stuck = TRUE;
                """)
                
                stuck_robots = cur.fetchall()
                if stuck_robots:
                    print(f"\n🚨 {len(stuck_robots)} ROBOTS NEED ASSISTANCE:")
                    for robot in stuck_robots:
                        robot_id, timestamp, stuck, pos_x, pos_y, current_wp, target_wp, status, speed, sensor_data = robot
                        print(f"\n  🔴 {robot_id}:")
                        print(f"    Position: ({pos_x:.2f}, {pos_y:.2f})")
                        print(f"    Waypoints: {current_wp} → {target_wp}")
                        print(f"    Status: {status}")
                        print(f"    Speed: {speed:.2f} m/s")
                        print(f"    Last update: {timestamp}")
                        if sensor_data:
                            print(f"    Sensors: {json.dumps(sensor_data, indent=6)}")
                else:
                    print("\n✅ All robots are operating normally")
                    
    except Exception as e:
        print(f"❌ Error checking stuck robots: {e}")

def search_telemetry(query):
    """Search telemetry using semantic similarity"""
    print(f"\n" + "=" * 60)
    print(f"SEMANTIC SEARCH: '{query}'")
    print("=" * 60)
    
    try:
        from sentence_transformers import SentenceTransformer
        
        model = SentenceTransformer("all-MiniLM-L6-v2")
        client = QdrantClient(**QDRANT_CONFIG)
        
        # Search telemetry
        query_vector = model.encode(query).tolist()
        results = client.search(
            collection_name="telemetry_data",
            query_vector=query_vector,
            limit=5,
            score_threshold=0.3
        )
        
        if results:
            print(f"\n🔍 Found {len(results)} relevant telemetry entries:")
            for i, result in enumerate(results, 1):
                payload = result.payload
                print(f"\n  {i}. Score: {result.score:.3f}")
                print(f"     Robot: {payload.get('robot_id')}")
                print(f"     Time: {payload.get('timestamp')}")
                print(f"     Text: {payload.get('searchable_text')}")
        else:
            print(f"\n❌ No relevant telemetry found for: '{query}'")
            
    except Exception as e:
        print(f"❌ Search Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Inspect Robot Guidance System databases")
    parser.add_argument("--postgres", "-p", action="store_true", help="Show PostgreSQL logs")
    parser.add_argument("--qdrant", "-q", action="store_true", help="Show Qdrant logs")
    parser.add_argument("--stuck", "-s", action="store_true", help="Show stuck robots")
    parser.add_argument("--search", "-S", type=str, help="Search telemetry semantically")
    parser.add_argument("--all", "-a", action="store_true", help="Show all logs")
    
    args = parser.parse_args()
    
    if not any([args.postgres, args.qdrant, args.stuck, args.search, args.all]):
        args.all = True
    
    print(f"🤖 Robot Guidance System Database Inspector")
    print(f"Generated at: {datetime.now().isoformat()}")
    
    if args.all or args.postgres:
        get_postgres_logs()
    
    if args.all or args.qdrant:
        get_qdrant_logs()
    
    if args.all or args.stuck:
        get_stuck_robots()
    
    if args.search:
        search_telemetry(args.search)

if __name__ == "__main__":
    main()