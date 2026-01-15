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