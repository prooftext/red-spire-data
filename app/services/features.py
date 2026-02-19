from typing import List
from app.models.requests import KeystrokeEvent

MIN_UDTIME_MICROS = -100_000
MAX_UDTIME_MICROS = 800_000

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
    - pausesOver2Sec, longestPauseMicros (microseconds)
    - pasteRatio
    """
    if not events:
        return {}
    
    total_keystrokes = len(events)
    dwell_times = [e.dwellTimeMicros for e in events if e.dwellTimeMicros is not None]
    
    # Calculate flight times from event data or timestamp differences
    flight_times = []
    for i in range(len(events) - 1):
        if events[i+1].flightTimeMicros is not None:
            flight_time_micros = events[i+1].flightTimeMicros
        elif events[i+1].timestamp and events[i].timestamp:
            time_diff_seconds = (events[i+1].timestamp - events[i].timestamp).total_seconds()
            flight_time_micros = int(time_diff_seconds * 1_000_000)
        else:
            continue

        if MIN_UDTIME_MICROS <= flight_time_micros <= MAX_UDTIME_MICROS:
            flight_times.append(flight_time_micros)
    
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
    
    # Count pauses over 2 seconds (2,000,000 microseconds)
    pauses_over_2sec = sum(1 for t in flight_times if t > 2_000_000)
    longest_pause_micros = max(flight_times) if flight_times else 0
    
    paste_ratio = paste_events / total_keystrokes if total_keystrokes else 0
    timing_sample_count = min(len(dwell_times), len(flight_times) + 1) if total_keystrokes else 0
    
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
        "longestPauseMicros": longest_pause_micros,
        "pasteRatio": paste_ratio,
        "timingSampleCount": timing_sample_count
    }