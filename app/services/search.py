async def search_documents(conn, text: str, limit: int = 5) -> list[dict]:
    """
    Search typing_sessions for matching documents.
    Returns ranked matches with human probability and username.
    """
    limit = max(1, min(int(limit), 20))
    cursor = await conn.execute(
        """
         SELECT ts.session_id, ts.user_id, ts.human_probability, ts.verification_status,
             ts_rank_cd(ts.document_tsvector, query) AS rank, ts.document_text, u.username,
             ts.session_metrics, ts.document_id
        FROM typing_sessions ts
        LEFT JOIN users u ON ts.user_id = u.user_id,
        plainto_tsquery('english', %s) query
        WHERE ts.document_tsvector @@ query
        ORDER BY rank DESC, COALESCE(ts.analyzed_at, ts.created_at) DESC
        LIMIT %s
    """,
        (text, limit),
    )
    rows = await cursor.fetchall()

    # Fallback for environments where document_tsvector has not been backfilled yet.
    if not rows:
        cursor = await conn.execute(
            """
            SELECT
                ts.session_id,
                ts.user_id,
                ts.human_probability,
                ts.verification_status,
                CASE
                    WHEN POSITION(LOWER(%s) IN LOWER(ts.document_text)) > 0 THEN
                        1.0 / POSITION(LOWER(%s) IN LOWER(ts.document_text))
                    ELSE 0.0
                END AS rank,
                ts.document_text,
                u.username,
                ts.session_metrics,
                ts.document_id
            FROM typing_sessions ts
            LEFT JOIN users u ON ts.user_id = u.user_id
            WHERE LOWER(ts.document_text) LIKE LOWER(%s)
            ORDER BY rank DESC, COALESCE(ts.analyzed_at, ts.created_at) DESC
            LIMIT %s
            """,
            (text, text, f"%{text}%", limit),
        )
        rows = await cursor.fetchall()

    if not rows:
        return []

    results = []
    for row in rows:
        session_id = row[0]

        keystroke_cursor = await conn.execute(
            """
            SELECT event_type, event_data, sequence_number
            FROM keystroke_events
            WHERE session_id = %s
            ORDER BY sequence_number ASC
        """,
            (session_id,),
        )
        keystroke_rows = await keystroke_cursor.fetchall()
        keystroke_events = [
            {
                "event_type": r[0],
                "event_data": r[1],
                "sequence_number": r[2],
            }
            for r in keystroke_rows
        ]

        results.append(
            {
                "session_id": row[0],
                "user_id": row[1],
                "human_probability": row[2],
                "verification_status": row[3],
                "rank": row[4],
                "document_text": row[5],
                "username": row[6],
                "keystroke_events": keystroke_events,
                "session_metrics": row[7],
                "document_id": row[8],
            }
        )

    return results