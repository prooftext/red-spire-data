from fastapi import APIRouter, HTTPException
from app.models.requests import VerifyRequest
from app.models.responses import VerifyResponse
from app.services.search import search_document
from app.services.text_categorizer import (
    reconstruct_text_from_keystrokes,
    identify_keystroke_spans,
    categorize_text_spans,
    create_text_segments
)
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
        keystroke_events = result.get("keystroke_events", [])
        
        text_categorization = None
        if keystroke_events:
            # Use the new segment-based categorization that handles pasted text
            text_categorization = create_text_segments(document_text, keystroke_events)
        
        return VerifyResponse(
            can_prove_human=verdict,
            confidence=prob,
            session_id=str(result["session_id"]),
            document_text=document_text,
            text_categorization=text_categorization
        )