from typing import List
from app.models.requests import KeystrokeEvent

def extract_metrics(events: List[KeystrokeEvent]) -> dict:
    """
    Compute session-level metrics from raw events.
    
    Returns dict with:
    - totalKeystrokes
    - avgDwellTimeMicros, stdDwellTimeMicros
    - avgFlightTimeMicros, stdFlightTimeMicros
    - wpm (words per minute)
    - pasteEvents, copyEvents
    - backspaceCount, deleteCount
    - formatChanges
    - pausesOver2Sec, longestPauseMs
    - pasteRatio
    """
    if not events:
        return {}
    
    total_keystrokes = len(events)
    dwell_times = [e.dwellTimeMicros for e in events if e.dwellTimeMicros is not None]
    flight_times = [e.flightTimeMicros for e in events if e.flightTimeMicros is not None]
    
    avg_dwell = sum(dwell_times) / len(dwell_times) if dwell_times else 0
    std_dwell = (sum((x - avg_dwell)**2 for x in dwell_times) / len(dwell_times))**0.5 if dwell_times else 0
    avg_flight = sum(flight_times) / len(flight_times) if flight_times else 0
    std_flight = (sum((x - avg_flight)**2 for x in flight_times) / len(flight_times))**0.5 if flight_times else 0
    
    # Rough WPM calculation
    total_time_sec = (events[-1].timestamp - events[0].timestamp).total_seconds() if len(events) > 1 else 1
    wpm = (total_keystrokes / 5) / (total_time_sec / 60) if total_time_sec > 0 else 0
    
    paste_events = sum(1 for e in events if e.pastedLength and e.pastedLength > 0)
    backspace_count = sum(1 for e in events if e.key == 'Backspace')
    delete_count = sum(1 for e in events if e.key == 'Delete')
    format_changes = sum(1 for e in events if e.formatAction)
    
    pauses_over_2sec = sum(1 for e in events if e.flightTimeMicros and e.flightTimeMicros > 2000000)
    longest_pause = max((e.flightTimeMicros for e in events if e.flightTimeMicros), default=0)
    
    paste_ratio = paste_events / total_keystrokes if total_keystrokes else 0
    
    return {
        "totalKeystrokes": total_keystrokes,
        "avgDwellTimeMicros": avg_dwell,
        "stdDwellTimeMicros": std_dwell,
        "avgFlightTimeMicros": avg_flight,
        "stdFlightTimeMicros": std_flight,
        "wpm": wpm,
        "pasteEvents": paste_events,
        "backspaceCount": backspace_count,
        "deleteCount": delete_count,
        "formatChanges": format_changes,
        "pausesOver2Sec": pauses_over_2sec,
        "longestPauseMs": longest_pause / 1000 if longest_pause else 0,
        "pasteRatio": paste_ratio
    }