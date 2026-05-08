from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, roc_auc_score

from .config import AGGREGATE_FEATURE_COLUMNS, MODELS_DIR, PROCESSED_DIR
from .feature_extraction import build_aggregate_features
from .labeling import label_sessions
from .train_user_encoder import SessionEncoder


def _compute_eer(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    thresholds = np.linspace(-1.0, 1.0, 200)
    best_gap = 1e9
    best = (0.5, 0.0)
    for th in thresholds:
        pred = scores >= th
        far = float(np.mean((pred == 1) & (labels == 0)))
        frr = float(np.mean((pred == 0) & (labels == 1)))
        gap = abs(far - frr)
        if gap < best_gap:
            best_gap = gap
            best = ((far + frr) / 2.0, th)
    return float(best[0]), float(best[1])


def evaluate_models() -> dict:
    events = pd.read_parquet(PROCESSED_DIR / "all_events.parquet")
    sessions = pd.read_parquet(PROCESSED_DIR / "all_sessions.parquet")

    labels = label_sessions(events, sessions)
    sessions = sessions.merge(
        labels[["session_id", "weak_label_mode", "weak_label_confidence"]], on="session_id", how="left"
    )
    sessions["label_mode"] = sessions["label_mode"].fillna(sessions["weak_label_mode"])

    feats = build_aggregate_features(events, sessions)
    mode_payload = joblib.load(MODELS_DIR / "mode_baseline.joblib")
    scaler = joblib.load(PROCESSED_DIR / "artifacts" / "aggregate_scaler.joblib")

    mode_df = feats[feats["label_mode"].notna()].copy()
    x_mode = scaler.transform(mode_df[AGGREGATE_FEATURE_COLUMNS].fillna(0.0).values)
    y_true = mode_df["label_mode"].astype(str).values
    le = mode_payload["label_encoder"]
    y_true_enc = le.transform(y_true)

    mode_model = mode_payload["model"]
    y_prob = mode_model.predict_proba(x_mode)
    y_pred = np.argmax(y_prob, axis=1)

    mode_metrics = {
        "accuracy": float(accuracy_score(y_true_enc, y_pred)),
        "macro_f1": float(f1_score(y_true_enc, y_pred, average="macro")),
        "confusion_matrix": confusion_matrix(y_true_enc, y_pred).tolist(),
        "roc_auc_ovr": float(roc_auc_score(y_true_enc, y_prob, multi_class="ovr")) if len(le.classes_) > 2 else None,
        "classes": le.classes_.tolist(),
    }

    # User verification evaluation.
    ubuilder = joblib.load(MODELS_DIR / "user_template_builder.joblib")
    ucfg = json.loads((MODELS_DIR / "user_encoder_config.json").read_text(encoding="utf-8"))
    encoder = SessionEncoder(input_dim=int(ucfg["input_dim"]), emb_dim=int(ucfg["embedding_dim"]))
    encoder.load_state_dict(torch.load(MODELS_DIR / "user_encoder.pt", map_location="cpu"))
    encoder.eval()

    user_df = feats[feats["user_id"].notna()].copy()
    user_counts = user_df["user_id"].value_counts()
    valid_users = user_counts[user_counts >= 2].index
    user_df = user_df[user_df["user_id"].isin(valid_users)].copy()

    ux = ubuilder["scaler"].transform(user_df[ubuilder["feature_columns"]].fillna(0.0).values)
    with torch.no_grad():
        uemb = encoder(torch.tensor(ux, dtype=torch.float32)).numpy()
    uu = user_df["user_id"].astype(str).values

    scores = []
    labels_bin = []
    for i in range(len(uemb)):
        for j in range(i + 1, len(uemb)):
            s = float(np.dot(uemb[i], uemb[j]) / ((np.linalg.norm(uemb[i]) + 1e-9) * (np.linalg.norm(uemb[j]) + 1e-9)))
            scores.append(s)
            labels_bin.append(1 if uu[i] == uu[j] else 0)

    scores_arr = np.array(scores)
    labels_arr = np.array(labels_bin)
    user_auc = float(roc_auc_score(labels_arr, scores_arr)) if len(np.unique(labels_arr)) > 1 else 0.5
    eer, eer_th = _compute_eer(scores_arr, labels_arr)

    far_frr_at = {}
    for th in [eer_th, 0.5, 0.7, 0.8]:
        pred = scores_arr >= th
        far = float(np.mean((pred == 1) & (labels_arr == 0)))
        frr = float(np.mean((pred == 0) & (labels_arr == 1)))
        far_frr_at[str(round(float(th), 4))] = {"far": far, "frr": frr}

    source_breakout = {}
    if "dataset" in user_df.columns:
        for ds in sorted(user_df["dataset"].dropna().unique().tolist()):
            source_breakout[str(ds)] = int((user_df["dataset"] == ds).sum())

    report = {
        "mode_classification": mode_metrics,
        "user_verification": {
            "roc_auc": user_auc,
            "eer": eer,
            "eer_threshold": float(eer_th),
            "far_frr": far_frr_at,
            "pair_trials": int(len(scores_arr)),
        },
        "by_source": source_breakout,
        "notes": {
            "public_datasets": "Included when available in ml/raw and normalized into ml/processed.",
            "production_weak_labels": "Included via exporter + deterministic weak labels.",
            "manual_review_labels": "Not detected in this run unless present in input sessions.",
        },
    }

    (MODELS_DIR / "eval_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = [
        "# Evaluation Report",
        "",
        "## Session Mode",
        f"- Accuracy: {mode_metrics['accuracy']:.4f}",
        f"- Macro F1: {mode_metrics['macro_f1']:.4f}",
        "",
        "## User Verification",
        f"- ROC-AUC: {user_auc:.4f}",
        f"- EER: {eer:.4f}",
        f"- EER Threshold: {eer_th:.4f}",
        "",
        "## Sources",
    ]
    for k, v in source_breakout.items():
        md.append(f"- {k}: {v} sessions")
    (MODELS_DIR / "eval_report.md").write_text("\n".join(md), encoding="utf-8")

    return report


if __name__ == "__main__":
    print(json.dumps(evaluate_models(), indent=2))
