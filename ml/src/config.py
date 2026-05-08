from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = ROOT / "ml"
RAW_DIR = ML_ROOT / "raw"
PROCESSED_DIR = ML_ROOT / "processed"
MODELS_DIR = ML_ROOT / "models"
PRODUCTION_DIR = MODELS_DIR / "production"


@dataclass(frozen=True)
class SequenceConfig:
    max_len: int = 512
    dwell_clip_us: int = 2_000_000
    flight_clip_us: int = 2_000_000
    paste_clip: int = 10_000
    delete_clip: int = 10_000


AGGREGATE_FEATURE_COLUMNS = [
    "dwell_mean",
    "dwell_std",
    "dwell_p10",
    "dwell_p50",
    "dwell_p90",
    "flight_mean",
    "flight_std",
    "flight_p10",
    "flight_p50",
    "flight_p90",
    "pause_mean",
    "pause_std",
    "pause_p90",
    "pause_over_2s_ratio",
    "paste_ratio",
    "delete_ratio",
    "navigation_ratio",
    "modifier_fraction",
    "avg_burst_length",
    "avg_inter_paste_distance",
    "text_growth_slope",
    "text_growth_r2",
    "cursor_jump_count",
    "keydown_count",
    "paste_event_count",
    "delete_event_count",
    "total_events",
]


def ensure_ml_dirs() -> None:
    for p in [RAW_DIR, PROCESSED_DIR, MODELS_DIR, PRODUCTION_DIR]:
        p.mkdir(parents=True, exist_ok=True)
