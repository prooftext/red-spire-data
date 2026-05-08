import json
from uuid import UUID, NAMESPACE_URL, uuid5


def ensure_uuid(value):
    if isinstance(value, UUID):
        return str(value)
    try:
        UUID(value)
        return value
    except (ValueError, AttributeError, TypeError):
        return str(uuid5(NAMESPACE_URL, f"prooftext:{value}"))


async def get_typing_profile(conn, user_id: str) -> dict | None:
    user_id = ensure_uuid(user_id)
    result = await conn.execute(
        """
        SELECT profile_data, sample_count, confidence_score
        FROM typing_profiles
        WHERE user_id = %s::uuid
        """,
        (user_id,),
    )
    row = await result.fetchone()
    if not row:
        return None

    profile_data = row[0]
    if isinstance(profile_data, str):
        try:
            profile_data = json.loads(profile_data)
        except json.JSONDecodeError:
            profile_data = None

    return {
        "profile_data": profile_data,
        "sample_count": row[1],
        "confidence_score": row[2],
    }


async def upsert_typing_profile(conn, user_id: str, profile_data: dict, sample_count: int, confidence_score: float) -> None:
    user_id = ensure_uuid(user_id)
    await conn.execute(
        """
        INSERT INTO typing_profiles (user_id, profile_data, sample_count, confidence_score, last_updated)
        VALUES (%s::uuid, %s::jsonb, %s, %s, NOW())
        ON CONFLICT (user_id)
        DO UPDATE SET
            profile_data = EXCLUDED.profile_data,
            sample_count = EXCLUDED.sample_count,
            confidence_score = EXCLUDED.confidence_score,
            last_updated = NOW()
        """,
        (user_id, json.dumps(profile_data), sample_count, confidence_score),
    )
