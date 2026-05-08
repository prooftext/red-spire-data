from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

from .config import AGGREGATE_FEATURE_COLUMNS, PROCESSED_DIR, SequenceConfig


EVENT_TYPE_MAP = {
    "keydown": 1,
    "keypress": 1,
    "paste": 2,
    "delete": 3,
    "backspace": 3,
    "navigation": 4,
    "format": 5,
}


KEY_CLASS_MAP = {
    "alpha": 1,
    "digit": 2,
    "space": 3,
    "punct": 4,
    "control": 5,
    "other": 6,
}


@dataclass
class PreprocessArtifacts:
    aggregate_scaler_path: str
    sequence_norm_path: str
    sequence_config: dict
    feature_columns: list[str]


def _safe_array(values: Iterable[float | int | None]) -> np.ndarray:
    return np.array([v for v in values if v is not None], dtype=float)


def _percentiles(values: np.ndarray) -> tuple[float, float, float]:
    if values.size == 0:
        return 0.0, 0.0, 0.0
    p10, p50, p90 = np.percentile(values, [10, 50, 90])
    return float(p10), float(p50), float(p90)


def _linreg_slope_r2(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if x.size < 2 or y.size < 2:
        return 0.0, 0.0
    coeff = np.polyfit(x, y, 1)
    pred = coeff[0] * x + coeff[1]
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return float(coeff[0]), max(0.0, min(1.0, r2))


def _event_type_code(event_type: str | None) -> int:
    if not event_type:
        return 0
    return EVENT_TYPE_MAP.get(event_type.lower(), 0)


def _key_class_code(key: str | None, event_type: str | None) -> int:
    if event_type and event_type.lower() in {"delete", "backspace", "navigation", "format", "paste"}:
        return KEY_CLASS_MAP["control"]
    if not key:
        return 0
    if key.isalpha():
        return KEY_CLASS_MAP["alpha"]
    if key.isdigit():
        return KEY_CLASS_MAP["digit"]
    if key.isspace():
        return KEY_CLASS_MAP["space"]
    if len(key) == 1 and not key.isalnum() and not key.isspace():
        return KEY_CLASS_MAP["punct"]
    return KEY_CLASS_MAP["other"]


def log_clip(value: float | int | None, max_value: int) -> float:
    if value is None:
        return 0.0
    v = max(0.0, min(float(value), float(max_value)))
    return float(np.log1p(v))


def build_aggregate_features(events_df: pd.DataFrame, sessions_df: pd.DataFrame | None = None) -> pd.DataFrame:
    rows: list[dict] = []
    for session_id, g in events_df.groupby("session_id"):
        g = g.sort_values("event_index")
        dwell = _safe_array(g.get("dwell_us", []))
        flight = _safe_array(g.get("flight_us", []))
        timestamps = _safe_array(g.get("timestamp_us", []))

        if timestamps.size > 1:
            pauses = np.diff(timestamps)
            pauses = pauses[pauses >= 0]
        else:
            pauses = np.array([], dtype=float)

        dwell_p10, dwell_p50, dwell_p90 = _percentiles(dwell)
        flight_p10, flight_p50, flight_p90 = _percentiles(flight)

        total_events = max(1, len(g))
        paste_chars = float(g.get("paste_len", pd.Series([0] * len(g))).fillna(0).sum())
        deletes = float(g.get("delete_len", pd.Series([0] * len(g))).fillna(0).sum())
        keydown_count = int((g["event_type"].isin(["keydown", "keypress"])) .sum())
        paste_count = int((g["event_type"] == "paste").sum())
        delete_count = int(g["event_type"].isin(["delete", "backspace"]).sum())
        nav_count = int((g["event_type"] == "navigation").sum())

        modifier_fraction = 0.0
        if "modifiers" in g.columns:
            mod_counts = []
            for raw in g["modifiers"].fillna("{}"):
                data = raw if isinstance(raw, dict) else {}
                if isinstance(raw, str):
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = {}
                mod_counts.append(1 if any(bool(v) for v in data.values()) else 0)
            modifier_fraction = float(np.mean(mod_counts)) if mod_counts else 0.0

        burst_lengths = []
        burst = 0
        inter_paste_dists = []
        prev_paste_idx = None
        last_cursor = None
        cursor_jump_count = 0
        text_growth_x = []
        text_growth_y = []
        text_len = 0
        for idx, row in enumerate(g.itertuples(index=False)):
            et = str(row.event_type).lower()
            if et in {"keydown", "keypress"}:
                burst += 1
                text_len += 1
            elif et == "paste":
                if burst > 0:
                    burst_lengths.append(burst)
                    burst = 0
                pl = int(getattr(row, "paste_len", 0) or 0)
                text_len += pl
                if prev_paste_idx is not None:
                    inter_paste_dists.append(idx - prev_paste_idx)
                prev_paste_idx = idx
            elif et in {"delete", "backspace"}:
                if burst > 0:
                    burst_lengths.append(burst)
                    burst = 0
                dl = int(getattr(row, "delete_len", 1) or 1)
                text_len = max(0, text_len - dl)
            elif et == "navigation":
                if burst > 0:
                    burst_lengths.append(burst)
                    burst = 0

            cursor = getattr(row, "cursor_position", None)
            cursor_valid = cursor is not None and cursor == cursor
            last_valid = last_cursor is not None and last_cursor == last_cursor
            if cursor_valid and last_valid and abs(int(cursor) - int(last_cursor)) > 15:
                cursor_jump_count += 1
            if cursor_valid:
                last_cursor = cursor

            text_growth_x.append(idx)
            text_growth_y.append(text_len)

        if burst > 0:
            burst_lengths.append(burst)

        x = np.array(text_growth_x, dtype=float)
        y = np.array(text_growth_y, dtype=float)
        slope, r2 = _linreg_slope_r2(x, y)

        doc_len = 0
        user_id = None
        dataset = "unknown"
        label_mode = None
        if sessions_df is not None and "session_id" in sessions_df.columns:
            s = sessions_df[sessions_df["session_id"] == session_id]
            if not s.empty:
                one = s.iloc[0]
                doc_len = int(one.get("document_text_len", 0) or 0)
                user_id = one.get("user_id")
                dataset = one.get("dataset", "unknown")
                label_mode = one.get("label_mode") or one.get("weak_label_mode")

        denom = max(doc_len, 1)
        rows.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "dataset": dataset,
                "label_mode": label_mode,
                "dwell_mean": float(np.mean(dwell)) if dwell.size else 0.0,
                "dwell_std": float(np.std(dwell)) if dwell.size else 0.0,
                "dwell_p10": dwell_p10,
                "dwell_p50": dwell_p50,
                "dwell_p90": dwell_p90,
                "flight_mean": float(np.mean(flight)) if flight.size else 0.0,
                "flight_std": float(np.std(flight)) if flight.size else 0.0,
                "flight_p10": flight_p10,
                "flight_p50": flight_p50,
                "flight_p90": flight_p90,
                "pause_mean": float(np.mean(pauses)) if pauses.size else 0.0,
                "pause_std": float(np.std(pauses)) if pauses.size else 0.0,
                "pause_p90": float(np.percentile(pauses, 90)) if pauses.size else 0.0,
                "pause_over_2s_ratio": float(np.mean(pauses > 2_000_000)) if pauses.size else 0.0,
                "paste_ratio": float(paste_chars / denom),
                "delete_ratio": float(deletes / denom),
                "navigation_ratio": float(nav_count / total_events),
                "modifier_fraction": modifier_fraction,
                "avg_burst_length": float(np.mean(burst_lengths)) if burst_lengths else 0.0,
                "avg_inter_paste_distance": float(np.mean(inter_paste_dists)) if inter_paste_dists else 0.0,
                "text_growth_slope": slope,
                "text_growth_r2": r2,
                "cursor_jump_count": float(cursor_jump_count),
                "keydown_count": float(keydown_count),
                "paste_event_count": float(paste_count),
                "delete_event_count": float(delete_count),
                "total_events": float(total_events),
            }
        )

    out = pd.DataFrame(rows)
    for c in AGGREGATE_FEATURE_COLUMNS:
        if c not in out.columns:
            out[c] = 0.0
    return out


