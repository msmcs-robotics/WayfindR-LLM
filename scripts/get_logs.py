#!/usr/bin/env python3
"""
Simple log viewer for the Robot Guidance System
Fetches and displays logs from both PostgreSQL (chat) and Qdrant (telemetry) in a readable format
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from qdrant_client import QdrantClient
from datetime import datetime
import json

# Configuration (matching your system)
DB_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres", 
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
TELEMETRY_COLLECTION = "robot_telemetry"

def print_header(title):
    """Print a nice header"""
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)

def print_separator():
    """Print a separator line"""
    print("-" * 60)

def get_chat_logs(limit=20):
    """Fetch recent chat messages from PostgreSQL"""
    try:
        with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        id, role, content, timestamp, user_id, metadata
                    FROM chat_messages 
                    ORDER BY timestamp DESC 
                    LIMIT %s;
                """, (limit,))
                
                return cur.fetchall()
    except Exception as e:
        print(f"❌ Error fetching chat logs: {e}")
        return []

def get_telemetry_logs(limit=20):
    """Fetch recent telemetry data from Qdrant"""
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        
        # Check if collection exists
        if not client.collection_exists(TELEMETRY_COLLECTION):
            print(f"⚠️  Collection '{TELEMETRY_COLLECTION}' does not exist")
            return []
        
        # Get recent points using scroll
        scroll_result = client.scroll(
            collection_name=TELEMETRY_COLLECTION,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )
        
        return scroll_result[0]  # Return points (first element of tuple)
        
    except Exception as e:
        print(f"❌ Error fetching telemetry logs: {e}")
        return []

def display_chat_logs(chat_logs):
    """Display chat logs in a readable format"""
    print_header("CHAT LOGS (PostgreSQL)")
    
    if not chat_logs:
        print("No chat messages found.")
        return
    
    print(f"📝 Found {len(chat_logs)} chat messages")
    print()
    
    for i, msg in enumerate(reversed(chat_logs), 1):  # Show oldest first
        timestamp = msg['timestamp'].strftime("%Y-%m-%d %H:%M:%S") if msg['timestamp'] else "Unknown"
        role_emoji = {"user": "👤", "assistant": "🤖", "robot": "🦾"}.get(msg['role'], "❓")
        
        print(f"{i:2d}. [{timestamp}] {role_emoji} {msg['role'].upper()}")
        if msg['user_id']:
            print(f"    User ID: {msg['user_id']}")
        
        # Truncate long messages
        content = msg['content']
        if len(content) > 200:
            content = content[:200] + "..."
        
        # Print content with indentation
        for line in content.split('\n'):
            print(f"    {line}")
        
        if msg['metadata']:
            print(f"    📋 Metadata: {json.dumps(msg['metadata'], indent=6)}")
        
        print()

def display_telemetry_logs(telemetry_logs):
    """Display telemetry logs in a readable format"""
    print_header("TELEMETRY LOGS (Qdrant)")
    
    if not telemetry_logs:
        print("No telemetry data found.")
        return
    
    print(f"📡 Found {len(telemetry_logs)} telemetry points")
    print()
    
    # Group by robot_id and sort by timestamp
    robot_data = {}
    for point in telemetry_logs:
        robot_id = point.payload.get("robot_id", "unknown")
        if robot_id not in robot_data:
            robot_data[robot_id] = []
        robot_data[robot_id].append(point)
    
    # Sort each robot's data by timestamp
    for robot_id in robot_data:
        robot_data[robot_id].sort(
            key=lambda x: x.payload.get("timestamp", ""), 
            reverse=True
        )
    
    # Display by robot
    for robot_id, points in robot_data.items():
        print(f"🦾 ROBOT: {robot_id}")
        print_separator()
        
        for i, point in enumerate(points, 1):
            payload = point.payload
            telemetry = payload.get("telemetry", {})
            
            timestamp = payload.get("timestamp", "Unknown")
            if timestamp != "Unknown":
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
            
            print(f"  {i:2d}. [{timestamp}]")
            
            # Position info
            pos = telemetry.get("position", {})
            exp_pos = telemetry.get("expected_position", {})
            print(f"      📍 Position: ({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f})")
            print(f"      🎯 Expected: ({exp_pos.get('x', 0):.2f}, {exp_pos.get('y', 0):.2f})")
            
            # Movement info
            speed = telemetry.get("movement_speed", 0)
            distance = telemetry.get("distance_traveled", 0)
            print(f"      🏃 Speed: {speed:.2f} m/s, Distance: {distance:.2f}m")
            
            # Navigation info
            current_wp = telemetry.get("current_waypoint", "none")
            target_wp = telemetry.get("target_waypoint", "none")
            nav_status = telemetry.get("navigation_status", "unknown")
            stuck = telemetry.get("is_stuck", False)
            
            status_emoji = "🔴" if stuck else "🟢"
            print(f"      {status_emoji} Status: {nav_status}")
            print(f"      🚩 Route: {current_wp} → {target_wp}")
            
            if stuck:
                print(f"      ⚠️  ROBOT IS STUCK!")
            
            print()
        
        print()

