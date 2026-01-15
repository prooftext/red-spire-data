async def create_session(conn, request, metrics, human_prob, status):
    session_start = request.events[0].timestamp if request.events else None
    session_end = request.events[-1].timestamp if request.events else None
    total_duration_ms = int((session_end - session_start).total_seconds() * 1000) if session_start and session_end else None
    
    await conn.execute("""
        INSERT INTO typing_sessions (session_id, user_id, document_text, session_start, session_end, total_duration_ms, verification_status, human_probability, session_metrics, analyzed_at)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, NOW())
    """, request.session_id, request.user_id, request.document_text, session_start, session_end, total_duration_ms, status, human_prob, metrics)