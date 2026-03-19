"""
Categorize text portions based on keystroke data.

Categories:
1. VERIFIED_HUMAN: Text we have keystrokes for
2. LIKELY_PASTED: Text in document but no keystrokes (paste events)
3. UNKNOWN: Text not in our keystroke db
4. AI_GENERATED: Text flagged as AI-generated
5. LIKELY_TRANSCRIBED: Typed from a source rather than composed
"""

from typing import List, Tuple
from datetime import datetime
import json
from app.services.scoring import calculate_transcription_likelihood

MIN_UDTIME_MICROS = -100_000
MAX_UDTIME_MICROS = 800_000

def reconstruct_text_from_keystrokes(events: List[dict]) -> str:
    """
    Reconstruct the text that was typed from keystroke events ONLY.
    
    This is a simplified reconstruction that handles basic typing.
    Returns the text that corresponds to actual keystroke events (not pasted text).
    """
    reconstructed = []
    
    for event in events:
        event_type = event.get('event_type', '')
        event_data = event.get('event_data', {})
        
        # Handle event_data as either dict or JSON string
        if isinstance(event_data, str):
            try:
                event_data = json.loads(event_data)
            except (json.JSONDecodeError, TypeError):
                event_data = {}
        
        # Only process keydown events, not paste events
        # Paste events are handled separately in create_text_segments
        if event_type == 'keydown':
            key = event_data.get('key', '')
            # Only include printable characters
            if len(key) == 1 and key.isprintable():
                reconstructed.append(key)
    
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


def _parse_event_data(event: dict) -> tuple[str, dict]:
    event_type = event.get('event_type') or event.get('eventType') or ''
    event_data = event.get('event_data') or event.get('eventData') or {}
    if isinstance(event_data, str):
        try:
            event_data = json.loads(event_data)
        except (json.JSONDecodeError, TypeError):
            event_data = {}
    return event_type, event_data


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_printable_key(key: str | None) -> bool:
    return isinstance(key, str) and len(key) == 1 and key.isprintable()


def _flatten_keystroke_positions(keystroke_spans: List[Tuple[int, int]], doc_length: int) -> List[int]:
    positions: List[int] = []
    for start, end in keystroke_spans:
        safe_start = max(0, start)
        safe_end = min(end, doc_length)
        if safe_start < safe_end:
            positions.extend(range(safe_start, safe_end))
    return positions


def _prepare_events_with_inferred_cursor(
    full_document: str,
    events: List[dict],
    keystroke_spans: List[Tuple[int, int]],
) -> List[dict]:
    """
    Normalize events and infer cursor positions when cursorPosition is missing.

    Inference is based on chronological event order (timestamp + sequence), then
    aligned to keystroke spans reconstructed from typed characters.
    """
    doc_length = len(full_document)
    typed_positions = _flatten_keystroke_positions(keystroke_spans, doc_length)

    prepared = []
    for index, event in enumerate(events):
        event_type, event_data = _parse_event_data(event)
        sequence = _to_int(
            event_data.get('sequence')
            or event.get('sequence_number')
            or event.get('sequence')
        )
        timestamp = _parse_timestamp(
            event_data.get('timestamp')
            or event_data.get('pressTime')
            or event.get('event_time')
        )
        explicit_cursor = _to_int(event_data.get('cursorPosition'))

        prepared.append({
            'event_type': event_type,
            'event_data': event_data,
            'sequence': sequence,
            'timestamp': timestamp,
            'index': index,
            'cursor_position': explicit_cursor,
        })

    prepared.sort(
        key=lambda item: (
            0 if item['timestamp'] is not None else 1,
            item['timestamp'].timestamp() if item['timestamp'] is not None else 0.0,
            0 if item['sequence'] is not None else 1,
            item['sequence'] if item['sequence'] is not None else 0,
            item['index'],
        )
    )

    cursor = 0
    typed_index = 0
    max_key_cursor = max(0, doc_length - 1)

    for item in prepared:
        event_type = item['event_type']
        event_data = item['event_data']
        key = event_data.get('key')
        cursor_pos = item.get('cursor_position')

        if cursor_pos is None:
            if event_type == 'keydown' and _is_printable_key(key):
                if typed_index < len(typed_positions):
                    cursor_pos = typed_positions[typed_index]
                else:
                    cursor_pos = min(cursor, max_key_cursor)
                typed_index += 1
                cursor = min(doc_length, cursor_pos + 1)
            elif event_type == 'keydown' and key == 'Backspace':
                cursor = max(0, cursor - 1)
                cursor_pos = cursor
            elif event_type == 'keydown' and key == 'Delete':
                cursor_pos = cursor
            elif event_type == 'navigation':
                if key in {'ArrowLeft', 'Left'}:
                    cursor = max(0, cursor - 1)
                elif key in {'ArrowRight', 'Right'}:
                    cursor = min(doc_length, cursor + 1)
                elif key == 'Home':
                    cursor = 0
                elif key == 'End':
                    cursor = doc_length
                cursor_pos = cursor
            elif event_type == 'paste':
                cursor_pos = cursor
                pasted_text = event_data.get('pastedText')
                if isinstance(pasted_text, str) and pasted_text:
                    cursor = min(doc_length, cursor + len(pasted_text))
            else:
                cursor_pos = cursor
        else:
            cursor = min(doc_length, max(0, cursor_pos))

        item['cursor_position'] = max(0, cursor_pos)

    return prepared


