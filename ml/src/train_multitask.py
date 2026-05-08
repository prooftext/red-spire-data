from __future__ import annotations

import json

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler

from .config import AGGREGATE_FEATURE_COLUMNS, MODELS_DIR, PROCESSED_DIR
from .feature_extraction import build_aggregate_features
from .labeling import label_sessions


class MultiTaskModel(nn.Module):
    def __init__(self, input_dim: int, num_classes: int, emb_dim: int = 128):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, emb_dim),
            nn.ReLU(),
        )
        self.mode_head = nn.Linear(emb_dim, num_classes)
        self.embed_head = nn.Linear(emb_dim, emb_dim)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.encoder(x)
        logits = self.mode_head(h)
        emb = nn.functional.normalize(self.embed_head(h), p=2, dim=1)
        return logits, emb


def train_multitask(alpha: float = 0.5) -> dict:
    events = pd.read_parquet(PROCESSED_DIR / "all_events.parquet")
    sessions = pd.read_parquet(PROCESSED_DIR / "all_sessions.parquet")

    labels = label_sessions(events, sessions)
    sessions = sessions.merge(labels[["session_id", "weak_label_mode"]], on="session_id", how="left")
    sessions["label_mode"] = sessions["label_mode"].fillna(sessions["weak_label_mode"])

    feats = build_aggregate_features(events, sessions)
    feats = feats[feats["label_mode"].notna() & feats["user_id"].notna()].copy()

    le = LabelEncoder()
    y_mode = le.fit_transform(feats["label_mode"].astype(str).values)
    user_labels = feats["user_id"].astype(str).to_numpy()

    scaler = StandardScaler()
    x = scaler.fit_transform(feats[AGGREGATE_FEATURE_COLUMNS].fillna(0.0).values)

    x_train, x_val, y_train, y_val, u_train, u_val = train_test_split(
        x, y_mode, user_labels, test_size=0.2, random_state=42, stratify=y_mode
    )

    model = MultiTaskModel(input_dim=x.shape[1], num_classes=len(le.classes_))
    ce = nn.CrossEntropyLoss()
    tri = nn.TripletMarginLoss(margin=0.7)
    opt = optim.Adam(model.parameters(), lr=1e-3)

    tx = torch.tensor(x_train, dtype=torch.float32)
    ty = torch.tensor(y_train, dtype=torch.long)
    tu = np.array(u_train)

    def sample_triplets() -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        by_user = {}
        for i, uid in enumerate(tu):
            by_user.setdefault(uid, []).append(i)

        a, p, n = [], [], []
        users = list(by_user.keys())
        for uid, idxs in by_user.items():
            if len(idxs) < 2:
                continue
            neg_users = [u for u in users if u != uid and by_user[u]]
            if not neg_users:
                continue
            for j in range(len(idxs) - 1):
                ai = idxs[j]
                pi = idxs[j + 1]
                nu = np.random.choice(neg_users)
                ni = int(np.random.choice(by_user[nu]))
                a.append(tx[ai])
                p.append(tx[pi])
                n.append(tx[ni])

        if not a:
            return tx[:1], tx[:1], tx[:1]
        return torch.stack(a), torch.stack(p), torch.stack(n)

    losses = []
    for _ in range(35):
        logits, _ = model(tx)
        mode_loss = ce(logits, ty)
        a, p, n = sample_triplets()
        _, za = model(a)
        _, zp = model(p)
        _, zn = model(n)
        metric_loss = tri(za, zp, zn)
        loss = mode_loss + alpha * metric_loss

        opt.zero_grad()
        loss.backward()
        opt.step()
        losses.append(float(loss.item()))

    torch.save(model.state_dict(), MODELS_DIR / "multitask_model.pt")
    (MODELS_DIR / "multitask_config.json").write_text(
        json.dumps(
            {
                "input_dim": x.shape[1],
                "classes": le.classes_.tolist(),
                "alpha": alpha,
                "epochs": 35,
                "final_loss": losses[-1] if losses else None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {"final_loss": losses[-1] if losses else None, "epochs": 35, "alpha": alpha}


if __name__ == "__main__":
    print(json.dumps(train_multitask(), indent=2))
