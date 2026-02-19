def calculate_human_score(
    metrics: dict,
    signature_match: float | None = None,
    signature_confidence: float | None = None,
) -> float:
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
    
    # Error correction (humans make mistakes).
    # Use WPM-aware threshold: at higher WPM we expect more corrections,
    # so a very low error rate is more suspicious when typing speed is high.
    total = metrics.get("totalKeystrokes", 1)
    backspaces = metrics.get("backspaceCount", 0)
    error_rate = backspaces / total if total > 0 else 0

    wpm = metrics.get("wpm", 0)
    # Base threshold for suspiciously few corrections
    base_thresh = 0.01
    if wpm > 40:
        # Scale threshold linearly from 0.01 at 40 WPM to ~0.03 at 100 WPM
        threshold = base_thresh * (1 + (wpm - 40) / 60)
    else:
        threshold = base_thresh
    # Cap threshold to a reasonable maximum
    threshold = min(threshold, 0.05)

    if error_rate < threshold:
        # Penalize proportionally to how far below threshold the error rate is,
        # up to a maximum penalty of 0.2
        reduction = 0.2 * (1 - (error_rate / threshold)) if threshold > 0 else 0.2
        score -= min(0.2, reduction)
    
    if signature_match is not None:
        confidence_factor = 1.0
        if signature_confidence is not None:
            confidence_factor = max(0.0, min(1.0, signature_confidence))

        if signature_match < 0.4:
            score -= 0.2 * confidence_factor
        elif signature_match > 0.8:
            score += 0.05 * confidence_factor

    return max(0.0, min(1.0, score))


def calculate_transcription_likelihood(metrics: dict, min_keystrokes: int = 50) -> float | None:
    """
    Returns probability (0.0 - 1.0) that text was typed via transcription.

    Heuristics inspired by findings in typing-process research: transcription
    tends to show steadier timing, fewer long pauses, and fewer corrections.
    """
    total = max(1, metrics.get("totalKeystrokes", 0))
    timing_samples = metrics.get("timingSampleCount", total)
    if timing_samples < min_keystrokes:
        return None
    backspaces = metrics.get("backspaceCount", 0)
    pauses_over_2s = metrics.get("pausesOver2Sec", 0)
    longest_pause = metrics.get("longestPauseMicros", 0)

    backspace_rate = backspaces / total
    pause_rate = pauses_over_2s / total

    std_dwell = metrics.get("stdDwellTimeMicros", 0)
    std_flight = metrics.get("stdFlightTimeMicros", 0)
    paste_ratio = metrics.get("pasteRatio", 0)

    score = 0.0

    if paste_ratio <= 0.05:
        score += 0.2

    if backspace_rate <= 0.01:
        score += 0.25

    if pause_rate <= 0.01:
        score += 0.2

    if std_dwell < 8000 and std_flight < 20000:
        score += 0.2

    if longest_pause and longest_pause < 2_000_000:
        score += 0.15

    return max(0.0, min(1.0, score))


def determine_status(probability: float) -> str:
    """Map probability to verification status."""
    if probability > 0.9:
        return "yes"
    elif probability > 0.5:
        return "maybe"
    return "no"