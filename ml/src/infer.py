from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch

from .config import AGGREGATE_FEATURE_COLUMNS
from .feature_extraction import build_aggregate_features
from .train_user_encoder import SessionEncoder


def _events_to_df(events: list[dict], session_id: str = "live_session", user_id: str = "live_user") -> pd.DataFrame:
    rows = []
    for i, e in enumerate(events):
        rows.append(
            {
                "dataset": "live",
                "session_id": session_id,
                "user_id": user_id,
                "event_index": int(e.get("sequence", i)),
                "event_type": str(e.get("eventType") or e.get("event_type") or "unknown").lower(),
                "key_code": e.get("keyCode") or e.get("key_code"),
                "key": e.get("key"),
                "timestamp_us": int(pd.to_datetime(e.get("timestamp"), utc=True).value // 1000) if e.get("timestamp") else None,
                "dwell_us": e.get("dwellTimeMicros") or e.get("dwell_us"),
                "flight_us": e.get("flightTimeMicros") or e.get("flight_us"),
                "cursor_position": e.get("cursorPosition") or e.get("cursor_position"),
                "paste_len": e.get("pastedLength") or e.get("paste_len"),
                "delete_len": e.get("deletedLength") or e.get("delete_len"),
                "modifiers": e.get("modifiers"),
            }
        )
    return pd.DataFrame(rows)


def reconstruct_segments(events: list[dict], document_text: str) -> list[dict[str, Any]]:
    cursor = 0
    text = []
    labels: list[str] = []

    def _insert(chars: str, label: str) -> None:
        nonlocal cursor
        for c in chars:
            text.insert(cursor, c)
            labels.insert(cursor, label)
            cursor += 1

    for ev in sorted(events, key=lambda x: int(x.get("sequence", 0))):
        et = str(ev.get("eventType") or "").lower()
        pos = ev.get("cursorPosition")
        if pos is not None:
            cursor = max(0, min(int(pos), len(text)))

        if et in {"keydown", "keypress"}:
            key = ev.get("key")
            if key and len(str(key)) == 1:
                _insert(str(key), "handwritten")
        elif et == "paste":
            pasted = ev.get("pastedText")
            if pasted is None:
                pasted = " " * int(ev.get("pastedLength") or 0)
            _insert(str(pasted), "pasted")
        elif et in {"delete", "backspace"}:
            dlen = int(ev.get("deletedLength") or 1)
            start = max(0, cursor - dlen)
            del text[start:cursor]
            del labels[start:cursor]
            cursor = start

    if not text and document_text:
        text = list(document_text)
        labels = ["unknown"] * len(text)

    spans = []
    if not labels:
        return spans

    start = 0
    cur = labels[0]
    for i in range(1, len(labels)):
        if labels[i] != cur:
            spans.append({"start": start, "end": i, "label": cur})
            start = i
            cur = labels[i]
    spans.append({"start": start, "end": len(labels), "label": cur})
    return spans


def apply_transcribed_overlay(spans: list[dict], mode_probs: dict[str, float]) -> list[dict]:
    transcribed_p = mode_probs.get("transcribed", 0.0)
    mixed_p = mode_probs.get("mixed", 0.0)
    out = []
    for s in spans:
        label = s["label"]
        confidence = 0.7 if label in {"handwritten", "pasted"} else 0.4
        if label == "pasted" and (transcribed_p >= 0.5 or mixed_p >= 0.45):
            label = "transcribed"
            confidence = max(confidence, transcribed_p)
        out.append({**s, "label": label, "confidence": float(confidence)})
    return out


class InferenceBundle:
    def __init__(self, production_dir: Path):
        self.production_dir = production_dir
        self.mode_payload = joblib.load(production_dir / "mode_model.joblib")
        self.aggregate_scaler = joblib.load(production_dir / "aggregate_scaler.joblib")
        self.user_template_builder = joblib.load(production_dir / "user_template_builder.joblib")

        cfg = json.loads((production_dir / "user_encoder_config.json").read_text(encoding="utf-8"))
        self.user_threshold = float(cfg.get("threshold", 0.78))
        self.encoder = SessionEncoder(input_dim=int(cfg["input_dim"]), emb_dim=int(cfg["embedding_dim"]))
        self.encoder.load_state_dict(torch.load(production_dir / "user_encoder.pt", map_location="cpu"))
        self.encoder.eval()

        self.metadata = json.loads((production_dir / "metadata.json").read_text(encoding="utf-8"))

    def score_session(
        self,
        events: list[dict],
        document_text: str,
        user_id: str | None = None,
        enrolled_templates: dict[str, list[float]] | None = None,
    ) -> dict:
        if not events:
            return {
                "mode": "mixed",
                "mode_confidence": 0.0,
                "mode_probs": {"original": 0.0, "mixed": 1.0, "transcribed": 0.0},
                "user_match": {"is_match": False, "score": 0.0, "threshold": self.user_threshold},
                "signals": {},
                "segments": [],
            }

        sid = "live"
        uid = user_id or "unknown_user"
        events_df = _events_to_df(events, session_id=sid, user_id=uid)
        sessions_df = pd.DataFrame(
            [
                {
                    "dataset": "live",
                    "session_id": sid,
                    "user_id": uid,
                    "document_text_len": len(document_text or ""),
                    "label_mode": None,
                }
            ]
        )

        features = build_aggregate_features(events_df, sessions_df)
        x = features[self.mode_payload["feature_columns"]].fillna(0.0).values
        x_scaled = self.aggregate_scaler.transform(x)

        mode_model = self.mode_payload["model"]
        mode_le = self.mode_payload["label_encoder"]
        probs = mode_model.predict_proba(x_scaled)[0]
        cls_idx = int(np.argmax(probs))
        mode = str(mode_le.classes_[cls_idx])
        mode_probs = {str(mode_le.classes_[i]): float(probs[i]) for i in range(len(probs))}

        template_score = 0.0
        is_match = False
        if user_id and enrolled_templates and user_id in enrolled_templates:
            scaler = self.user_template_builder["scaler"]
            columns = self.user_template_builder["feature_columns"]
            user_feature = scaler.transform(features[columns].fillna(0.0).values)[0]
            with torch.no_grad():
                emb = self.encoder(torch.tensor(user_feature.reshape(1, -1), dtype=torch.float32)).numpy()[0]
            tpl = np.array(enrolled_templates[user_id], dtype=float)
            template_score = float(np.dot(emb, tpl) / ((np.linalg.norm(emb) + 1e-9) * (np.linalg.norm(tpl) + 1e-9)))
            is_match = template_score >= self.user_threshold

        spans = reconstruct_segments(events, document_text)
        spans = apply_transcribed_overlay(spans, mode_probs)

        signals = {
            "paste_ratio": float(features.iloc[0]["paste_ratio"]),
            "delete_ratio": float(features.iloc[0]["delete_ratio"]),
            "mean_dwell": float(features.iloc[0]["dwell_mean"]),
            "std_flight": float(features.iloc[0]["flight_std"]),
        }

        return {
            "mode": mode,
            "mode_confidence": float(np.max(probs)),
            "mode_probs": mode_probs,
            "user_match": {
                "is_match": bool(is_match),
                "score": float(template_score),
                "threshold": float(self.user_threshold),
            },
            "signals": signals,
            "segments": spans,
        }
