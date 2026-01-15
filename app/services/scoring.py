def calculate_human_score(metrics: dict) -> float:
    """
    Returns probability (0.0 - 1.0) that session was human-typed.
    
    Key indicators:
    - High paste ratio → lower score
    - Low timing variance → lower score (AI is too consistent)
    - No backspaces → lower score
    - Very high WPM with low errors → lower score
    """
    score = 1.0
    
    # Paste behavior
    if metrics.get("pasteRatio", 0) > 0.5:
        score -= 0.4
    elif metrics.get("pasteRatio", 0) > 0.2:
        score -= 0.2
    
    # Timing variance (humans have natural variability)
    std_dwell = metrics.get("stdDwellTimeMicros", 0)
    if std_dwell < 5000:  # Too consistent
        score -= 0.3
    
    # Error correction (humans make mistakes)
    total = metrics.get("totalKeystrokes", 1)
    backspaces = metrics.get("backspaceCount", 0)
    error_rate = backspaces / total if total > 0 else 0
    if error_rate < 0.01:  # Suspiciously few corrections
        score -= 0.2
    
    return max(0.0, min(1.0, score))


def determine_status(probability: float) -> str:
    """Map probability to verification status."""
    if probability > 0.9:
        return "yes"
    elif probability > 0.5:
        return "maybe"
    return "no"