def fit_aggregate_scaler(feature_df: pd.DataFrame, output_path: Path | None = None) -> RobustScaler:
    scaler = RobustScaler()
    x = feature_df[AGGREGATE_FEATURE_COLUMNS].fillna(0.0).values
    scaler.fit(x)
    if output_path is not None:
        joblib.dump(scaler, output_path)
    return scaler


def transform_aggregate_features(feature_df: pd.DataFrame, scaler: RobustScaler) -> np.ndarray:
    x = feature_df[AGGREGATE_FEATURE_COLUMNS].fillna(0.0).values
    return scaler.transform(x)


def build_sequence_features(events_df: pd.DataFrame, cfg: SequenceConfig | None = None) -> tuple[np.ndarray, np.ndarray, list[str]]:
    cfg = cfg or SequenceConfig()
    session_ids = sorted(events_df["session_id"].unique().tolist())
    features = np.zeros((len(session_ids), cfg.max_len, 10), dtype=np.float32)
    mask = np.zeros((len(session_ids), cfg.max_len), dtype=np.float32)

    for i, sid in enumerate(session_ids):
        g = events_df[events_df["session_id"] == sid].sort_values("event_index").head(cfg.max_len)
        prev_ts = None
        for t, row in enumerate(g.itertuples(index=False)):
            et = str(row.event_type).lower()
            key = getattr(row, "key", None)
            ts = getattr(row, "timestamp_us", None)

            delta_t = 0.0
            if prev_ts is not None and ts is not None:
                delta_t = log_clip(max(0, int(ts) - int(prev_ts)), cfg.flight_clip_us)
            prev_ts = ts if ts is not None else prev_ts

            seq = np.array(
                [
                    log_clip(getattr(row, "dwell_us", None), cfg.dwell_clip_us),
                    log_clip(getattr(row, "flight_us", None), cfg.flight_clip_us),
                    float(_event_type_code(et)),
                    float(_key_class_code(key, et)),
                    1.0 if (key == "Backspace" or et == "backspace") else 0.0,
                    1.0 if et == "paste" else 0.0,
                    min(float(getattr(row, "paste_len", 0) or 0.0), float(cfg.paste_clip)),
                    min(float(getattr(row, "delete_len", 0) or 0.0), float(cfg.delete_clip)),
                    float(getattr(row, "cursor_position", 0) or 0.0),
                    delta_t,
                ],
                dtype=np.float32,
            )
            features[i, t, :] = seq
            mask[i, t] = 1.0

    return features, mask, session_ids


def save_preprocess_artifacts(scaler: RobustScaler, cfg: SequenceConfig, out_dir: Path | None = None) -> PreprocessArtifacts:
    out_dir = out_dir or (PROCESSED_DIR / "artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    scaler_path = out_dir / "aggregate_scaler.joblib"
    seq_path = out_dir / "sequence_norm.json"

    joblib.dump(scaler, scaler_path)
    seq_path.write_text(json.dumps({"sequence_config": asdict(cfg)}, indent=2), encoding="utf-8")

    return PreprocessArtifacts(
        aggregate_scaler_path=str(scaler_path),
        sequence_norm_path=str(seq_path),
        sequence_config=asdict(cfg),
        feature_columns=AGGREGATE_FEATURE_COLUMNS,
    )


def load_sequence_config(path: Path) -> SequenceConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    return SequenceConfig(**data.get("sequence_config", {}))
