from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models.requests import CollectRequest
from app.models.responses import CollectResponse
from app.services.features import extract_metrics
from app.services.scoring import calculate_human_score, calculate_transcription_likelihood, determine_status
from app.services.typing_signature import build_feature_values, compute_signature_similarity, update_profile
from app.repositories.typing_profiles import get_typing_profile, upsert_typing_profile
from app.repositories.sessions import create_or_merge_session
from app.repositories.events import bulk_insert_events
from app.database import get_pool

router = APIRouter()

@router.post("/collect", response_model=CollectResponse)
async def collect_keystroke(request: CollectRequest, background: BackgroundTasks):
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection not initialized")
    async with pool.connection() as conn:
        # Extract metrics
        metrics = extract_metrics(request.events)
        
        # Typing signature comparison (per-user profile)
        feature_values = build_feature_values(metrics)
        profile = await get_typing_profile(conn, request.user_id)
        timing_samples = metrics.get("timingSampleCount", 0)
        signature_match = None
        if timing_samples >= 50:
            signature_match = compute_signature_similarity(
                profile.get("profile_data") if profile else None,
                feature_values,
            )
        signature_confidence = profile.get("confidence_score") if profile else None

        # Calculate human probability
        human_prob = calculate_human_score(
            metrics,
            signature_match=signature_match,
            signature_confidence=signature_confidence,
        )
        status = determine_status(human_prob)

        transcription_likelihood = calculate_transcription_likelihood(metrics)
        if transcription_likelihood is not None:
            metrics["transcriptionLikelihood"] = transcription_likelihood
        if signature_match is not None:
            metrics["signatureMatch"] = signature_match
        if signature_confidence is not None:
            metrics["signatureConfidence"] = signature_confidence
        
        # Create or merge session (supports multiple calls to same session)
        await create_or_merge_session(conn, request, metrics, human_prob, status)
        
        # Store events in background (non-blocking)
        background.add_task(bulk_insert_events, request.session_id, request.user_id, request.events)

        # Update typing profile after scoring
        profile_data = profile.get("profile_data") if profile else None
        updated_profile, sample_count, confidence_score = update_profile(profile_data, feature_values)
        await upsert_typing_profile(conn, request.user_id, updated_profile, sample_count, confidence_score)
        
        return CollectResponse(
            session_id=request.session_id,
            human_probability=human_prob,
            verification_status=status,
            metrics=metrics
        )