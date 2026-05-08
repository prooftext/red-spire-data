from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from .config import AGGREGATE_FEATURE_COLUMNS, MODELS_DIR, PROCESSED_DIR
from .feature_extraction import build_aggregate_features


class SessionEncoder(nn.Module):
    def __init__(self, input_dim: int, emb_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, emb_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.net(x)
        return nn.functional.normalize(z, p=2, dim=1)


@dataclass
class UserTemplateBuilder:
    scaler: StandardScaler
    feature_columns: list[str]

    def transform(self, feature_df: pd.DataFrame) -> np.ndarray:
        x = feature_df[self.feature_columns].fillna(0.0).values
        return self.scaler.transform(x)

    def build_centroids(self, feature_df: pd.DataFrame) -> dict[str, np.ndarray]:
        centroids: dict[str, np.ndarray] = {}
        for uid, g in feature_df.groupby("user_id"):
            x = self.transform(g)
            centroids[str(uid)] = np.mean(x, axis=0)
        return centroids


def _build_pairs(embeddings: np.ndarray, users: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    scores = []
    labels = []
    n = len(embeddings)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(np.dot(embeddings[i], embeddings[j]) / ((np.linalg.norm(embeddings[i]) + 1e-9) * (np.linalg.norm(embeddings[j]) + 1e-9)))
            scores.append(sim)
            labels.append(1 if users[i] == users[j] else 0)
    return np.array(scores), np.array(labels)


def train_user_encoder() -> dict:
    events_path = PROCESSED_DIR / "all_events.parquet"
    sessions_path = PROCESSED_DIR / "all_sessions.parquet"
    events = pd.read_parquet(events_path)
    sessions = pd.read_parquet(sessions_path)

    feats = build_aggregate_features(events, sessions)
    feats = feats[feats["user_id"].notna()].copy()
    user_counts = feats["user_id"].value_counts()
    valid_users = user_counts[user_counts >= 2].index
    feats = feats[feats["user_id"].isin(valid_users)].copy()

    if feats.empty or feats["user_id"].nunique() < 2:
        raise RuntimeError("Need at least two users with multiple sessions for user encoder training")

    x = feats[AGGREGATE_FEATURE_COLUMNS].fillna(0.0).values
    users = feats["user_id"].astype(str).to_numpy()

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x)

    x_train, x_test, u_train, u_test = train_test_split(
        x_scaled, users, test_size=0.3, random_state=42, stratify=users
    )

    input_dim = x_train.shape[1]
    emb_dim = 128
    model = SessionEncoder(input_dim=input_dim, emb_dim=emb_dim)
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.TripletMarginLoss(margin=0.7)

    train_x = torch.tensor(x_train, dtype=torch.float32)
    train_u = np.array(u_train)

    def sample_triplets() -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        anchors, positives, negatives = [], [], []
        by_user: dict[str, list[int]] = {}
        for idx, uid in enumerate(train_u):
            by_user.setdefault(uid, []).append(idx)

        all_users = list(by_user.keys())
        for uid, idxs in by_user.items():
            if len(idxs) < 2:
                continue
            neg_users = [u for u in all_users if u != uid and by_user[u]]
            if not neg_users:
                continue
            for i in range(len(idxs) - 1):
                a_idx = idxs[i]
                p_idx = idxs[i + 1]
                n_uid = np.random.choice(neg_users)
                n_idx = int(np.random.choice(by_user[n_uid]))
                anchors.append(train_x[a_idx])
                positives.append(train_x[p_idx])
                negatives.append(train_x[n_idx])

        if not anchors:
            raise RuntimeError("Unable to sample triplets from current training set")

        return torch.stack(anchors), torch.stack(positives), torch.stack(negatives)

    model.train()
    epochs = 40
    losses = []
    for _ in range(epochs):
        a, p, n = sample_triplets()
        za = model(a)
        zp = model(p)
        zn = model(n)
        loss = criterion(za, zp, zn)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))

    model.eval()
    with torch.no_grad():
        test_emb = model(torch.tensor(x_test, dtype=torch.float32)).numpy()

    pair_scores, pair_labels = _build_pairs(test_emb, np.array(u_test))
    auc = roc_auc_score(pair_labels, pair_scores) if len(np.unique(pair_labels)) > 1 else 0.5

    # EER approximation.
    thresholds = np.linspace(-1.0, 1.0, 200)
    fars, frrs = [], []
    for th in thresholds:
        pred_same = pair_scores >= th
        far = float(np.mean((pred_same == 1) & (pair_labels == 0)))
        frr = float(np.mean((pred_same == 0) & (pair_labels == 1)))
        fars.append(far)
        frrs.append(frr)
    idx = int(np.argmin(np.abs(np.array(fars) - np.array(frrs))))
    eer = float((fars[idx] + frrs[idx]) / 2.0)
    threshold = float(thresholds[idx])

    torch.save(model.state_dict(), MODELS_DIR / "user_encoder.pt")
    (MODELS_DIR / "user_encoder_config.json").write_text(
        json.dumps({"input_dim": input_dim, "embedding_dim": emb_dim, "threshold": threshold}, indent=2),
        encoding="utf-8",
    )

    template_builder = {
        "scaler": scaler,
        "feature_columns": AGGREGATE_FEATURE_COLUMNS,
    }
    joblib.dump(template_builder, MODELS_DIR / "user_template_builder.joblib")

    metrics = {
        "pair_roc_auc": float(auc),
        "eer": eer,
        "eer_threshold": threshold,
        "pair_trials": int(len(pair_scores)),
        "users": int(feats["user_id"].nunique()),
        "sessions": int(len(feats)),
        "train_loss_final": float(losses[-1]) if losses else None,
    }
    (MODELS_DIR / "user_train_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    print(json.dumps(train_user_encoder(), indent=2))
