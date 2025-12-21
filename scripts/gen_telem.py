#!/usr/bin/env python3
"""
Telemetry Generator for WayfindR-LLM
Simulates robot telemetry for testing
"""
import requests
import time
import random
from datetime import datetime

# Configuration
API_URL = "http://localhost:5000"
ROBOT_ID = "robot_01"
WAYPOINTS = [
    "reception",
    "lobby",
    "cafeteria",
    "meeting_room_a",
    "meeting_room_b",
    "conference_hall",
    "elevator",
    "restroom",
    "exit",
    "main_hall",
]

STATUSES = ["idle", "navigating", "idle", "idle", "navigating"]


def generate_telemetry():
    """Generate random telemetry data"""
    return {
        "robot_id": ROBOT_ID,
        "telemetry": {
            "status": random.choice(STATUSES),
            "battery": random.randint(20, 100),
            "current_location": random.choice(WAYPOINTS),
            "destination": random.choice(WAYPOINTS) if random.random() > 0.5 else None,
            "position": {
                "x": round(random.uniform(-10, 10), 2),
                "y": round(random.uniform(-10, 10), 2)
            },
            "sensors": {
                "lidar_front": round(random.uniform(0.5, 5.0), 2),
                "lidar_rear": round(random.uniform(0.5, 5.0), 2),
                "ultrasonic": round(random.uniform(0.1, 2.0), 2)
            },
            "timestamp": datetime.now().isoformat()
        }
    }


def send_telemetry(data):
    """Send telemetry to API"""
    try:
        response = requests.post(
            f"{API_URL}/telemetry",
            json=data,
            timeout=5
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 50)
    print("WayfindR Telemetry Generator")
    print("=" * 50)
    print(f"Robot ID: {ROBOT_ID}")
    print(f"API URL: {API_URL}")
    print("Sending telemetry every 2 seconds...")
    print("Press Ctrl+C to stop")
    print("=" * 50)

    count = 0
    while True:
        try:
            count += 1
            data = generate_telemetry()

            print(f"\n[{count}] Sending telemetry...")
            print(f"  Status: {data['telemetry']['status']}")
            print(f"  Location: {data['telemetry']['current_location']}")
            print(f"  Battery: {data['telemetry']['battery']}%")

            result = send_telemetry(data)

            if result.get('success'):
                print(f"  Result: OK (point_id: {result.get('point_id', 'N/A')[:8]})")
            else:
                print(f"  Result: ERROR - {result.get('error', 'Unknown')}")

            time.sleep(2)

        except KeyboardInterrupt:
            print("\n\nStopping telemetry generator...")
            break
        except Exception as e:
            print(f"\nError: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
