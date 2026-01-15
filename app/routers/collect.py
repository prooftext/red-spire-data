from fastapi import APIRouter, BackgroundTasks
from app.models.requests import CollectRequest
from app.models.responses import CollectResponse
from app.services.features import extract_metrics
from app.services.scoring import calculate_human_score, determine_status
from app.repositories.sessions import create_session
from app.repositories.events import bulk_insert_events
from app.database import get_pool

router = APIRouter()

@router.post("/collect", response_model=CollectResponse)
async def collect_keystroke(request: CollectRequest, background: BackgroundTasks):
    pool = get_pool()
    async with pool.acquire() as conn:
        # Extract metrics
        metrics = extract_metrics(request.events)
        
        # Calculate human probability
        human_prob = calculate_human_score(metrics)
        status = determine_status(human_prob)
        
        # Store session
        await create_session(conn, request, metrics, human_prob, status)
        
        # Store events in background (non-blocking)
        background.add_task(bulk_insert_events, request.session_id, request.user_id, request.events)
        
        return CollectResponse(
            session_id=request.session_id,
            human_probability=human_prob,
            verification_status=status,
            metrics=metrics
        )