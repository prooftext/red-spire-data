from fastapi import APIRouter, HTTPException
from app.models.requests import VerifyRequest
from app.models.responses import VerifyResponse
from app.services.search import search_document
from app.services.text_categorizer import create_text_segments
from app.services.text_detectors import run_detectors
from app.repositories.detector_comparisons import insert_detector_comparisons
import json
from app.database import get_pool

router = APIRouter()

@router.post("/verify", response_model=VerifyResponse)
async def verify_text(request: VerifyRequest):
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection not initialized")
    async with pool.connection() as conn:
        result = await search_document(conn, request.document_text)
        
        if not result:
            return VerifyResponse(
                can_prove_human="no",
                confidence=0.0,
                session_id=None,
                username=None,
                document_text=None,
                text_categorization=None
            )
        
        prob = result.get("human_probability", 0.0)
        if prob > 0.9:
            verdict = "yes"
        elif prob > 0.5:
            verdict = "maybe"
        else:
            verdict = "no"
        
        # Categorize text based on keystroke data
        document_text = result.get("document_text", "")
        document_id = result.get("document_id")
        keystroke_events = result.get("keystroke_events", [])
        session_metrics = result.get("session_metrics") or {}
        if isinstance(session_metrics, str):
            try:
                session_metrics = json.loads(session_metrics)
            except json.JSONDecodeError:
                session_metrics = {}

        transcription_likelihood = session_metrics.get("transcriptionLikelihood")
        timing_samples = session_metrics.get("timingSampleCount")
        signature_confidence = session_metrics.get("signatureConfidence")

        model_ready = False
        if timing_samples is not None and signature_confidence is not None:
            model_ready = timing_samples >= 50 and signature_confidence >= 0.5
        
        text_categorization = None
        if keystroke_events:
            # Use segment-based categorization derived from per-fragment keystroke data
            text_categorization = create_text_segments(document_text, keystroke_events)

        detector_results = run_detectors(document_text)
        if detector_results:
            await insert_detector_comparisons(
                conn,
                result["session_id"],
                document_id,
                detector_results,
                len(document_text),
            )
        
        return VerifyResponse(
            can_prove_human=verdict,
            confidence=prob,
            session_id=str(result["session_id"]),
            username=result.get("username"),
            document_text=document_text,
            text_categorization=text_categorization,
            transcription_likelihood=transcription_likelihood,
            model_ready=model_ready,
            detector_results=detector_results
        )