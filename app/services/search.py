async def search_document(conn, text: str) -> dict:
    """
    Search typing_sessions for matching document.
    Returns best match with human probability and username.
    """
    cursor = await conn.execute("""
         SELECT ts.session_id, ts.user_id, ts.human_probability, ts.verification_status,
             ts_rank_cd(ts.document_tsvector, query) AS rank, ts.document_text, u.username,
             ts.session_metrics, ts.document_id
        FROM typing_sessions ts
        LEFT JOIN users u ON ts.user_id = u.user_id,
        plainto_tsquery('english', %s) query
        WHERE ts.document_tsvector @@ query
        ORDER BY rank DESC
        LIMIT 1
    """, (text,))
    row = await cursor.fetchone()
    if row:
        session_id = row[0]
        
        # Get keystroke events for this session
        keystroke_cursor = await conn.execute("""
            SELECT event_type, event_data, sequence_number
            FROM keystroke_events
            WHERE session_id = %s
            ORDER BY sequence_number ASC
        """, (session_id,))
        keystroke_rows = await keystroke_cursor.fetchall()
        keystroke_events = [
            {
                "event_type": r[0],
                "event_data": r[1],
                "sequence_number": r[2]
            }
            for r in keystroke_rows
        ]
        
        return {
            "session_id": row[0],
            "user_id": row[1],
            "human_probability": row[2],
            "verification_status": row[3],
            "rank": row[4],
            "document_text": row[5],
            "username": row[6],
            "keystroke_events": keystroke_events,
            "session_metrics": row[7],
            "document_id": row[8]
        }
    return None