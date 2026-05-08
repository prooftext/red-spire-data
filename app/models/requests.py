from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class KeystrokeEvent(BaseModel):
    eventType: str = Field(..., description="Type of event: 'keydown', 'paste', 'delete', 'format', 'navigation'")
    key: Optional[str] = Field(None, description="The character key (for keydown events)")
    keyCode: Optional[int] = Field(None, description="Numeric key code (for keydown events)")
    timestamp: datetime = Field(..., description="When the event occurred (ISO 8601)")
    pressTime: Optional[datetime] = Field(None, description="When the key was pressed")
    releaseTime: Optional[datetime] = Field(None, description="When the key was released")
    dwellTimeMicros: Optional[int] = Field(None, description="Duration key was held (microseconds)")
    flightTimeMicros: Optional[int] = Field(None, description="Time between releasing this key and next (microseconds)")
    cursorPosition: Optional[int] = Field(None, description="Optional position in document where event occurred (inferred from event timing/order when omitted)")
    sequence: int = Field(..., description="Sequential number for ordering events")
    pastedLength: Optional[int] = Field(None, description="Number of characters pasted")
    pastedText: Optional[str] = Field(None, description="The actual text that was pasted (required for accurate paste detection)")
    deletedLength: Optional[int] = Field(None, description="Number of characters deleted")
    formatAction: Optional[str] = Field(None, description="Type of formatting applied ('bold', 'italic', etc.)")
    selectedRange: Optional[dict] = Field(None, description="Range of text affected {start, end}")
    modifiers: Optional[dict] = Field(None, description="Keys held during event (Shift, Ctrl, Alt)")

class CollectRequest(BaseModel):
    session_id: str
    user_id: str
    document_text: str
    events: List[KeystrokeEvent]
    metadata: dict = {}

class VerifyRequest(BaseModel):
    document_text: str
    top_k: int = 5


class ScoreSessionRequest(BaseModel):
    document_text: str
    events: List[KeystrokeEvent]
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    include_segments: bool = True