def extract_segment_metrics(events_with_cursor: List[dict], start: int, end: int) -> dict:
    keydown_events = []
    for event in events_with_cursor:
        event_type = event.get('event_type', '')
        event_data = event.get('event_data', {})
        if event_type != 'keydown':
            continue
        cursor_pos = event.get('cursor_position')
        if cursor_pos is None:
            continue
        if start <= cursor_pos < end:
            keydown_events.append(event_data)

    total_keystrokes = len(keydown_events)
    if total_keystrokes == 0:
        return {}

    dwell_times = [e.get('dwellTimeMicros') for e in keydown_events if e.get('dwellTimeMicros') is not None]
    avg_dwell = sum(dwell_times) / len(dwell_times) if dwell_times else 0
    std_dwell = (sum((x - avg_dwell) ** 2 for x in dwell_times) / len(dwell_times)) ** 0.5 if dwell_times else 0

    timestamps = [_parse_timestamp(e.get('timestamp') or e.get('pressTime')) for e in keydown_events]
    flight_times = []
    for i in range(len(timestamps) - 1):
        flight_time = keydown_events[i + 1].get('flightTimeMicros')
        current_timestamp = timestamps[i]
        next_timestamp = timestamps[i + 1]
        if flight_time is None and current_timestamp is not None and next_timestamp is not None:
            time_diff_seconds = (next_timestamp - current_timestamp).total_seconds()
            flight_time = int(time_diff_seconds * 1_000_000)

        if flight_time is None:
            continue

        if MIN_UDTIME_MICROS <= flight_time <= MAX_UDTIME_MICROS:
            flight_times.append(flight_time)

    avg_flight = sum(flight_times) / len(flight_times) if flight_times else 0
    std_flight = (sum((x - avg_flight) ** 2 for x in flight_times) / len(flight_times)) ** 0.5 if flight_times else 0

    backspaces = sum(1 for e in keydown_events if e.get('key') == 'Backspace')
    pauses_over_2sec = sum(1 for t in flight_times if t > 2_000_000)
    longest_pause_micros = max(flight_times) if flight_times else 0

    total_time_sec = 0
    if timestamps and timestamps[0] and timestamps[-1]:
        total_time_sec = (timestamps[-1] - timestamps[0]).total_seconds()

    wpm = (total_keystrokes / 5) / (total_time_sec / 60) if total_time_sec > 0 else 0

    timing_sample_count = min(len(dwell_times), len(flight_times) + 1) if total_keystrokes else 0

    return {
        "totalKeystrokes": total_keystrokes,
        "avgDwellTimeMicros": avg_dwell,
        "stdDwellTimeMicros": std_dwell,
        "avgFlightTimeMicros": avg_flight,
        "stdFlightTimeMicros": std_flight,
        "wpm": wpm,
        "backspaceCount": backspaces,
        "pausesOver2Sec": pauses_over_2sec,
        "longestPauseMicros": longest_pause_micros,
        "pasteRatio": 0.0,
        "timingSampleCount": timing_sample_count,
    }


