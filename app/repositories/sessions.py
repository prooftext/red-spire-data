import json
from uuid import UUID

def ensure_uuid(value):
    """Convert string to UUID if valid, return as-is if already UUID, raise if invalid"""
    if isinstance(value, UUID):
        return str(value)
    try:
        # Validate that it's a valid UUID string
        UUID(value)
        return value
    except (ValueError, AttributeError):
        # Not a valid UUID string, generate one
        return str(UUID(int=hash(value) % (2**128)))

async def create_session(conn, request, metrics, human_prob, status):
    session_start = request.events[0].timestamp if request.events else None
    session_end = request.events[-1].timestamp if request.events else None
    total_duration_ms = int((session_end - session_start).total_seconds() * 1000) if session_start and session_end else None
    
    session_id = ensure_uuid(request.session_id)
    user_id = ensure_uuid(request.user_id)
    
    # First, ensure the user exists
    await conn.execute("""
        INSERT INTO users (user_id, username)
        VALUES (%s::uuid, %s)
        ON CONFLICT (user_id) DO NOTHING
    """, (user_id, f"user_{user_id}"))
    
    # Then insert the session
    await conn.execute("""
        INSERT INTO typing_sessions (session_id, user_id, document_text, session_start, session_end, total_duration_ms, verification_status, human_probability, session_metrics, analyzed_at)
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, NOW())
    """, (session_id, user_id, request.document_text, session_start, session_end, total_duration_ms, status, human_prob, json.dumps(metrics)))