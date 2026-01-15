import pytest
from app.services.scoring import calculate_human_score

def test_calculate_human_score():
    metrics = {"pasteRatio": 0.1, "stdDwellTimeMicros": 10000, "totalKeystrokes": 100, "backspaceCount": 2}
    score = calculate_human_score(metrics)
    assert 0 <= score <= 1