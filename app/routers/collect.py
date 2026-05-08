from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models.requests import CollectRequest
from app.models.responses import CollectResponse
from app.services.features import extract_metrics
from app.services.scoring import calculate_human_score, calculate_transcription_likelihood, determine_status
from app.services.typing_signature import build_feature_values, compute_signature_similarity, update_profile
from app.repositories.typing_profiles import get_typing_profile, upsert_typing_profile
from app.repositories.sessions import create_or_merge_session
from app.repositories.events import bulk_insert_events
from app.repositories.session_scores import insert_session_score
from app.repositories.user_templates import (
    fetch_user_template_centroid,
    get_user_enrollment_count,
    insert_user_template,
)
from app.ml_inference import (
    compute_session_embedding,
    get_model_version,
    is_available as ml_available,
    score_session,
)
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

        # ML scoring with production model package when available.
        enrolled_template = await fetch_user_template_centroid(conn, request.user_id, model_version=get_model_version())
        ml_result = score_session(
            events=request.events,
            document_text=request.document_text,
            user_id=request.user_id,
            enrolled_template=enrolled_template,
        ) if ml_available() else None

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
        if ml_result:
            metrics["mlMode"] = ml_result.get("mode")
            metrics["mlModeConfidence"] = ml_result.get("mode_confidence")
            metrics["mlModeProbs"] = ml_result.get("mode_probs")
            metrics["mlUserMatch"] = ml_result.get("user_match")
            metrics["mlSignals"] = ml_result.get("signals")
            metrics["mlSegments"] = ml_result.get("segments")
        
        # Create or merge session (supports multiple calls to same session)
        await create_or_merge_session(conn, request, metrics, human_prob, status)
        
        # Store events in background (non-blocking)
        background.add_task(bulk_insert_events, request.session_id, request.user_id, request.events)

        # Update typing profile after scoring
        profile_data = profile.get("profile_data") if profile else None
        updated_profile, sample_count, confidence_score = update_profile(profile_data, feature_values)
        await upsert_typing_profile(conn, request.user_id, updated_profile, sample_count, confidence_score)

        # Persist ML session score and optionally enroll trusted template embeddings.
        if ml_result and ml_available():
            await insert_session_score(
                conn,
                request.session_id,
                request.user_id,
                ml_result,
                model_version=get_model_version(),
            )

            enrollment_count = await get_user_enrollment_count(conn, request.user_id, model_version=get_model_version())
            trusted_mode = (
                ml_result.get("mode") == "original"
                and float(ml_result.get("mode_confidence", 0.0)) >= 0.85
                and human_prob >= 0.9
            )
            enough_signal = timing_samples >= 50
            if trusted_mode and enough_signal and enrollment_count >= 1:
                emb = compute_session_embedding(request.events, request.document_text, user_id=request.user_id)
                if emb:
                    await insert_user_template(
                        conn,
                        user_id=request.user_id,
                        embedding_vector=emb,
                        source_session_id=request.session_id,
                        trusted=True,
                        model_version=get_model_version(),
                    )
            elif trusted_mode and enough_signal and enrollment_count == 0:
                # Bootstrap with a first untrusted embedding to avoid overconfident first-session matching.
                emb = compute_session_embedding(request.events, request.document_text, user_id=request.user_id)
                if emb:
                    await insert_user_template(
                        conn,
                        user_id=request.user_id,
                        embedding_vector=emb,
                        source_session_id=request.session_id,
                        trusted=False,
                        model_version=get_model_version(),
                    )
        
        return CollectResponse(
            session_id=request.session_id,
            human_probability=human_prob,
            verification_status=status,
            metrics=metrics
        )