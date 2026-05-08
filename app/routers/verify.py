from fastapi import APIRouter, HTTPException
from app.models.requests import VerifyRequest
from app.models.responses import VerifyResponse
from app.services.search import search_documents
from app.services.text_categorizer import create_text_segments
from app.services.text_detectors import run_detectors
from app.ml_inference import is_available as ml_available, score_session
from app.repositories.detector_comparisons import insert_detector_comparisons
import json
from app.database import get_pool

router = APIRouter()


def _normalize_keystroke_events(raw_events: list[dict]) -> list[dict]:
    events = []
    for row in raw_events:
        event_data = row.get("event_data") or {}
        if isinstance(event_data, str):
            try:
                event_data = json.loads(event_data)
            except json.JSONDecodeError:
                event_data = {}

        if not isinstance(event_data, dict):
            event_data = {}

        event_data.setdefault("eventType", row.get("event_type"))
        event_data.setdefault("sequence", row.get("sequence_number"))
        events.append(event_data)
    return events


def _map_label_to_category(label: str) -> str:
    normalized = str(label or "").strip().lower()
    if normalized in {"handwritten", "verified_human", "human"}:
        return "VERIFIED_HUMAN"
    if normalized in {"pasted", "likely_pasted", "paste"}:
        return "LIKELY_PASTED"
    if normalized in {"transcribed", "likely_transcribed"}:
        return "LIKELY_TRANSCRIBED"
    if normalized in {"ai_generated", "ai"}:
        return "AI_GENERATED"
    return "UNKNOWN"


def _category_source(category: str) -> str:
    mapping = {
        "VERIFIED_HUMAN": "keystroke",
        "LIKELY_PASTED": "pasted",
        "LIKELY_TRANSCRIBED": "transcribed",
        "AI_GENERATED": "ai_detector",
        "UNKNOWN": "unknown",
        "NOT_IN_SYSTEM": "not_in_system",
    }
    return mapping.get(category, "unknown")


def _detector_ai_score(detector_results: list[dict]) -> float:
    best = 0.0
    for result in detector_results or []:
        if str(result.get("label", "")).upper() != "AI":
            continue
        try:
            best = max(best, float(result.get("score") or 0.0))
        except (TypeError, ValueError):
            continue
    return best


def _to_query_segments(query_text: str, char_categories: list[str]) -> list[dict]:
    if not query_text:
        return []
    if not char_categories:
        return []

    segments = []
    start = 0
    current = char_categories[0]
    for i in range(1, len(query_text)):
        if char_categories[i] != current:
            segments.append(
                {
                    "start": start,
                    "end": i,
                    "text": query_text[start:i],
                    "category": current,
                    "source": _category_source(current),
                }
            )
            start = i
            current = char_categories[i]

    segments.append(
        {
            "start": start,
            "end": len(query_text),
            "text": query_text[start:len(query_text)],
            "category": current,
            "source": _category_source(current),
        }
    )
    return segments


def _project_ml_segments_to_query(query_text: str, full_document: str, segments: list[dict]) -> list[dict]:
    if not query_text:
        return []

    query_lower = query_text.lower()
    doc_lower = (full_document or "").lower()
    match_start = doc_lower.find(query_lower)

    # The queried text should always be returned; default to NOT_IN_SYSTEM when not aligned.
    char_categories = ["NOT_IN_SYSTEM"] * len(query_text)
    if match_start == -1:
        return _to_query_segments(query_text, char_categories)

    match_end = match_start + len(query_text)
    for i in range(len(query_text)):
        char_categories[i] = "UNKNOWN"

    for seg in segments or []:
        seg_start = int(seg.get("start") or 0)
        seg_end = int(seg.get("end") or 0)
        if seg_end <= seg_start:
            continue

        overlap_start = max(seg_start, match_start)
        overlap_end = min(seg_end, match_end)
        if overlap_end <= overlap_start:
            continue

        category = _map_label_to_category(seg.get("category") or seg.get("label") or seg.get("source"))
        rel_start = overlap_start - match_start
        rel_end = overlap_end - match_start
        for idx in range(rel_start, rel_end):
            char_categories[idx] = category

    return _to_query_segments(query_text, char_categories)

@router.post("/verify", response_model=VerifyResponse)
async def verify_text(request: VerifyRequest):
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection not initialized")
    async with pool.connection() as conn:
        results = await search_documents(conn, request.document_text, limit=request.top_k)
        
        if not results:
            unknown_segments = [
                {
                    "start": 0,
                    "end": len(request.document_text),
                    "text": request.document_text,
                    "category": "NOT_IN_SYSTEM",
                    "source": "not_in_system",
                }
            ] if request.document_text else []
            return VerifyResponse(
                can_prove_human="no",
                confidence=0.0,
                session_id=None,
                username=None,
                document_text=request.document_text,
                text_categorization=unknown_segments,
                top_hits=[],
            )

        query_text = request.document_text
        detector_results = run_detectors(query_text)
        ai_score = _detector_ai_score(detector_results)

        top_hits = []
        for result in results:
            prob = result.get("human_probability", 0.0)
            if prob > 0.9:
                verdict = "yes"
            elif prob > 0.5:
                verdict = "maybe"
            else:
                verdict = "no"

            full_document_text = result.get("document_text", "")
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

            normalized_events = _normalize_keystroke_events(keystroke_events)

            ml_segments = []
            if normalized_events and ml_available():
                ml_result = score_session(
                    events=normalized_events,
                    document_text=full_document_text,
                    user_id=str(result.get("user_id") or ""),
                )
                ml_segments = ml_result.get("segments") or []

            if not ml_segments and normalized_events:
                ml_segments = create_text_segments(full_document_text, keystroke_events)

            text_categorization = _project_ml_segments_to_query(
                query_text=query_text,
                full_document=full_document_text,
                segments=ml_segments,
            )

            if ai_score >= 0.5:
                for seg in text_categorization:
                    if seg.get("category") == "UNKNOWN":
                        seg["category"] = "AI_GENERATED"
                        seg["source"] = "ai_detector"

            if detector_results:
                await insert_detector_comparisons(
                    conn,
                    result["session_id"],
                    document_id,
                    detector_results,
                    len(query_text),
                )

            top_hits.append(
                {
                    "can_prove_human": verdict,
                    "confidence": prob,
                    "session_id": str(result["session_id"]),
                    "username": result.get("username"),
                    "document_text": query_text,
                    "text_categorization": text_categorization,
                    "transcription_likelihood": transcription_likelihood,
                    "model_ready": model_ready,
                    "rank": float(result.get("rank") or 0.0),
                }
            )

        primary = top_hits[0]
        return VerifyResponse(
            can_prove_human=primary["can_prove_human"],
            confidence=primary["confidence"],
            session_id=primary["session_id"],
            username=primary.get("username"),
            document_text=query_text,
            text_categorization=primary.get("text_categorization"),
            transcription_likelihood=primary.get("transcription_likelihood"),
            model_ready=primary.get("model_ready"),
            detector_results=detector_results,
            top_hits=top_hits,
        )