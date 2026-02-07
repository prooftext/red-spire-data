from pydantic import BaseModel
from typing import Optional

class CollectResponse(BaseModel):
    session_id: str
    human_probability: float
    verification_status: str
    metrics: dict

class VerifyResponse(BaseModel):
    can_prove_human: str  # "yes", "no", "maybe"
    confidence: float
    matched_session_id: Optional[str] = None


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