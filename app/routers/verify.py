from fastapi import APIRouter, HTTPException
from app.models.requests import VerifyRequest
from app.models.responses import VerifyResponse
from app.services.search import search_document
from app.services.text_categorizer import (
    reconstruct_text_from_keystrokes,
    identify_keystroke_spans,
    categorize_text_spans
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
            # Reconstruct text from keystrokes
            keystroke_text = reconstruct_text_from_keystrokes(keystroke_events)
            
            # Identify which spans have keystrokes
            keystroke_spans = identify_keystroke_spans(document_text, keystroke_text)
            
            # Count paste events
            paste_count = sum(1 for e in keystroke_events if e.get("event_type") == "paste")
            
            # Categorize text spans
            text_categorization = categorize_text_spans(
                document_text,
                keystroke_spans,
                paste_count
            )
        
        return VerifyResponse(
            can_prove_human=verdict,
            confidence=prob,
            session_id=str(result["session_id"]),
            document_text=document_text,
            text_categorization=text_categorization
        )