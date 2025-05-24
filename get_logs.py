# get_logs.py
import psycopg2
import json
from qdrant_client import QdrantClient
from psycopg2.extras import Json

# Configuration matching your docker-compose setup
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
POSTGRES_CONFIG = {
    "dbname": "rag_db",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}
QDRANT_COLLECTION = "telemetry_data"

def print_qdrant_logs():
    """Query and print all logs from Qdrant"""
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        
        print("\n" + "="*50 + "\nQdrant Logs\n" + "="*50)
        records = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=100,
            with_payload=True,
            with_vectors=False
        )[0]

        if not records:
            print("No Qdrant records found")
            return

        for i, record in enumerate(records, 1):
            print(f"\nRecord #{i}")
            print(f"ID: {record.id}")
            print("Payload:")
            print(json.dumps(record.payload, indent=2))
            print("-" * 50)

    except Exception as e:
        print(f"Error accessing Qdrant: {e}")

def print_postgres_logs():
    """Query and print all PostgreSQL logs"""
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        
        print("\n" + "="*50 + "\nPostgreSQL Logs\n" + "="*50)
        
        with conn.cursor() as cur:
            # Agent Relationships
            cur.execute("SELECT * FROM agent_relationships;")
            print("\nAgent Relationships:")
            for row in cur.fetchall():
                print(f"\nID: {row[0]}")
                print(f"Agent ID: {row[1]}")
                print(f"Created At: {row[3]}")
                print("Relationship:")
                print(json.dumps(row[2], indent=2))
                print("-" * 50)

            # MCP Message Chains
            cur.execute("SELECT * FROM mcp_message_chains;")
            print("\nMCP Message Chains:")
            for row in cur.fetchall():
                print(f"\nID: {row[0]}")
                print(f"Created At: {row[2]}")
                print("Message Chain:")
                print(json.dumps(row[1], indent=2))
                print("-" * 50)

    except Exception as e:
        print(f"Error accessing PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print_qdrant_logs()
    
    input("\nPress Enter to view PostgreSQL logs...")
    
    print_postgres_logs()
    print("\nLog review complete!")