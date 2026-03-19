import pytest
from app.services.scoring import calculate_human_score, determine_status, calculate_transcription_likelihood
from app.services.features import extract_metrics
from app.models.requests import KeystrokeEvent
from datetime import datetime

def test_calculate_human_score_returns_valid_probability():
    """Human score should always return a probability between 0 and 1"""
    metrics = {"pasteRatio": 0.1, "stdDwellTimeMicros": 10000, "totalKeystrokes": 100, "backspaceCount": 2}
    score = calculate_human_score(metrics)
    assert 0 <= score <= 1, "Score should be a valid probability"

def test_human_behavior_scores_higher_than_ai():
    """Natural human behavior (with variance, corrections, pauses) should score higher than AI-like behavior"""
    # Human-like: natural timing variance, some corrections, natural pauses
    human_metrics = {
        "pasteRatio": 0.0,  # No pasting
        "stdDwellTimeMicros": 15000,  # Natural variance in typing speed
        "totalKeystrokes": 100,
        "backspaceCount": 3  # Some natural corrections
    }
    
    # AI-like: high paste ratio, no timing variance, no corrections
    ai_metrics = {
        "pasteRatio": 0.7,  # High paste usage (less typing)
        "stdDwellTimeMicros": 1000,  # Suspiciously consistent
        "totalKeystrokes": 100,
        "backspaceCount": 0  # No corrections
    }
    
    human_score = calculate_human_score(human_metrics)
    ai_score = calculate_human_score(ai_metrics)
    
    assert human_score > ai_score, "Natural human behavior should score higher than AI behavior"

def test_determine_status_maps_probabilities_correctly():
    """Status determination should classify probabilities as yes/maybe/no"""
    # High probability → "yes"
    assert determine_status(0.95) == "yes"
    
    # Medium probability → "maybe"
    assert determine_status(0.75) == "maybe"
    
    # Low probability → "no"
    assert determine_status(0.3) == "no"


def test_calculate_transcription_likelihood_requires_min_samples():
    """Transcription likelihood should be unavailable when timing sample count is too low."""
    metrics = {
        "totalKeystrokes": 40,
        "timingSampleCount": 40,
        "backspaceCount": 0,
        "pausesOver2Sec": 0,
        "longestPauseMicros": 400000,
        "stdDwellTimeMicros": 3000,
        "stdFlightTimeMicros": 9000,
        "pasteRatio": 0.0,
    }

    score = calculate_transcription_likelihood(metrics)
    assert score is None


def test_transcription_like_metrics_score_high():
    """Steady, low-correction typing should produce a high transcription likelihood."""
    metrics = {
        "totalKeystrokes": 120,
        "timingSampleCount": 120,
        "backspaceCount": 0,
        "pausesOver2Sec": 0,
        "longestPauseMicros": 500000,
        "stdDwellTimeMicros": 2500,
        "stdFlightTimeMicros": 7000,
        "pasteRatio": 0.0,
    }

    score = calculate_transcription_likelihood(metrics)
    assert score is not None
    assert score >= 0.9


def test_composition_like_metrics_score_lower_for_transcription():
    """More variable, correction-heavy typing should score lower for transcription."""
    metrics = {
        "totalKeystrokes": 120,
        "timingSampleCount": 120,
        "backspaceCount": 12,
        "pausesOver2Sec": 8,
        "longestPauseMicros": 2500000,
        "stdDwellTimeMicros": 16000,
        "stdFlightTimeMicros": 35000,
        "pasteRatio": 0.0,
    }

    score = calculate_transcription_likelihood(metrics)
    assert score is not None
    assert score <= 0.3

def test_extract_metrics_empty_events_returns_empty_dict():
    """No keystroke events should return no metrics"""
    events = []
    metrics = extract_metrics(events)
    assert metrics == {}

def test_extract_metrics_calculates_keypress_count():
    """Keystroke metrics should count the number of keypresses"""
    events = [
        KeystrokeEvent(eventType="keydown", key="a", timestamp=datetime(2023, 1, 1, 0, 0, 0), dwellTimeMicros=100000, sequence=1),
        KeystrokeEvent(eventType="keydown", key="b", timestamp=datetime(2023, 1, 1, 0, 0, 1), dwellTimeMicros=90000, sequence=2),
    ]
    metrics = extract_metrics(events)
    assert metrics["totalKeystrokes"] == 2

def test_extract_metrics_calculates_average_dwell_time():
    """Metrics should calculate average time between key press and release"""
    events = [
        KeystrokeEvent(eventType="keydown", key="a", timestamp=datetime(2023, 1, 1, 0, 0, 0), dwellTimeMicros=100000, sequence=1),
        KeystrokeEvent(eventType="keydown", key="b", timestamp=datetime(2023, 1, 1, 0, 0, 1), dwellTimeMicros=90000, sequence=2),
    ]
    metrics = extract_metrics(events)
    # Average of 100000 and 90000
    assert metrics["avgDwellTimeMicros"] == 95000.0

def test_extract_metrics_detects_paste_events():
    """Metrics should identify when text was pasted rather than typed"""
    events = [
        KeystrokeEvent(eventType="keydown", key="a", timestamp=datetime(2023, 1, 1, 0, 0, 0), dwellTimeMicros=100000, sequence=1, pastedLength=10),
        KeystrokeEvent(eventType="keydown", key="b", timestamp=datetime(2023, 1, 1, 0, 0, 1), dwellTimeMicros=90000, sequence=2),
    ]
    metrics = extract_metrics(events)
    assert metrics["pasteRatio"] > 0, "Should detect paste events"

def test_extract_metrics_counts_corrections():
    """Metrics should count backspace corrections as indicator of human typing"""
    events = [
        KeystrokeEvent(eventType="keydown", key="a", timestamp=datetime(2023, 1, 1, 0, 0, 0), dwellTimeMicros=100000, sequence=1),
        KeystrokeEvent(eventType="keydown", key="Backspace", timestamp=datetime(2023, 1, 1, 0, 0, 1), dwellTimeMicros=90000, sequence=2),
        KeystrokeEvent(eventType="keydown", key="b", timestamp=datetime(2023, 1, 1, 0, 0, 2), dwellTimeMicros=100000, sequence=3),
    ]
    metrics = extract_metrics(events)
    assert metrics["backspaceCount"] == 1, "Should count backspace corrections"