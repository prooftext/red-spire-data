from pydantic import BaseModel
from typing import Optional

class CollectResponse(BaseModel):
    session_id: str
    human_probability: float
    verification_status: str
    metrics: dict

class TextSegment(BaseModel):
    start: int  # Start position in document
    end: int    # End position in document
    text: str   # The actual text
    category: str  # VERIFIED_HUMAN, LIKELY_PASTED, UNKNOWN, AI_GENERATED
    source: Optional[str] = None  # "keystroke", "pasted", "unknown" - more specific than category

class VerifyResponse(BaseModel):
    can_prove_human: str  # "yes", "no", "maybe"
    confidence: float
    session_id: Optional[str] = None
    username: Optional[str] = None
    document_text: Optional[str] = None
    text_categorization: Optional[list] = None  # List of TextSegment dicts
    pasted_segments: Optional[list] = None  # Deprecated: use text_categorization instead
    transcription_likelihood: Optional[float] = None
    model_ready: Optional[bool] = None
    detector_results: Optional[list] = None


class SessionMetadata(BaseModel):
    session_id: str
    user_id: str
    document_id: Optional[str] = None
    session_start: Optional[str] = None
    session_end: Optional[str] = None
    analyzed_at: Optional[str] = None


class LastSessionResponse(BaseModel):
    document_id: str
    session_id: Optional[str] = None


class MLScoreResponse(BaseModel):
    mode: str
    mode_confidence: float
    mode_probs: dict
    user_match: dict
    signals: dict
    segments: Optional[list] = None
    model_version: Optional[str] = None