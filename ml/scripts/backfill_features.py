from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ml.src.feature_extraction import build_aggregate_features


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "ml" / "processed"


def backfill() -> dict:
    events = pd.read_parquet(PROCESSED / "prod_events.parquet")
    sessions = pd.read_parquet(PROCESSED / "prod_sessions.parquet")
    feats = build_aggregate_features(events, sessions)
    out_path = PROCESSED / "prod_aggregate_features.parquet"
    feats.to_parquet(out_path, index=False)
    return {"rows": int(len(feats)), "path": str(out_path)}


if __name__ == "__main__":
    print(json.dumps(backfill(), indent=2))
