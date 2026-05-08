from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class NormalizedEvent(BaseModel):
    dataset: str
    session_id: str
    user_id: str
    event_index: int
    event_type: str
    key_code: Optional[int] = None
    key: Optional[str] = None
    timestamp_us: Optional[int] = None
    dwell_us: Optional[int] = None
    flight_us: Optional[int] = None
    cursor_position: Optional[int] = None
    paste_len: Optional[int] = None
    delete_len: Optional[int] = None
    label_mode: Optional[str] = None


class SessionSummary(BaseModel):
    dataset: str
    session_id: str
    user_id: str
    document_text_len: int = 0
    total_events: int = 0
    keydown_count: int = 0
    paste_event_count: int = 0
    total_pasted_chars: int = 0
    paste_ratio: float = 0.0
    delete_event_count: int = 0
    delete_ratio: float = 0.0
    mean_dwell: float = 0.0
    std_dwell: float = 0.0
    mean_flight: float = 0.0
    std_flight: float = 0.0
    weak_label_mode: Optional[str] = None
    weak_label_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
