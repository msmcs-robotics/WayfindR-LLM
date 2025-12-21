"""
Streaming endpoints for real-time log updates.
For WayfindR-LLM Tour Guide Robot System
"""
import json
import asyncio
from datetime import datetime
from collections import deque
from fastapi.responses import StreamingResponse

# Import storage backends
try:
    from rag.qdrant_store import qdrant_client, TELEMETRY_COLLECTION
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    qdrant_client = None
    TELEMETRY_COLLECTION = "robot_telemetry"

try:
    from rag.postgresql_store import get_messages_by_type
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False


def normalize_timestamp_to_iso(ts) -> str:
    """Normalize any timestamp format to ISO string"""
    if isinstance(ts, str):
        return ts
    elif isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts).isoformat()
        except (ValueError, OSError):
            return datetime.now().isoformat()
    elif isinstance(ts, datetime):
        return ts.isoformat()
    else:
        return datetime.now().isoformat()


def fetch_logs_from_qdrant(limit=200):
    """Fetch telemetry logs from Qdrant, sorted by timestamp (newest first)"""
    if not QDRANT_AVAILABLE or not qdrant_client:
        return []

    try:
        results = qdrant_client.scroll(
            collection_name=TELEMETRY_COLLECTION,
            limit=limit * 2,
            with_payload=True,
            with_vectors=False
        )[0]

        logs = []
        for point in results:
            point_id = str(point.id)
            payload = point.payload
            raw_timestamp = payload.get('timestamp', datetime.now())
            iso_timestamp = normalize_timestamp_to_iso(raw_timestamp)

            log = {
                '_point_id': point_id,
                'log_id': point_id[:8],
                'text': payload.get('text', ''),
                'metadata': {
                    'robot_id': payload.get('robot_id'),
                    'status': payload.get('status'),
                    'battery': payload.get('battery'),
                    'current_location': payload.get('current_location'),
                    'destination': payload.get('destination'),
                    'timestamp': iso_timestamp
                },
                'created_at': iso_timestamp,
                'source': 'qdrant',
                '_sort_key': raw_timestamp
            }

            logs.append(log)

        # Sort by timestamp (newest first)
        try:
            logs.sort(key=lambda x: x['_sort_key'], reverse=True)
        except Exception as e:
            print(f"[STREAMING] Warning: Could not sort Qdrant logs: {e}")

        return logs[:limit]

    except Exception as e:
        print(f"[STREAMING] Error fetching from Qdrant: {e}")
        return []


async def get_qdrant_data():
    """Get recent Qdrant data - ASYNC version"""
    logs = fetch_logs_from_qdrant(limit=100)

    # Remove internal keys before sending
    for log in logs:
        log.pop('_point_id', None)
        log.pop('_sort_key', None)

    return logs


async def get_postgresql_data():
    """Get recent PostgreSQL data - ASYNC version"""
    if not POSTGRESQL_AVAILABLE:
        return []

    try:
        user_msgs = get_messages_by_type('command', limit=25)
        llm_msgs = get_messages_by_type('response', limit=25)
        error_msgs = get_messages_by_type('error', limit=25)
        notif_msgs = get_messages_by_type('notification', limit=25)

        messages = user_msgs + llm_msgs + error_msgs + notif_msgs

        formatted = []
        for msg in messages:
            formatted.append({
                'log_id': str(msg['id'])[:8],
                'text': msg['text'],
                'metadata': msg.get('metadata', {}),
                'created_at': msg.get('created_at', datetime.now()).isoformat()
                             if isinstance(msg.get('created_at'), datetime)
                             else str(msg.get('created_at', '')),
                'source': 'postgresql'
            })

        return formatted
    except Exception as e:
        print(f"[DATA] Error fetching PostgreSQL data: {e}")
        return []


async def stream_qdrant():
    """Stream Qdrant telemetry logs in real-time with sliding window deduplication"""
    async def event_generator():
        seen_point_ids = deque(maxlen=500)
        check_count = 0
        initial_load_done = False

        print("[STREAMING] Qdrant stream generator started")

        while True:
            try:
                check_count += 1

                logs = fetch_logs_from_qdrant(limit=200)

                new_logs = [
                    log for log in logs
                    if log.get('_point_id') not in seen_point_ids
                ]

                if check_count == 1 or check_count % 10 == 0:
                    print(f"[STREAMING] Qdrant check #{check_count}: "
                          f"fetched {len(logs)}, {len(new_logs)} new")

                if new_logs:
                    for log in new_logs:
                        point_id = log.get('_point_id')
                        if point_id:
                            seen_point_ids.append(point_id)

                        log_copy = log.copy()
                        log_copy.pop('_point_id', None)
                        log_copy.pop('_sort_key', None)

                        yield f"data: {json.dumps(log_copy)}\n\n"

                    if not initial_load_done:
                        initial_load_done = True
                        print(f"[STREAMING] Qdrant: Initial load complete ({len(new_logs)} logs)")

                await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                print("[STREAMING] Qdrant stream cancelled")
                break
            except Exception as e:
                print(f"[STREAMING] Error in Qdrant stream: {e}")
                await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


async def stream_postgresql():
    """Stream PostgreSQL logs in real-time with sliding window"""
    async def event_generator():
        seen_ids = deque(maxlen=500)
        check_count = 0

        print("[STREAMING] PostgreSQL stream generator started")

        while True:
            try:
                check_count += 1

                messages = []
                if POSTGRESQL_AVAILABLE:
                    try:
                        user_msgs = get_messages_by_type('command', limit=50)
                        llm_msgs = get_messages_by_type('response', limit=50)
                        error_msgs = get_messages_by_type('error', limit=50)
                        notif_msgs = get_messages_by_type('notification', limit=50)

                        messages = user_msgs + llm_msgs + error_msgs + notif_msgs
                    except Exception as e:
                        print(f"[STREAMING] Error fetching PostgreSQL messages: {e}")

                new_messages = [
                    msg for msg in messages
                    if str(msg['id']) not in seen_ids
                ]

                if check_count == 1 or check_count % 10 == 0:
                    print(f"[STREAMING] PostgreSQL check #{check_count}: "
                          f"fetched {len(messages)}, {len(new_messages)} new")

                for msg in new_messages:
                    msg_id = str(msg['id'])
                    seen_ids.append(msg_id)

                    log_entry = {
                        'log_id': msg_id[:8],
                        'text': msg['text'],
                        'metadata': msg.get('metadata', {}),
                        'created_at': msg.get('created_at', datetime.now()).isoformat()
                                     if isinstance(msg.get('created_at'), datetime)
                                     else str(msg.get('created_at', '')),
                        'source': 'postgresql'
                    }

                    yield f"data: {json.dumps(log_entry)}\n\n"

                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                print("[STREAMING] PostgreSQL stream cancelled")
                break
            except Exception as e:
                print(f"[STREAMING] Error in PostgreSQL stream: {e}")
                await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


__all__ = [
    'stream_qdrant',
    'stream_postgresql',
    'get_qdrant_data',
    'get_postgresql_data'
]
