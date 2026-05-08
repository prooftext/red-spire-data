from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
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


def _empty_event_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
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
            "modifiers",
            "label_mode",
        ]
    )


def _empty_session_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["dataset", "session_id", "user_id", "document_text_len", "label_mode", "label_source"])


def _extract_prefixed_float(record: dict[str, Any], prefixes: list[str], token: str) -> float | None:
    for p in prefixes:
        for key in (f"{p}.{token}", f"{p}_{token}"):
            if key in record and pd.notna(record[key]):
                try:
                    return float(record[key])
                except Exception:
                    continue
    return None


def _parse_cmu(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    cmu_dir = raw_dir / "cmu"
    if not cmu_dir.exists():
        return _empty_event_df(), _empty_session_df()

    csv_candidates = list(cmu_dir.rglob("*.csv"))
    if not csv_candidates:
        return _empty_event_df(), _empty_session_df()

    events_rows = []
    sessions_rows = []
    max_sessions_per_user = 50

    for fp in csv_candidates:
        try:
            df = pd.read_csv(fp)
        except Exception:
            continue
        if df.empty:
            continue

        cols_lower = {c.lower(): c for c in df.columns}
        subject_col = cols_lower.get("subject") or cols_lower.get("user") or cols_lower.get("user_id")
        session_col = cols_lower.get("session") or cols_lower.get("session_id")
        if subject_col is None:
            # For classical CMU strong-password data, each row is a sample and subject is required.
            continue

        sampled = []
        for uid, g in df.groupby(subject_col):
            sampled.append(g.head(max_sessions_per_user))
        df = pd.concat(sampled, ignore_index=True)

        for row_idx, row in enumerate(df.itertuples(index=False)):
            r = row._asdict()
            uid = str(r.get(subject_col, "cmu_unknown_user"))
            if session_col and pd.notna(r.get(session_col)):
                sid = f"cmu_{uid}_{r.get(session_col)}"
            else:
                sid = f"cmu_{uid}_{row_idx}"

            # Try to recover dwell/flight vectors from columns like H.period, UD.t.i, etc.
            dwell_values = []
            flight_values = []
            for c, v in r.items():
                if not pd.notna(v):
                    continue
                lc = str(c).lower()
                try:
                    fv = float(v)
                except Exception:
                    continue
                if lc.startswith("h.") or lc.startswith("hold"):
                    dwell_values.append(max(0.0, fv * 1_000_000.0))
                elif lc.startswith("ud.") or lc.startswith("flight") or lc.startswith("dd."):
                    flight_values.append(max(0.0, fv * 1_000_000.0))

            if not dwell_values and not flight_values:
                continue

            n_events = max(len(dwell_values), len(flight_values))
            t_us = 0
            for i in range(n_events):
                d = int(dwell_values[i]) if i < len(dwell_values) else None
                f = int(flight_values[i]) if i < len(flight_values) else None
                if i > 0 and f is not None:
                    t_us += f
                events_rows.append(
                    {
                        "dataset": "cmu",
                        "session_id": sid,
                        "user_id": uid,
                        "event_index": i,
                        "event_type": "keydown",
                        "key_code": None,
                        "key": None,
                        "timestamp_us": t_us,
                        "dwell_us": d,
                        "flight_us": f,
                        "cursor_position": None,
                        "paste_len": None,
                        "delete_len": None,
                        "modifiers": None,
                        "label_mode": None,
                    }
                )

            sessions_rows.append(
                {
                    "dataset": "cmu",
                    "session_id": sid,
                    "user_id": uid,
                    "document_text_len": int(n_events),
                    "label_mode": None,
                    "label_source": "cmu_public",
                }
            )

    if not events_rows:
        return _empty_event_df(), _empty_session_df()
    return pd.DataFrame(events_rows), pd.DataFrame(sessions_rows)


def _parse_keyrecs(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    kr_dir = raw_dir / "keyrecs"
    if not kr_dir.exists():
        return _empty_event_df(), _empty_session_df()

    events_rows = []
    sessions_rows = []

    def _consume_events(records: list[dict[str, Any]], dataset_tag: str) -> None:
        for rec_idx, rec in enumerate(records):
            sid = str(rec.get("session_id") or rec.get("id") or f"keyrecs_session_{rec_idx}")
            uid = str(rec.get("user_id") or rec.get("user") or rec.get("subject") or "keyrecs_unknown_user")
            mode = rec.get("label_mode") or rec.get("mode")

            if "events" in rec and isinstance(rec["events"], list):
                evs = rec["events"]
            else:
                evs = [rec]

            local_count = 0
            for i, ev in enumerate(evs):
                if not isinstance(ev, dict):
                    continue
                nr = normalize_event("keyrecs", sid, uid, i, ev, label_mode=mode)
                if nr.get("event_type") == "unknown":
                    continue
                events_rows.append({**nr, "dataset": dataset_tag})
                local_count += 1

            if local_count > 0:
                sessions_rows.append(
                    {
                        "dataset": dataset_tag,
                        "session_id": sid,
                        "user_id": uid,
                        "document_text_len": int(local_count),
                        "label_mode": mode,
                        "label_source": "keyrecs_public",
                    }
                )

    jsonl_files = list(kr_dir.rglob("*.jsonl"))
    for fp in jsonl_files:
        records = []
        for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        _consume_events(records, "keyrecs")

    json_files = list(kr_dir.rglob("*.json"))
    for fp in json_files:
        try:
            obj = json.loads(fp.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if isinstance(obj, list):
            _consume_events([x for x in obj if isinstance(x, dict)], "keyrecs")
        elif isinstance(obj, dict):
            _consume_events([obj], "keyrecs")

    csv_files = list(kr_dir.rglob("*.csv"))
    for fp in csv_files:
        try:
            df = pd.read_csv(fp)
        except Exception:
            continue
        if df.empty:
            continue

        # Case A: event-level rows already flattened.
        columns = {c.lower(): c for c in df.columns}
        sid_col = columns.get("session_id") or columns.get("session")
        uid_col = columns.get("user_id") or columns.get("user") or columns.get("subject")
        ev_col = columns.get("event_type") or columns.get("eventtype")
        if sid_col and uid_col and ev_col:
            for sid, g in df.groupby(sid_col):
                uid = str(g.iloc[0][uid_col])
                mode = g.iloc[0][columns.get("label_mode")] if columns.get("label_mode") else None
                for i, rr in enumerate(g.itertuples(index=False)):
                    rd = rr._asdict()
                    ev = {
                        "event_type": rd.get(ev_col),
                        "eventType": rd.get(ev_col),
                        "key": rd.get(columns.get("key", "")),
                        "key_code": rd.get(columns.get("key_code", "")),
                        "keyCode": rd.get(columns.get("keycode", "")),
                        "timestamp": rd.get(columns.get("timestamp", "")) or rd.get(columns.get("event_time", "")),
                        "dwell_us": rd.get(columns.get("dwell_us", "")) or rd.get(columns.get("dwelltimemicros", "")),
                        "flight_us": rd.get(columns.get("flight_us", "")) or rd.get(columns.get("flighttimemicros", "")),
                        "cursor_position": rd.get(columns.get("cursor_position", "")),
                        "paste_len": rd.get(columns.get("paste_len", "")),
                        "delete_len": rd.get(columns.get("delete_len", "")),
                    }
                    nr = normalize_event("keyrecs", str(sid), uid, i, ev, label_mode=mode)
                    events_rows.append(nr)
                sessions_rows.append(
                    {
                        "dataset": "keyrecs",
                        "session_id": str(sid),
                        "user_id": uid,
                        "document_text_len": int(len(g)),
                        "label_mode": mode,
                        "label_source": "keyrecs_public",
                    }
                )

    if not events_rows:
        return _empty_event_df(), _empty_session_df()
    return pd.DataFrame(events_rows), pd.DataFrame(sessions_rows)


def _parse_lsia(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    lsia_dir = raw_dir / "lsia"
    if not lsia_dir.exists():
        return _empty_event_df(), _empty_session_df()

    events_rows = []
    sessions_rows = []

    def _canonical_mode(raw_label: Any) -> str | None:
        if raw_label is None:
            return None
        s = str(raw_label).strip().lower()
        if s in {"human", "original", "handwritten", "composed"}:
            return "original"
        if s in {"transcribed", "copied", "copy", "synthesized", "ai"}:
            return "transcribed"
        if s in {"mixed"}:
            return "mixed"
        return None

    def _consume_text_sessions(df: pd.DataFrame, dataset_tag: str) -> None:
        cols = {c.lower(): c for c in df.columns}
        text_col = cols.get("text") or cols.get("document_text") or cols.get("content")
        uid_col = cols.get("user_id") or cols.get("user") or cols.get("author")
        sid_col = cols.get("session_id") or cols.get("id")
        label_col = cols.get("label_mode") or cols.get("label") or cols.get("class") or cols.get("source")
        if text_col is None:
            return

        for i, row in enumerate(df.itertuples(index=False)):
            r = row._asdict()
            sid = str(r.get(sid_col, f"lsia_{i}")) if sid_col else f"lsia_{i}"
            uid = str(r.get(uid_col, f"lsia_user_{i}")) if uid_col else f"lsia_user_{i}"
            text = str(r.get(text_col, "") or "")
            label_mode = _canonical_mode(r.get(label_col)) if label_col else None

            # LSIA-style corpora are often text-level, so represent as synthetic sequence
            # with timing unknown and a single event to preserve supervised labels.
            events_rows.append(
                {
                    "dataset": dataset_tag,
                    "session_id": sid,
                    "user_id": uid,
                    "event_index": 0,
                    "event_type": "unknown",
                    "key_code": None,
                    "key": None,
                    "timestamp_us": None,
                    "dwell_us": None,
                    "flight_us": None,
                    "cursor_position": None,
                    "paste_len": None,
                    "delete_len": None,
                    "modifiers": None,
                    "label_mode": label_mode,
                }
            )
            sessions_rows.append(
                {
                    "dataset": dataset_tag,
                    "session_id": sid,
                    "user_id": uid,
                    "document_text_len": int(len(text)),
                    "label_mode": label_mode,
                    "label_source": "lsia_public",
                }
            )

    for fp in lsia_dir.rglob("*.csv"):
        try:
            df = pd.read_csv(fp)
        except Exception:
            continue
        if not df.empty:
            _consume_text_sessions(df, "lsia")

    for fp in lsia_dir.rglob("*.jsonl"):
        records = []
        for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        if records:
            _consume_text_sessions(pd.DataFrame(records), "lsia")

    for fp in lsia_dir.rglob("*.json"):
        try:
            obj = json.loads(fp.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            _consume_text_sessions(pd.DataFrame(obj), "lsia")
        elif isinstance(obj, dict):
            _consume_text_sessions(pd.DataFrame([obj]), "lsia")

    if not events_rows:
        return _empty_event_df(), _empty_session_df()
    return pd.DataFrame(events_rows), pd.DataFrame(sessions_rows)


def build_normalized_datasets(output_prefix: str = "all") -> dict[str, str]:
    ensure_ml_dirs()

    root = Path(__file__).resolve().parents[2]
    fixtures_dir = root.parent / "database-fiiles" / "fixtures"

    fixture_events, fixture_sessions = _parse_fixture_events(fixtures_dir)
    cmu_events, cmu_sessions = _parse_cmu(RAW_DIR)
    keyrecs_events, keyrecs_sessions = _parse_keyrecs(RAW_DIR)
    lsia_events, lsia_sessions = _parse_lsia(RAW_DIR)
    prod_events, prod_sessions = _parse_prod_exports(PROCESSED_DIR)

    events = pd.concat(
        [fixture_events, cmu_events, keyrecs_events, lsia_events, prod_events],
        ignore_index=True,
    )
    sessions = pd.concat(
        [fixture_sessions, cmu_sessions, keyrecs_sessions, lsia_sessions, prod_sessions],
        ignore_index=True,
    )

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
        "counts_by_dataset": json.dumps({k: int(v) for k, v in events["dataset"].value_counts().to_dict().items()}),
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
