from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MLInferenceService:
    def __init__(self, production_dir: Path):
        self.production_dir = production_dir
        self.bundle = None
        self.available = False
        self.model_version = "unavailable"
        self._import_error: str | None = None

    def load(self) -> None:
        try:
            from ml.src.infer import InferenceBundle

            self.bundle = InferenceBundle(self.production_dir)
            self.available = True
            self.model_version = str(self.bundle.metadata.get("model_version", "unknown"))
            logger.info("Loaded ML inference bundle version=%s", self.model_version)
        except Exception as exc:
            self.available = False
            self.bundle = None
            self._import_error = str(exc)
            logger.warning("ML inference bundle unavailable: %s", exc)

    def score_session(self, events: list[dict], document_text: str, user_id: str | None = None, enrolled_template: list[float] | None = None) -> dict:
        if not self.available or not self.bundle:
            return {
                "mode": "mixed",
                "mode_confidence": 0.0,
                "mode_probs": {"original": 0.0, "mixed": 1.0, "transcribed": 0.0},
                "user_match": {"is_match": False, "score": 0.0, "threshold": 0.78},
                "signals": {},
                "segments": [],
            }

        templates = None
        if user_id and enrolled_template is not None:
            templates = {user_id: enrolled_template}

        return self.bundle.score_session(
            events=events,
            document_text=document_text,
            user_id=user_id,
            enrolled_templates=templates,
        )

    def compute_session_embedding(self, events: list[dict], document_text: str, user_id: str | None = None) -> list[float] | None:
        if not self.available or not self.bundle:
            return None

        try:
            import pandas as pd
            import torch

            from ml.src.infer import _events_to_df
            from ml.src.feature_extraction import build_aggregate_features
        except Exception as exc:
            logger.warning("ML embedding dependencies unavailable: %s", exc)
            return None

        sid = "embed_live"
        uid = user_id or "unknown_user"
        events_df = _events_to_df(events, session_id=sid, user_id=uid)
        sessions_df = pd.DataFrame(
            [{"dataset": "live", "session_id": sid, "user_id": uid, "document_text_len": len(document_text or ""), "label_mode": None}]
        )

        features = build_aggregate_features(events_df, sessions_df)
        scaler = self.bundle.user_template_builder["scaler"]
        columns = self.bundle.user_template_builder["feature_columns"]
        transformed = scaler.transform(features[columns].fillna(0.0).values)
        with torch.no_grad():
            emb = self.bundle.encoder(torch.tensor(transformed, dtype=torch.float32)).numpy()[0]
        return emb.tolist()


_ml_service = MLInferenceService(Path(__file__).resolve().parents[1] / "ml" / "models" / "production")


def load_models_once() -> None:
    _ml_service.load()


def score_session(events: list, document_text: str, user_id: str | None = None, enrolled_template: list[float] | None = None) -> dict:
    normalized = []
    for idx, ev in enumerate(events):
        if hasattr(ev, "model_dump"):
            raw = ev.model_dump()
        elif isinstance(ev, dict):
            raw = ev
        else:
            raw = dict(ev)
        raw.setdefault("sequence", idx)
        normalized.append(raw)
    return _ml_service.score_session(normalized, document_text, user_id=user_id, enrolled_template=enrolled_template)


def compute_session_embedding(events: list, document_text: str, user_id: str | None = None) -> list[float] | None:
    normalized = []
    for idx, ev in enumerate(events):
        if hasattr(ev, "model_dump"):
            raw = ev.model_dump()
        elif isinstance(ev, dict):
            raw = ev
        else:
            raw = dict(ev)
        raw.setdefault("sequence", idx)
        normalized.append(raw)
    return _ml_service.compute_session_embedding(normalized, document_text=document_text, user_id=user_id)


def get_model_version() -> str:
    return _ml_service.model_version


def is_available() -> bool:
    return _ml_service.available
