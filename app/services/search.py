async def search_document(conn, text: str) -> dict:
    """
    Search typing_sessions for matching document.
    Returns best match with human probability.
    """
    cursor = await conn.execute("""
        SELECT session_id, user_id, human_probability, verification_status,
               ts_rank_cd(document_tsvector, query) AS rank, document_text
        FROM typing_sessions, plainto_tsquery('english', %s) query
        WHERE document_tsvector @@ query
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
            "keystroke_events": keystroke_events
        }
    return None