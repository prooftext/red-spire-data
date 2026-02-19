"""
Documentation endpoints for the Prooftext API.
Provides information about supported event types and API schema.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()


class EventTypeDoc(BaseModel):
    """Documentation for a supported event type"""
    name: str
    description: str
    fields: dict  # Field name -> description
    example: dict


# Supported event types
SUPPORTED_EVENT_TYPES = [
    EventTypeDoc(
        name="keydown",
        description="A keyboard key was pressed",
        fields={
            "key": "The character that was typed (e.g., 'a', 'A', ' ')",
            "keyCode": "The numeric key code (e.g., 65 for 'A')",
            "timestamp": "When the key was pressed (ISO 8601 format)",
            "dwellTimeMicros": "How long the key was held down in microseconds",
            "flightTimeMicros": "Time between releasing this key and pressing the next (microseconds)",
            "cursorPosition": "Position in the document where this key was inserted",
            "sequence": "Sequential number for ordering events",
            "modifiers": "Keys held during the keypress (e.g., Shift, Ctrl, Alt)"
        },
        example={
            "eventType": "keydown",
            "key": "H",
            "keyCode": 72,
            "timestamp": "2026-02-19T10:30:45.123Z",
            "dwellTimeMicros": 150000,
            "flightTimeMicros": 85000,
            "cursorPosition": 0,
            "sequence": 1,
            "modifiers": None
        }
    ),
    EventTypeDoc(
        name="paste",
        description="Text was pasted into the document (Ctrl+V or Cmd+V)",
        fields={
            "pastedText": "The actual text that was pasted (required for text analysis)",
            "pastedLength": "Number of characters pasted",
            "timestamp": "When the paste occurred (ISO 8601 format)",
            "cursorPosition": "Position in the document where the paste was inserted",
            "sequence": "Sequential number for ordering events"
        },
        example={
            "eventType": "paste",
            "pastedText": "Hello World",
            "pastedLength": 11,
            "timestamp": "2026-02-19T10:30:46.500Z",
            "cursorPosition": 5,
            "sequence": 2
        }
    ),
    EventTypeDoc(
        name="delete",
        description="One or more characters were deleted",
        fields={
            "deletedLength": "Number of characters deleted",
            "timestamp": "When the deletion occurred",
            "cursorPosition": "Position where the deletion happened",
            "sequence": "Sequential number for ordering events"
        },
        example={
            "eventType": "delete",
            "deletedLength": 3,
            "timestamp": "2026-02-19T10:30:47.000Z",
            "cursorPosition": 8,
            "sequence": 3
        }
    ),
    EventTypeDoc(
        name="format",
        description="Text formatting was applied (bold, italic, etc.)",
        fields={
            "formatAction": "Type of formatting (e.g., 'bold', 'italic', 'underline')",
            "selectedRange": "Dictionary with 'start' and 'end' positions of the formatted text",
            "timestamp": "When the formatting was applied",
            "sequence": "Sequential number for ordering events"
        },
        example={
            "eventType": "format",
            "formatAction": "bold",
            "selectedRange": {"start": 0, "end": 5},
            "timestamp": "2026-02-19T10:30:47.500Z",
            "sequence": 4
        }
    )
]


@router.get("/event-types", response_model=List[EventTypeDoc])
async def get_supported_event_types():
    """
    Get documentation for all supported keystroke event types.
    
    This endpoint provides detailed information about each event type that can be
    sent to the `/keystroke/collect` endpoint, including field descriptions and examples.
    
    **Event Types:**
    - `keydown`: Individual key presses with timing information
    - `paste`: Text pasted via clipboard, including the pasted text
    - `delete`: Character deletions
    - `format`: Text formatting changes (bold, italic, etc.)
    
    **Why pastedText is Important:**
    When capturing paste events, always include the `pastedText` field with the actual
    text that was pasted. This allows the verify endpoint to accurately highlight which
    portions of the document were typed vs. pasted, providing better insights into
    writing authenticity.
    
    Returns:
        List of EventTypeDoc objects describing each supported event type
    """
    return SUPPORTED_EVENT_TYPES


@router.get("/api-schema")
async def get_api_schema():
    """
    Get detailed API schema and usage information.
    
    Returns endpoint structure, request/response models, and implementation notes.
    """
    return {
        "version": "1.0.0",
        "title": "Prooftext Keystroke Biometrics API",
        "description": "Captures keystroke events, analyzes typing patterns, and verifies text authenticity",
        "endpoints": {
            "collect": {
                "path": "/api/v1/keystroke/collect",
                "method": "POST",
                "description": "Submit keystroke events for a typing session",
                "request": "CollectRequest with session_id, user_id, document_text, and events array",
                "response": "CollectResponse with human_probability, verification_status, and metrics",
                "important_notes": [
                    "For paste events, always include pastedText field",
                    "Maintain sequence numbering for proper event ordering",
                    "Include accurate timestamps in ISO 8601 format",
                    "cursorPosition helps identify where pasted text was inserted"
                ]
            },
            "verify": {
                "path": "/api/v1/keystroke/verify",
                "method": "POST",
                "description": "Verify if a document text matches previously collected sessions",
                "request": "VerifyRequest with document_text",
                "response": "VerifyResponse with can_prove_human verdict, confidence, and text_categorization",
                "text_categorization_fields": {
                    "start": "Start position in document",
                    "end": "End position in document",
                    "text": "The actual text segment",
                    "category": "VERIFIED_HUMAN, LIKELY_PASTED, or UNKNOWN",
                    "source": "keystroke, pasted, or unknown"
                }
            },
            "event-types": {
                "path": "/api/v1/keystroke/event-types",
                "method": "GET",
                "description": "Get documentation for all supported event types",
                "response": "List of EventTypeDoc with examples and field descriptions"
            }
        }
    }
