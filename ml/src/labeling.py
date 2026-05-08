from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class WeakLabelThresholds:
    original_max_paste_ratio: float = 0.08
    original_min_delete_ratio: float = 0.015
    transcribed_min_paste_ratio: float = 0.4
    transcribed_max_delete_ratio: float = 0.005
    transcribed_low_variance_std: float = 8_000.0
    mixed_min_paste_ratio: float = 0.12


def _safe_std(arr: pd.Series) -> float:
    clean = arr.dropna()
    return float(clean.std()) if not clean.empty else 0.0


def summarize_sessions(events_df: pd.DataFrame, sessions_df: pd.DataFrame | None = None) -> pd.DataFrame:
    rows: list[dict] = []
    for session_id, g in events_df.groupby("session_id"):
        g = g.sort_values("event_index")
        keydown = g["event_type"].isin(["keydown", "keypress"]).sum()
        paste_events = (g["event_type"] == "paste").sum()
        pasted_chars = g.get("paste_len", pd.Series([0] * len(g))).fillna(0).sum()
        delete_events = g["event_type"].isin(["delete", "backspace"]).sum()
        deleted_chars = g.get("delete_len", pd.Series([0] * len(g))).fillna(0).sum()
        nav_count = (g["event_type"] == "navigation").sum()
        dwell = g.get("dwell_us", pd.Series(dtype=float)).dropna()
        flight = g.get("flight_us", pd.Series(dtype=float)).dropna()

        pause_stats = {"pause_mean": 0.0, "pause_std": 0.0, "pause_p90": 0.0, "pauses_over_2s": 0}
        ts = g.get("timestamp_us", pd.Series(dtype=float)).dropna().values
        if ts.size > 1:
            pauses = np.diff(ts)
            pause_stats = {
                "pause_mean": float(np.mean(pauses)),
                "pause_std": float(np.std(pauses)),
                "pause_p90": float(np.percentile(pauses, 90)),
                "pauses_over_2s": int(np.sum(pauses > 2_000_000)),
            }

        revision_bursts = int(delete_events + nav_count)
        final_len = 1
        dataset = "unknown"
        user_id = None
        label_mode = None
        if sessions_df is not None and "session_id" in sessions_df.columns:
            s = sessions_df[sessions_df["session_id"] == session_id]
            if not s.empty:
                one = s.iloc[0]
                final_len = max(1, int(one.get("document_text_len", 0) or 0))
                dataset = one.get("dataset", "unknown")
                user_id = one.get("user_id")
                label_mode = one.get("label_mode")

        rows.append(
            {
                "dataset": dataset,
                "session_id": session_id,
                "user_id": user_id,
                "label_mode": label_mode,
                "total_events": int(len(g)),
                "keydown_count": int(keydown),
                "paste_event_count": int(paste_events),
                "total_pasted_chars": int(pasted_chars),
                "paste_ratio": float(pasted_chars / final_len),
                "delete_event_count": int(delete_events),
                "delete_ratio": float(deleted_chars / final_len),
                "mean_dwell": float(dwell.mean()) if not dwell.empty else 0.0,
                "std_dwell": _safe_std(dwell),
                "mean_flight": float(flight.mean()) if not flight.empty else 0.0,
                "std_flight": _safe_std(flight),
                "navigation_count": int(nav_count),
                "revision_bursts": revision_bursts,
                **pause_stats,
            }
        )

    return pd.DataFrame(rows)


def weak_label_mode(summary_df: pd.DataFrame, thresholds: WeakLabelThresholds | None = None) -> pd.DataFrame:
    th = thresholds or WeakLabelThresholds()
    out = summary_df.copy()

    labels = []
    confidences = []
    provenance = []

    for row in out.itertuples(index=False):
        paste_ratio = float(getattr(row, "paste_ratio", 0.0) or 0.0)
        delete_ratio = float(getattr(row, "delete_ratio", 0.0) or 0.0)
        std_dwell = float(getattr(row, "std_dwell", 0.0) or 0.0)
        std_flight = float(getattr(row, "std_flight", 0.0) or 0.0)
        revision_bursts = float(getattr(row, "revision_bursts", 0.0) or 0.0)
        keydown_count = float(getattr(row, "keydown_count", 0.0) or 0.0)

        original_score = 0.0
        transcribed_score = 0.0

        if paste_ratio <= th.original_max_paste_ratio:
            original_score += 0.35
        if delete_ratio >= th.original_min_delete_ratio:
            original_score += 0.25
        if std_dwell >= th.transcribed_low_variance_std and std_flight >= th.transcribed_low_variance_std:
            original_score += 0.2
        if revision_bursts >= 2:
            original_score += 0.2

        if paste_ratio >= th.transcribed_min_paste_ratio:
            transcribed_score += 0.45
        if delete_ratio <= th.transcribed_max_delete_ratio:
            transcribed_score += 0.2
        if std_dwell <= th.transcribed_low_variance_std:
            transcribed_score += 0.15
        if std_flight <= th.transcribed_low_variance_std:
            transcribed_score += 0.1
        if keydown_count <= 20 and paste_ratio > 0.5:
            transcribed_score += 0.1

        if paste_ratio >= th.mixed_min_paste_ratio and paste_ratio < th.transcribed_min_paste_ratio:
            label = "mixed"
            confidence = min(0.85, 0.5 + paste_ratio)
            reason = "mixed_paste_and_typing"
        elif transcribed_score > original_score and transcribed_score >= 0.45:
            label = "transcribed"
            confidence = min(0.99, transcribed_score)
            reason = "high_paste_low_revision"
        elif original_score >= 0.5:
            label = "original"
            confidence = min(0.99, original_score)
            reason = "low_paste_natural_variance"
        else:
            label = "mixed"
            confidence = 0.45
            reason = "ambiguous_default_mixed"

        labels.append(label)
        confidences.append(confidence)
        provenance.append(reason)

    out["weak_label_mode"] = labels
    out["weak_label_confidence"] = confidences
    out["weak_label_provenance"] = provenance
    return out


def label_sessions(events_df: pd.DataFrame, sessions_df: pd.DataFrame | None = None) -> pd.DataFrame:
    summary = summarize_sessions(events_df, sessions_df)
    labeled = weak_label_mode(summary)
    return labeled


def _main() -> None:
    parser = argparse.ArgumentParser(description="Generate weak labels for session mode.")
    parser.add_argument("--input", required=True, help="Input events parquet path")
    parser.add_argument("--sessions", default=None, help="Optional sessions parquet path")
    parser.add_argument("--output", required=True, help="Output labeled sessions parquet")
    args = parser.parse_args()

    events_df = pd.read_parquet(args.input)
    sessions_df = pd.read_parquet(args.sessions) if args.sessions else None
    labeled = label_sessions(events_df, sessions_df)
    labeled.to_parquet(args.output, index=False)
    print(f"wrote {len(labeled)} labeled sessions -> {args.output}")


if __name__ == "__main__":
    _main()
