from math import sqrt
from typing import Dict, Optional

FEATURE_KEYS = [
    "avgDwellTimeMicros",
    "stdDwellTimeMicros",
    "avgFlightTimeMicros",
    "stdFlightTimeMicros",
    "wpm",
    "backspaceRate",
    "pauseRate",
    "longestPauseMicros",
]


def build_feature_values(metrics: dict) -> Dict[str, float]:
    total = max(1, metrics.get("totalKeystrokes", 0))
    backspaces = metrics.get("backspaceCount", 0)
    pauses = metrics.get("pausesOver2Sec", 0)

    return {
        "avgDwellTimeMicros": float(metrics.get("avgDwellTimeMicros", 0.0)),
        "stdDwellTimeMicros": float(metrics.get("stdDwellTimeMicros", 0.0)),
        "avgFlightTimeMicros": float(metrics.get("avgFlightTimeMicros", 0.0)),
        "stdFlightTimeMicros": float(metrics.get("stdFlightTimeMicros", 0.0)),
        "wpm": float(metrics.get("wpm", 0.0)),
        "backspaceRate": float(backspaces) / float(total),
        "pauseRate": float(pauses) / float(total),
        "longestPauseMicros": float(metrics.get("longestPauseMicros", 0.0)),
    }


def initialize_profile(feature_values: Dict[str, float]) -> dict:
    features = {}
    for key, value in feature_values.items():
        features[key] = {
            "mean": float(value),
            "m2": 0.0,
            "count": 1,
        }
    return {
        "version": 1,
        "features": features,
    }


def update_profile(profile_data: Optional[dict], feature_values: Dict[str, float]) -> tuple[dict, int, float]:
    if not profile_data:
        profile_data = initialize_profile(feature_values)

    features = profile_data.get("features", {})
    for key, value in feature_values.items():
        if key not in features:
            features[key] = {"mean": float(value), "m2": 0.0, "count": 1}
            continue

        entry = features[key]
        count = entry.get("count", 0) + 1
        delta = value - entry.get("mean", 0.0)
        mean = entry.get("mean", 0.0) + (delta / count)
        delta2 = value - mean
        m2 = entry.get("m2", 0.0) + (delta * delta2)

        entry.update({"mean": float(mean), "m2": float(m2), "count": int(count)})
        features[key] = entry

    profile_data["features"] = features

    sample_count = min(features[key].get("count", 0) for key in features) if features else 0
    confidence_score = min(1.0, sample_count / 2.0) if sample_count else 0.0

    return profile_data, sample_count, confidence_score


def compute_signature_similarity(profile_data: Optional[dict], feature_values: Dict[str, float]) -> Optional[float]:
    if not profile_data:
        return None

    features = profile_data.get("features", {})
    if not features:
        return None

    distances = []
    for key, value in feature_values.items():
        entry = features.get(key)
        if not entry:
            continue

        count = entry.get("count", 0)
        if count < 2:
            continue

        variance = entry.get("m2", 0.0) / (count - 1) if count > 1 else 0.0
        std = sqrt(variance) if variance > 0 else 0.0
        if std <= 0:
            continue

        z_score = abs(value - entry.get("mean", 0.0)) / (std + 1.0)
        distances.append(min(z_score, 3.0))

    if not distances:
        return None

    avg_distance = sum(distances) / len(distances)
    similarity = max(0.0, 1.0 - (avg_distance / 3.0))
    return similarity
