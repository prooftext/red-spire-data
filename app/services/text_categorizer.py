"""
Categorize text portions based on keystroke data.

Categories:
1. VERIFIED_HUMAN: Text we have keystrokes for
2. LIKELY_PASTED: Text in document but no keystrokes (paste events)
3. UNKNOWN: Text not in our keystroke db
4. AI_GENERATED: Text flagged as AI-generated
"""

from typing import List, Tuple
from app.models.requests import KeystrokeEvent

def reconstruct_text_from_keystrokes(events: List[dict]) -> str:
    """
    Reconstruct the text that was typed from keystroke events.
    
    This is a simplified reconstruction that handles basic typing.
    Returns the text that corresponds to actual keystroke events.
    """
    reconstructed = []
    
    for event in events:
        event_type = event.get('event_type', '')
        event_data = event.get('event_data', {})
        
        if event_type == 'keydown':
            key = event_data.get('key', '')
            # Only include printable characters
            if len(key) == 1 and key.isprintable():
                reconstructed.append(key)
        elif event_type == 'paste':
            # Paste events include the pasted text
            pasted_text = event_data.get('pastedText', '')
            reconstructed.append(pasted_text)
    
    return ''.join(reconstructed)


def identify_keystroke_spans(document_text: str, keystroke_text: str) -> List[Tuple[int, int]]:
    """
    Identify which character positions in the document correspond to actual keystrokes.
    
    Returns list of (start_pos, end_pos) tuples representing spans with keystrokes.
    """
    if not keystroke_text or not document_text:
        return []
    
    spans = []
    search_pos = 0
    
    for i, char in enumerate(keystroke_text):
        # Find where this keystroke text appears in the document
        match_pos = document_text.find(keystroke_text[i:], search_pos)
        if match_pos != -1:
            # Track this character as part of a keystroke span
            if not spans or spans[-1][1] != match_pos:
                spans.append((match_pos, match_pos + 1))
            else:
                # Extend the current span
                spans[-1] = (spans[-1][0], match_pos + 1)
            search_pos = match_pos + 1
    
    return spans


def categorize_text_spans(
    full_document: str,
    keystroke_spans: List[Tuple[int, int]],
    paste_events_count: int = 0
) -> List[dict]:
    """
    Categorize each character in the document into one of 4 categories.
    
    Returns list of dicts with 'char', 'category', 'start', 'end'.
    
    Categories:
    - VERIFIED_HUMAN: has keystroke events
    - LIKELY_PASTED: no keystrokes and paste events exist
    - UNKNOWN: not in database
    - AI_GENERATED: flagged as AI text (would need additional analysis)
    """
    
    # Create a map of which positions have keystrokes
    char_categories = []
    keystroke_positions = set()
    
    for start, end in keystroke_spans:
        for pos in range(start, end):
            keystroke_positions.add(pos)
    
    # Categorize each character
    for i, char in enumerate(full_document):
        if i in keystroke_positions:
            category = "VERIFIED_HUMAN"
        elif paste_events_count > 0:
            # If we have paste events, text without keystrokes is likely pasted
            category = "LIKELY_PASTED"
        else:
            # No keystroke data for this text
            category = "UNKNOWN"
        
        char_categories.append({
            "char": char,
            "category": category,
            "position": i
        })
    
    return char_categories


def get_category_info(category: str) -> dict:
    """Get display info for a category."""
    info = {
        "VERIFIED_HUMAN": {
            "label": "Human Verified",
            "description": "Text with keystroke records",
            "color": "#90EE90",  # Light green
            "textColor": "#155724"
        },
        "LIKELY_PASTED": {
            "label": "Likely Pasted",
            "description": "Text without keystroke records (copy/paste)",
            "color": "#FFB6C1",  # Light pink
            "textColor": "#721c24"
        },
        "UNKNOWN": {
            "label": "Unknown",
            "description": "Text not in keystroke database",
            "color": "#E0E0E0",  # Light gray
            "textColor": "#333333"
        },
        "AI_GENERATED": {
            "label": "AI Generated",
            "description": "Text flagged as AI-generated",
            "color": "#FFD700",  # Gold
            "textColor": "#856404"
        }
    }
    return info.get(category, {})
