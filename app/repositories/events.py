from app.database import get_pool

async def bulk_insert_events(session_id: str, user_id: str, events):
    pool = get_pool()
    async with pool.acquire() as conn:
        for event in events:
            await conn.execute("""
                INSERT INTO keystroke_events (session_id, user_id, event_time, event_type, sequence_number, cursor_position, text_length, event_data)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb)
            """, session_id, user_id, event.timestamp, event.eventType, event.sequence, event.cursorPosition, None, event.model_dump())