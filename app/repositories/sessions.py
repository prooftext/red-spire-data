import json
import hashlib
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

async def session_exists(conn, session_id):
    """Check if a session already exists"""
    session_id = ensure_uuid(session_id)
    result = await conn.execute("""
        SELECT session_id FROM typing_sessions WHERE session_id = %s::uuid
    """, (session_id,))
    return await result.fetchone() is not None

async def create_or_merge_session(conn, request, metrics, human_prob, status):
    """Create a new session or merge with existing session if it already exists"""
    session_start = request.events[0].timestamp if request.events else None
    session_end = request.events[-1].timestamp if request.events else None
    total_duration_ms = int((session_end - session_start).total_seconds() * 1000) if session_start and session_end else None
    
    session_id = ensure_uuid(request.session_id)
    user_id = ensure_uuid(request.user_id)
    # Deterministic document identifier derived from document_text
    document_id = None
    if getattr(request, "document_text", None):
        document_id = hashlib.md5(request.document_text.encode("utf-8")).hexdigest()
    
    # First, ensure the user exists
    await conn.execute("""
        INSERT INTO users (user_id, username)
        VALUES (%s::uuid, %s)
        ON CONFLICT (user_id) DO NOTHING
    """, (user_id, f"user_{user_id}"))
    
    # Check if session exists
    if await session_exists(conn, session_id):
        # Merge with existing session: update the end time, duration, and recalculated metrics
        # Try with document_id, fall back without if column doesn't exist
        try:
            await conn.execute("""
                UPDATE typing_sessions
                SET session_end = %s,
                    total_duration_ms = %s,
                    human_probability = %s,
                    verification_status = %s,
                    session_metrics = %s,
                    document_id = COALESCE(document_id, %s),
                    analyzed_at = NOW()
                WHERE session_id = %s::uuid
            """, (session_end, total_duration_ms, human_prob, status, json.dumps(metrics), document_id, session_id))
        except Exception as e:
            # If document_id column doesn't exist, update without it
            if "document_id" in str(e):
                await conn.execute("""
                    UPDATE typing_sessions
                    SET session_end = %s,
                        total_duration_ms = %s,
                        human_probability = %s,
                        verification_status = %s,
                        session_metrics = %s,
                        analyzed_at = NOW()
                    WHERE session_id = %s::uuid
                """, (session_end, total_duration_ms, human_prob, status, json.dumps(metrics), session_id))
            else:
                raise
    else:
        # Create new session
        # Try to insert with document_id, fall back to without if column doesn't exist
        try:
            await conn.execute("""
                INSERT INTO typing_sessions (session_id, user_id, document_text, document_id, session_start, session_end, total_duration_ms, verification_status, human_probability, session_metrics, analyzed_at)
                VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (session_id, user_id, request.document_text, document_id, session_start, session_end, total_duration_ms, status, human_prob, json.dumps(metrics)))
        except Exception as e:
            # If document_id column doesn't exist, insert without it
            if "document_id" in str(e):
                await conn.execute("""
                    INSERT INTO typing_sessions (session_id, user_id, document_text, session_start, session_end, total_duration_ms, verification_status, human_probability, session_metrics, analyzed_at)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (session_id, user_id, request.document_text, session_start, session_end, total_duration_ms, status, human_prob, json.dumps(metrics)))
            else:
                raise

async def get_session_metadata(conn, session_id: str):
    """Return basic metadata for a session: session_id, user_id, document_id and timestamps"""
    sid = ensure_uuid(session_id)
    result = await conn.execute("""
        SELECT session_id::text, user_id::text, document_id, session_start, session_end, analyzed_at
        FROM typing_sessions
        WHERE session_id = %s::uuid
    """, (sid,))
    row = await result.fetchone()
    if not row:
        return None
    return {
        "session_id": row[0],
        "user_id": row[1],
        "document_id": row[2],
        "session_start": row[3].isoformat() if row[3] else None,
        "session_end": row[4].isoformat() if row[4] else None,
        "analyzed_at": row[5].isoformat() if row[5] else None,
    }

async def get_last_session_id_by_document(conn, document_id: str):
    """Return the most recent session_id for a given document_id, or None"""
    result = await conn.execute("""
        SELECT session_id::text
        FROM typing_sessions
        WHERE document_id = %s
        ORDER BY COALESCE(analyzed_at, created_at) DESC
        LIMIT 1
    """, (document_id,))
    row = await result.fetchone()
    return row[0] if row else None

async def create_session(conn, request, metrics, human_prob, status):
    """Legacy function - now calls create_or_merge_session"""
    await create_or_merge_session(conn, request, metrics, human_prob, status)