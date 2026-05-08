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


async def ensure_session_scores_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_scores (
            id BIGSERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            user_id UUID NOT NULL,
            model_version TEXT NOT NULL,
            mode_label TEXT,
            mode_confidence FLOAT,
            mode_probs JSONB,
            user_match_score FLOAT,
            user_match_threshold FLOAT,
            user_match_is_match BOOLEAN,
            signals JSONB,
            segments JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_session_scores_session ON session_scores(session_id, created_at DESC);
        """
    )


async def insert_session_score(conn, session_id: str, user_id: str, score_payload: dict, model_version: str) -> None:
    await ensure_session_scores_table(conn)
    session_id = ensure_uuid(session_id)
    user_id = ensure_uuid(user_id)
    mode_probs = score_payload.get("mode_probs") or {}
    user_match = score_payload.get("user_match") or {}
    await conn.execute(
        """
        INSERT INTO session_scores (
            session_id,
            user_id,
            model_version,
            mode_label,
            mode_confidence,
            mode_probs,
            user_match_score,
            user_match_threshold,
            user_match_is_match,
            signals,
            segments
        )
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (
            session_id,
            user_id,
            model_version,
            score_payload.get("mode"),
            score_payload.get("mode_confidence"),
            json.dumps(mode_probs),
            user_match.get("score"),
            user_match.get("threshold"),
            user_match.get("is_match"),
            json.dumps(score_payload.get("signals") or {}),
            json.dumps(score_payload.get("segments") or []),
        ),
    )
