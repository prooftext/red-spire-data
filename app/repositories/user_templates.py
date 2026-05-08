import json
import math
from typing import Any
from uuid import UUID


def ensure_uuid(value):
    if isinstance(value, UUID):
        return str(value)
    try:
        UUID(value)
        return value
    except (ValueError, AttributeError, TypeError):
        return str(UUID(int=hash(str(value)) % (2**128)))


async def ensure_user_templates_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_typing_templates (
            id BIGSERIAL PRIMARY KEY,
            user_id UUID NOT NULL,
            embedding_vector FLOAT8[] NOT NULL,
            source_session_id UUID,
            trusted BOOLEAN DEFAULT FALSE,
            model_version TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_typing_templates_user ON user_typing_templates(user_id, created_at DESC);
        """
    )


async def fetch_user_template_centroid(conn, user_id: str, model_version: str | None = None) -> list[float] | None:
    await ensure_user_templates_table(conn)
    user_id = ensure_uuid(user_id)
    query = """
        SELECT embedding_vector
        FROM user_typing_templates
        WHERE user_id = %s::uuid
    """
    params: list[Any] = [user_id]
    if model_version:
        query += " AND model_version = %s"
        params.append(model_version)
    query += " ORDER BY created_at DESC LIMIT 20"

    result = await conn.execute(query, tuple(params))
    rows = await result.fetchall()
    if not rows:
        return None

    vecs: list[list[float]] = []
    for r in rows:
        if not r or not r[0]:
            continue
        try:
            vecs.append([float(x) for x in r[0]])
        except Exception:
            continue

    if not vecs:
        return None

    dim = len(vecs[0])
    if dim == 0:
        return None

    sums = [0.0] * dim
    used = 0
    for v in vecs:
        if len(v) != dim:
            continue
        used += 1
        for i, val in enumerate(v):
            sums[i] += val

    if used == 0:
        return None

    centroid = [s / used for s in sums]
    norm = math.sqrt(sum(x * x for x in centroid))
    if norm > 0:
        centroid = [x / norm for x in centroid]
    return centroid


async def insert_user_template(
    conn,
    user_id: str,
    embedding_vector: list[float],
    source_session_id: str,
    trusted: bool,
    model_version: str,
) -> None:
    await ensure_user_templates_table(conn)
    user_id = ensure_uuid(user_id)
    source_session_id = ensure_uuid(source_session_id)
    await conn.execute(
        """
        INSERT INTO user_typing_templates (user_id, embedding_vector, source_session_id, trusted, model_version)
        VALUES (%s::uuid, %s, %s::uuid, %s, %s)
        """,
        (user_id, embedding_vector, source_session_id, trusted, model_version),
    )


async def get_user_enrollment_count(conn, user_id: str, model_version: str | None = None) -> int:
    await ensure_user_templates_table(conn)
    user_id = ensure_uuid(user_id)
    query = "SELECT COUNT(*) FROM user_typing_templates WHERE user_id = %s::uuid"
    params: list[Any] = [user_id]
    if model_version:
        query += " AND model_version = %s"
        params.append(model_version)

    result = await conn.execute(query, tuple(params))
    row = await result.fetchone()
    return int(row[0] if row else 0)
