from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models.requests import CollectRequest
from app.models.responses import CollectResponse
from app.services.features import extract_metrics
from app.services.scoring import calculate_human_score, determine_status
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
        
        # Calculate human probability
        human_prob = calculate_human_score(metrics)
        status = determine_status(human_prob)
        
        # Create or merge session (supports multiple calls to same session)
        await create_or_merge_session(conn, request, metrics, human_prob, status)
        
        # Store events in background (non-blocking)
        background.add_task(bulk_insert_events, request.session_id, request.user_id, request.events)
        
        return CollectResponse(
            session_id=request.session_id,
            human_probability=human_prob,
            verification_status=status,
            metrics=metrics
        )