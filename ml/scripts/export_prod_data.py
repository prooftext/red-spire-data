from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "ml" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)


def _to_us(v) -> int | None:
    if v is None:
        return None
    try:
        return int(pd.to_datetime(v, utc=True).value // 1000)
    except Exception:
        return None


def export_prod_data() -> dict:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required")

    engine = create_engine(db_url)

    sessions_q = text(
        """
        SELECT
            session_id::text AS session_id,
            user_id::text AS user_id,
            document_text,
            COALESCE(document_id, md5(document_text)) AS document_id,
            session_start,
            session_end,
            total_duration_ms,
            verification_status,
            human_probability,
            session_metrics,
            created_at
        FROM typing_sessions
        ORDER BY created_at DESC
        """
    )

    events_q = text(
        """
        SELECT
            session_id::text AS session_id,
            user_id::text AS user_id,
            sequence_number,
            event_time,
            event_type,
            cursor_position,
            event_data
        FROM keystroke_events
        ORDER BY event_time ASC
        """
    )

    with engine.begin() as conn:
        sessions = pd.read_sql(sessions_q, conn)
        events_raw = pd.read_sql(events_q, conn)

    sessions["dataset"] = "prod"
    sessions["document_text_len"] = sessions["document_text"].fillna("").str.len()
    sessions_out = PROCESSED / "prod_sessions.parquet"
    sessions.to_parquet(sessions_out, index=False)

    event_rows = []
    for r in events_raw.itertuples(index=False):
        data = r.event_data
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {}
        if not isinstance(data, dict):
            data = {}

        event_rows.append(
            {
                "dataset": "prod",
                "session_id": str(r.session_id),
                "user_id": str(r.user_id),
                "event_index": int(r.sequence_number),
                "event_type": str(data.get("eventType") or r.event_type or "unknown").lower(),
                "key_code": data.get("keyCode"),
                "key": data.get("key"),
                "timestamp_us": _to_us(data.get("timestamp") or r.event_time),
                "dwell_us": data.get("dwellTimeMicros"),
                "flight_us": data.get("flightTimeMicros"),
                "cursor_position": data.get("cursorPosition") or r.cursor_position,
                "paste_len": data.get("pastedLength"),
                "delete_len": data.get("deletedLength"),
                "modifiers": data.get("modifiers"),
                "label_mode": None,
            }
        )

    events = pd.DataFrame(event_rows)
    events_out = PROCESSED / "prod_events.parquet"
    events.to_parquet(events_out, index=False)

    # Seed templates from high-confidence human sessions.
    trusted = sessions[(sessions["human_probability"].fillna(0) >= 0.9)]
    user_templates_seed = trusted[["session_id", "user_id", "human_probability", "created_at"]].copy()
    user_templates_seed["trusted"] = True
    seed_out = PROCESSED / "user_templates_seed.parquet"
    user_templates_seed.to_parquet(seed_out, index=False)

    return {
        "sessions_rows": int(len(sessions)),
        "events_rows": int(len(events)),
        "sessions_path": str(sessions_out),
        "events_path": str(events_out),
        "seed_templates_path": str(seed_out),
    }


if __name__ == "__main__":
    print(json.dumps(export_prod_data(), indent=2))