def get_system_stats():
    """Get basic system statistics"""
    print_header("SYSTEM STATISTICS")
    
    # Chat stats
    try:
        with psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_messages,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(CASE WHEN role = 'user' THEN 1 END) as user_messages,
                        COUNT(CASE WHEN role = 'assistant' THEN 1 END) as assistant_messages,
                        COUNT(CASE WHEN role = 'robot' THEN 1 END) as robot_messages,
                        MAX(timestamp) as last_message
                    FROM chat_messages;
                """)
                
                stats = dict(cur.fetchone())
                
                print("📊 CHAT DATABASE (PostgreSQL):")
                print(f"   Total Messages: {stats['total_messages']}")
                print(f"   Unique Users: {stats['unique_users']}")
                print(f"   User Messages: {stats['user_messages']}")
                print(f"   Assistant Messages: {stats['assistant_messages']}")
                print(f"   Robot Messages: {stats['robot_messages']}")
                
                if stats['last_message']:
                    last_msg = stats['last_message'].strftime("%Y-%m-%d %H:%M:%S")
                    print(f"   Last Message: {last_msg}")
                
    except Exception as e:
        print(f"❌ Error getting chat stats: {e}")
    
    # Telemetry stats
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        
        if client.collection_exists(TELEMETRY_COLLECTION):
            collection_info = client.get_collection(TELEMETRY_COLLECTION)
            
            # Get unique robots
            scroll_result = client.scroll(
                collection_name=TELEMETRY_COLLECTION,
                limit=100,
                with_payload=True,
                with_vectors=False
            )
            
            unique_robots = set()
            for point in scroll_result[0]:
                robot_id = point.payload.get("robot_id")
                if robot_id:
                    unique_robots.add(robot_id)
            
            print("\n📡 TELEMETRY DATABASE (Qdrant):")
            print(f"   Total Points: {collection_info.vectors_count}")
            print(f"   Unique Robots: {len(unique_robots)}")
            print(f"   Robots: {', '.join(sorted(unique_robots))}")
            print(f"   Collection Status: {collection_info.status}")
            
        else:
            print("\n📡 TELEMETRY DATABASE (Qdrant):")
            print("   Collection does not exist")
            
    except Exception as e:
        print(f"❌ Error getting telemetry stats: {e}")

def main():
    """Main function to display all logs"""
    print("🔍 Robot Guidance System - Log Viewer")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Get system statistics
    get_system_stats()
    
    # Get and display chat logs
    chat_logs = get_chat_logs(limit=20)
    display_chat_logs(chat_logs)
    
    # Get and display telemetry logs
    telemetry_logs = get_telemetry_logs(limit=20)
    display_telemetry_logs(telemetry_logs)
    
    print_header("LOG VIEWING COMPLETE")
    print("💡 Tip: Run with 'python log_viewer.py' to refresh logs")

if __name__ == "__main__":
    main()