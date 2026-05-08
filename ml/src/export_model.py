from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import MODELS_DIR, PROCESSED_DIR, PRODUCTION_DIR


def export_production_package() -> dict:
    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)

    artifacts = {
        MODELS_DIR / "mode_baseline.joblib": PRODUCTION_DIR / "mode_model.joblib",
        MODELS_DIR / "user_encoder.pt": PRODUCTION_DIR / "user_encoder.pt",
        MODELS_DIR / "user_encoder_config.json": PRODUCTION_DIR / "user_encoder_config.json",
        MODELS_DIR / "user_template_builder.joblib": PRODUCTION_DIR / "user_template_builder.joblib",
        PROCESSED_DIR / "artifacts" / "aggregate_scaler.joblib": PRODUCTION_DIR / "aggregate_scaler.joblib",
    }

    missing = [str(src) for src in artifacts if not src.exists()]
    if missing:
        raise FileNotFoundError(f"Missing artifacts: {missing}")

    for src, dst in artifacts.items():
        shutil.copy2(src, dst)

    preprocess_cfg = {
        "aggregate_scaler": "aggregate_scaler.joblib",
        "feature_columns_source": "ml/src/config.py",
        "sequence": "inference currently uses aggregate baseline for production path",
    }
    (PRODUCTION_DIR / "preprocess_config.json").write_text(json.dumps(preprocess_cfg, indent=2), encoding="utf-8")

    metadata = {
        "model_version": datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_schema_version": "keystroke-event-v1",
        "mode_labels": ["original", "mixed", "transcribed"],
    }
    (PRODUCTION_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "production_dir": str(PRODUCTION_DIR),
        "metadata": metadata,
        "files": sorted([p.name for p in PRODUCTION_DIR.iterdir() if p.is_file()]),
    }


if __name__ == "__main__":
    print(json.dumps(export_production_package(), indent=2))