def create_text_segments(
    full_document: str,
    events: List[dict],
    transcription_threshold: float = 0.7,
) -> List[dict]:
    """
    Create contiguous text segments with categorization.
    Identifies which segments were pasted based on actual pastedText from paste events.
    
    Returns list of segment dicts with:
    - start, end: positions in document
    - text: the actual text of the segment
    - category: VERIFIED_HUMAN, LIKELY_PASTED, UNKNOWN
    - source: "keystroke", "pasted", or "unknown"
    """
    if not full_document:
        return []
    
    # Map character positions to their source
    char_source = ['unknown'] * len(full_document)
    pasted_texts = {}  # Map of position -> pasted text for pasted content

    # Build keystroke spans and infer cursor locations for events that don't provide them
    keystroke_spans = identify_keystroke_spans(full_document, reconstruct_text_from_keystrokes(events))
    prepared_events = _prepare_events_with_inferred_cursor(full_document, events, keystroke_spans)
    
    # Extract all pasted text segments
    for event in prepared_events:
        event_type = event.get('event_type', '')
        event_data = event.get('event_data', {})
        
        if event_type == 'paste' and event_data:
            # event_data is a dict with pastedText
            pasted_text = event_data.get('pastedText')
            cursor_pos = event_data.get('cursorPosition')
            if cursor_pos is None:
                cursor_pos = event.get('cursor_position')
            
            if pasted_text and cursor_pos is not None:
                # Find where this pasted text appears in the document starting from cursor position
                pasted_start = full_document.find(pasted_text, cursor_pos)
                if pasted_start == -1:
                    pasted_start = full_document.find(pasted_text)
                if pasted_start != -1:
                    pasted_end = pasted_start + len(pasted_text)
                    for i in range(pasted_start, min(pasted_end, len(full_document))):
                        char_source[i] = 'pasted'
                    pasted_texts[pasted_start] = (pasted_end, pasted_text)
            elif pasted_text and cursor_pos is None:
                # If no cursor position, search for the pasted text anywhere in document
                pasted_start = full_document.find(pasted_text)
                if pasted_start != -1:
                    pasted_end = pasted_start + len(pasted_text)
                    for i in range(pasted_start, min(pasted_end, len(full_document))):
                        char_source[i] = 'pasted'
                    pasted_texts[pasted_start] = (pasted_end, pasted_text)
    
    for start, end in keystroke_spans:
        for i in range(start, min(end, len(full_document))):
            char_source[i] = 'keystroke'
    
    # Create segments by merging consecutive characters with the same source
    segments = []
    current_start = 0
    current_source = char_source[0]
    
    for i in range(1, len(full_document) + 1):
        next_source = char_source[i] if i < len(full_document) else None
        
        if next_source != current_source:
            # End of current segment
            segment_text = full_document[current_start:i]
            
            # Determine category based on source
            if current_source == 'keystroke':
                segment_metrics = extract_segment_metrics(prepared_events, current_start, i)
                segment_transcription = None
                if segment_metrics:
                    segment_transcription = calculate_transcription_likelihood(segment_metrics)
                if segment_transcription is not None and segment_transcription >= transcription_threshold:
                    category = 'LIKELY_TRANSCRIBED'
                else:
                    category = 'VERIFIED_HUMAN'
            elif current_source == 'pasted':
                category = 'LIKELY_PASTED'
            else:
                category = 'UNKNOWN'
            
            segments.append({
                'start': current_start,
                'end': i,
                'text': segment_text,
                'category': category,
                'source': current_source
            })
            
            current_start = i
            current_source = next_source
    
    return segments


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
        },
        "LIKELY_TRANSCRIBED": {
            "label": "Likely Transcribed",
            "description": "Typed from a source rather than composed",
            "color": "#B3D9FF",  # Light blue
            "textColor": "#0B3D91"
        }
    }
    return info.get(category, {})
