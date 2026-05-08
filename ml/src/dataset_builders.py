from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import PROCESSED_DIR, RAW_DIR, ensure_ml_dirs


CAPABILITIES = {
    "cmu": {
        "has_dwell": True,
        "has_flight": True,
        "has_event_type": False,
        "has_cursor": False,
        "supports_mode_label": False,
        "supports_user_label": True,
    },
    "keyrecs": {
        "has_dwell": True,
        "has_flight": True,
        "has_event_type": True,
        "has_cursor": True,
        "supports_mode_label": False,
        "supports_user_label": True,
    },
    "lsia": {
        "has_dwell": False,
        "has_flight": False,
        "has_event_type": True,
        "has_cursor": False,
        "supports_mode_label": True,
        "supports_user_label": False,
    },
    "prod": {
        "has_dwell": True,
        "has_flight": True,
        "has_event_type": True,
        "has_cursor": True,
        "supports_mode_label": True,
        "supports_user_label": True,
    },
}


def _to_timestamp_us(v: Any) -> int | None:
    if v is None:
        return None
    try:
        ts = pd.to_datetime(v, utc=True)
        return int(ts.value // 1000)
    except Exception:
        return None


def normalize_event(
    dataset: str,
    session_id: str,
    user_id: str,
    event_index: int,
    event: dict,
    label_mode: str | None = None,
) -> dict:
    et = str(event.get("eventType") or event.get("event_type") or "unknown").lower()
    return {
        "dataset": dataset,
        "session_id": str(session_id),
        "user_id": str(user_id),
        "event_index": int(event.get("sequence") or event.get("event_index") or event_index),
        "event_type": et,
        "key_code": event.get("keyCode") or event.get("key_code"),
        "key": event.get("key"),
        "timestamp_us": _to_timestamp_us(event.get("timestamp") or event.get("event_time") or event.get("pressTime")),
        "dwell_us": event.get("dwellTimeMicros") or event.get("dwell_us"),
        "flight_us": event.get("flightTimeMicros") or event.get("flight_us"),
        "cursor_position": event.get("cursorPosition") or event.get("cursor_position"),
        "paste_len": event.get("pastedLength") or event.get("paste_len"),
        "delete_len": event.get("deletedLength") or event.get("delete_len"),
        "modifiers": event.get("modifiers"),
        "label_mode": label_mode,
    }


def _parse_fixture_events(fixtures_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping = {
        "human_typing_sample.json": ("fixture_human_001", "fixture_user_a", "original", "fixtures"),
        "ai_pasted_sample.json": ("fixture_ai_001", "fixture_user_b", "transcribed", "fixtures"),
        "mixed_behavior_sample.json": ("fixture_mixed_001", "fixture_user_a", "mixed", "fixtures"),
    }

    all_events = []
    sessions = []
    for fname, (sid, uid, label_mode, dataset) in mapping.items():
        fp = fixtures_dir / fname
        if not fp.exists():
            continue
        events = json.loads(fp.read_text(encoding="utf-8"))
        for idx, ev in enumerate(events):
            all_events.append(normalize_event(dataset, sid, uid, idx, ev, label_mode=label_mode))

        doc_len = int(sum((e.get("pastedLength") or 1) for e in events))
        sessions.append(
            {
                "dataset": dataset,
                "session_id": sid,
                "user_id": uid,
                "document_text_len": doc_len,
                "label_mode": label_mode,
                "label_source": "fixture",
            }
        )

    base_events = pd.DataFrame(all_events)
    base_sessions = pd.DataFrame(sessions)

    # Deterministic augmentation from fixture sessions to enable robust local training.
    aug_events = []
    aug_sessions = []
    multipliers = [0.9, 1.0, 1.1]
    for srow in base_sessions.itertuples(index=False):
        sid = str(srow.session_id)
        uid = str(srow.user_id)
        label_mode = str(srow.label_mode)
        sess_events = base_events[base_events["session_id"] == sid].sort_values("event_index")
        for k, mult in enumerate(multipliers):
            new_sid = f"{sid}_aug{k+1}"
            new_uid = uid if k < 2 else ("fixture_user_c" if uid != "fixture_user_c" else "fixture_user_d")
            for ev in sess_events.itertuples(index=False):
                dwell = ev.dwell_us
                flight = ev.flight_us
                aug_events.append(
                    {
                        **ev._asdict(),
                        "dataset": "fixtures_aug",
                        "session_id": new_sid,
                        "user_id": new_uid,
                        "dwell_us": int(float(dwell) * mult) if (dwell is not None and dwell == dwell) else None,
                        "flight_us": int(float(flight) * mult) if (flight is not None and flight == flight) else None,
                    }
                )
            aug_sessions.append(
                {
                    "dataset": "fixtures_aug",
                    "session_id": new_sid,
                    "user_id": new_uid,
                    "document_text_len": int(srow.document_text_len),
                    "label_mode": label_mode,
                    "label_source": "fixture_augmented",
                }
            )

    all_events_df = pd.concat([base_events, pd.DataFrame(aug_events)], ignore_index=True)
    all_sessions_df = pd.concat([base_sessions, pd.DataFrame(aug_sessions)], ignore_index=True)
    return all_events_df, all_sessions_df


def _parse_prod_exports(processed_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    events_path = processed_dir / "prod_events.parquet"
    sessions_path = processed_dir / "prod_sessions.parquet"
    if not events_path.exists() or not sessions_path.exists():
        return pd.DataFrame(), pd.DataFrame()
    events = pd.read_parquet(events_path)
    sessions = pd.read_parquet(sessions_path)

    # Ensure canonical columns.
    for col in [
        "dataset",
        "session_id",
        "user_id",
        "event_index",
        "event_type",
        "key_code",
        "key",
        "timestamp_us",
        "dwell_us",
        "flight_us",
        "cursor_position",
        "paste_len",
        "delete_len",
        "label_mode",
    ]:
        if col not in events.columns:
            events[col] = None

    if "dataset" not in sessions.columns:
        sessions["dataset"] = "prod"
    if "document_text_len" not in sessions.columns:
        sessions["document_text_len"] = sessions.get("document_text", "").fillna("").str.len()

    return events, sessions


def build_normalized_datasets(output_prefix: str = "all") -> dict[str, str]:
    ensure_ml_dirs()

    root = Path(__file__).resolve().parents[2]
    fixtures_dir = root.parent / "database-fiiles" / "fixtures"

    fixture_events, fixture_sessions = _parse_fixture_events(fixtures_dir)
    prod_events, prod_sessions = _parse_prod_exports(PROCESSED_DIR)

    events = pd.concat([fixture_events, prod_events], ignore_index=True)
    sessions = pd.concat([fixture_sessions, prod_sessions], ignore_index=True)

    if "dataset" not in events.columns:
        events["dataset"] = "unknown"

    events_out = PROCESSED_DIR / f"{output_prefix}_events.parquet"
    sessions_out = PROCESSED_DIR / f"{output_prefix}_sessions.parquet"
    caps_out = PROCESSED_DIR / "dataset_capabilities.json"

    events.to_parquet(events_out, index=False)
    sessions.to_parquet(sessions_out, index=False)
    caps_out.write_text(json.dumps(CAPABILITIES, indent=2), encoding="utf-8")

    return {
        "events": str(events_out),
        "sessions": str(sessions_out),
        "capabilities": str(caps_out),
        "events_rows": str(len(events)),
        "sessions_rows": str(len(sessions)),
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Build normalized datasets from available sources.")
    parser.add_argument("--build-all", action="store_true", help="Build consolidated normalized parquet files")
    args = parser.parse_args()
    if args.build_all:
        result = build_normalized_datasets()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
