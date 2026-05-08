# Keystroke ML Pipeline

This directory contains the end-to-end ML pipeline for:

1. Session mode classification (`original`, `mixed`, `transcribed`).
2. User typing signature verification (same user vs different user).

## Layout

- `raw/`: raw downloaded or exported data files.
- `processed/`: normalized parquet files and engineered datasets.
- `models/`: model artifacts and evaluation outputs.
- `src/`: reusable python modules.
- `scripts/`: operational scripts for download/export/retrain.

## Quick Start

```bash
pip install -r ml/requirements.txt
python ml/scripts/export_prod_data.py
python -m ml.src.dataset_builders --build-all
python -m ml.src.labeling --input ml/processed/prod_events.parquet --output ml/processed/prod_session_labels.parquet
python -m ml.src.train_mode_classifier
python -m ml.src.train_user_encoder
python -m ml.src.evaluate
python -m ml.src.export_model
```

## Notes

- Weak labels are tracked separately from any reviewed labels.
- All artifacts include model metadata and schema versions.
- Inference is integrated in `app/ml_inference.py` and wired into the collect path.
