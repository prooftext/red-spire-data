from fastapi import APIRouter

from app.ml_inference import get_model_version, is_available as ml_available, score_session
from app.models.requests import ScoreSessionRequest
from app.models.responses import MLScoreResponse


router = APIRouter()


@router.post("/score-session", response_model=MLScoreResponse)
async def score_keystroke_session(request: ScoreSessionRequest) -> MLScoreResponse:
    result = score_session(
        events=request.events,
        document_text=request.document_text,
        user_id=request.user_id,
        enrolled_template=None,
    ) if ml_available() else {
        "mode": "mixed",
        "mode_confidence": 0.0,
        "mode_probs": {"original": 0.0, "mixed": 1.0, "transcribed": 0.0},
        "user_match": {"is_match": False, "score": 0.0, "threshold": 0.78},
        "signals": {},
        "segments": [],
    }

    segments = result.get("segments") if request.include_segments else None

    return MLScoreResponse(
        mode=str(result.get("mode", "mixed")),
        mode_confidence=float(result.get("mode_confidence", 0.0)),
        mode_probs=dict(result.get("mode_probs", {})),
        user_match=dict(result.get("user_match", {})),
        signals=dict(result.get("signals", {})),
        segments=segments,
        model_version=get_model_version(),
    )
