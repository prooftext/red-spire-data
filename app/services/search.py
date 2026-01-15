async def search_document(conn, text: str) -> dict:
    """
    Search typing_sessions for matching document.
    Returns best match with human probability.
    """
    row = await conn.fetchone("""
        SELECT session_id, user_id, human_probability, verification_status,
               ts_rank_cd(document_tsvector, query) AS rank
        FROM typing_sessions, plainto_tsquery('english', %s) query
        WHERE document_tsvector @@ query
        ORDER BY rank DESC
        LIMIT 1
    """, (text,))
    return dict(row) if row else None