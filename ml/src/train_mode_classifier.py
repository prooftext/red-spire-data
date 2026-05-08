from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

from .config import AGGREGATE_FEATURE_COLUMNS, MODELS_DIR, PROCESSED_DIR, ensure_ml_dirs
from .feature_extraction import build_aggregate_features, fit_aggregate_scaler, save_preprocess_artifacts, SequenceConfig
from .labeling import label_sessions


def _load_training_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    events_path = PROCESSED_DIR / "all_events.parquet"
    sessions_path = PROCESSED_DIR / "all_sessions.parquet"
    if not events_path.exists() or not sessions_path.exists():
        raise FileNotFoundError("Run dataset builder first: python -m ml.src.dataset_builders --build-all")

    events = pd.read_parquet(events_path)
    sessions = pd.read_parquet(sessions_path)

    labels = label_sessions(events, sessions)
    merged_sessions = sessions.merge(
        labels[["session_id", "weak_label_mode", "weak_label_confidence"]],
        on="session_id",
        how="left",
    )
    merged_sessions["label_mode"] = merged_sessions["label_mode"].fillna(merged_sessions["weak_label_mode"])
    return events, merged_sessions


def train_mode_classifier() -> dict:
    ensure_ml_dirs()
    events, sessions = _load_training_data()

    feats = build_aggregate_features(events, sessions)
    feats = feats[feats["label_mode"].notna()].copy()
    if feats.empty:
        raise RuntimeError("No labeled sessions available for mode classifier training")

    x = feats[AGGREGATE_FEATURE_COLUMNS].fillna(0.0)
    y_raw = feats["label_mode"].astype(str)

    le = LabelEncoder()
    y = le.fit_transform(y_raw)

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.3, random_state=42, stratify=y if len(np.unique(y)) > 1 else None
    )

    scaler = fit_aggregate_scaler(pd.DataFrame(x_train, columns=AGGREGATE_FEATURE_COLUMNS))
    x_train_s = scaler.transform(x_train)
    x_test_s = scaler.transform(x_test)

    models = {
        "logreg": LogisticRegression(max_iter=2000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(n_estimators=400, random_state=42, class_weight="balanced"),
    }

    results = {}
    best_name = None
    best_f1 = -1.0
    best_model = None

    for name, model in models.items():
        model.fit(x_train_s, y_train)
        pred = model.predict(x_test_s)
        prob = model.predict_proba(x_test_s)

        acc = accuracy_score(y_test, pred)
        macro_f1 = f1_score(y_test, pred, average="macro")
        cm = confusion_matrix(y_test, pred).tolist()

        try:
            auc = roc_auc_score(y_test, prob, multi_class="ovr")
        except Exception:
            auc = None

        results[name] = {
            "accuracy": acc,
            "macro_f1": macro_f1,
            "roc_auc": auc,
            "confusion_matrix": cm,
            "classification_report": classification_report(y_test, pred, target_names=le.classes_, output_dict=True),
        }

        if macro_f1 > best_f1:
            best_f1 = macro_f1
            best_name = name
            best_model = model

    model_path = MODELS_DIR / "mode_baseline.joblib"
    payload = {
        "model": best_model,
        "label_encoder": le,
        "feature_columns": AGGREGATE_FEATURE_COLUMNS,
        "model_name": best_name,
    }
    joblib.dump(payload, model_path)

    preprocess = save_preprocess_artifacts(scaler, SequenceConfig())

    metrics = {
        "best_model": best_name,
        "best_macro_f1": best_f1,
        "results": results,
        "train_size": int(len(x_train)),
        "test_size": int(len(x_test)),
        "preprocess": preprocess.__dict__,
    }

    (MODELS_DIR / "mode_train_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    out = train_mode_classifier()
    print(json.dumps(out, indent=2))
