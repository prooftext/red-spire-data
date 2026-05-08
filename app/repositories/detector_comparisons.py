from typing import Iterable
from uuid import UUID, NAMESPACE_URL, uuid5


def ensure_uuid(value):
    if isinstance(value, UUID):
        return str(value)
    try:
        UUID(value)
        return value
    except (ValueError, AttributeError, TypeError):
        return str(uuid5(NAMESPACE_URL, f"prooftext:{value}"))


async def insert_detector_comparisons(conn, session_id: str, document_id: str | None, results: Iterable[dict], text_length: int) -> None:
    session_id = ensure_uuid(session_id)
    for result in results:
        await conn.execute(
            """
            INSERT INTO ai_detector_comparisons (
                session_id,
                document_id,
                detector_name,
                detector_score,
                detector_label,
                text_length,
                created_at
            )
            VALUES (%s::uuid, %s, %s, %s, %s, %s, NOW())
            """,
            (
                session_id,
                document_id,
                result.get("name"),
                result.get("score"),
                result.get("label"),
                text_length,
            ),
        )
