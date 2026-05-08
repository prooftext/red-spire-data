from app.database import get_pool
import json
from uuid import UUID, NAMESPACE_URL, uuid5

def ensure_uuid(value):
    """Convert string to UUID if valid, return as-is if already UUID, raise if invalid"""
    if isinstance(value, UUID):
        return str(value)
    try:
        # Validate that it's a valid UUID string
        UUID(value)
        return value
    except (ValueError, AttributeError, TypeError):
        # Not a valid UUID string: map deterministically to UUID5.
        return str(uuid5(NAMESPACE_URL, f"prooftext:{value}"))

async def bulk_insert_events(session_id: str, user_id: str, events):
    pool = get_pool()
    session_id = ensure_uuid(session_id)
    user_id = ensure_uuid(user_id)
    async with pool.connection() as conn:
        for event in events:
            # Use Pydantic's model_dump_json which handles datetime serialization
            event_data = json.loads(event.model_dump_json())
            await conn.execute("""
                INSERT INTO keystroke_events (session_id, user_id, event_time, event_type, sequence_number, cursor_position, text_length, event_data)
                VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s)
            """, (session_id, user_id, event.timestamp, event.eventType, event.sequence, event.cursorPosition, None, json.dumps(event_data)))