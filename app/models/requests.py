from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class KeystrokeEvent(BaseModel):
    eventType: str
    key: Optional[str] = None
    keyCode: Optional[int] = None
    timestamp: datetime
    pressTime: Optional[datetime] = None
    releaseTime: Optional[datetime] = None
    dwellTimeMicros: Optional[int] = None
    flightTimeMicros: Optional[int] = None
    cursorPosition: Optional[int] = None
    sequence: int
    pastedLength: Optional[int] = None
    deletedLength: Optional[int] = None
    formatAction: Optional[str] = None
    selectedRange: Optional[dict] = None
    modifiers: Optional[dict] = None

class CollectRequest(BaseModel):
    session_id: str
    user_id: str
    document_text: str
    events: List[KeystrokeEvent]
    metadata: dict = {}

class VerifyRequest(BaseModel):
    document_text: str