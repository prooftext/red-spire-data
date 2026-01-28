async def search_document(conn, text: str) -> dict:
    """
    Search typing_sessions for matching document.
    Returns best match with human probability.
    """
    cursor = await conn.execute("""
        SELECT session_id, user_id, human_probability, verification_status,
               ts_rank_cd(document_tsvector, query) AS rank
        FROM typing_sessions, plainto_tsquery('english', %s) query
        WHERE document_tsvector @@ query
        ORDER BY rank DESC
        LIMIT 1
    """, (text,))
    row = await cursor.fetchone()
    if row:
        return {
            "session_id": row[0],
            "user_id": row[1],
            "human_probability": row[2],
            "verification_status": row[3],
            "rank": row[4]
        }
    return None