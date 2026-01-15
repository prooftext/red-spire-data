from fastapi import APIRouter
from app.models.requests import VerifyRequest
from app.models.responses import VerifyResponse
from app.services.search import search_document
from app.database import get_pool

router = APIRouter()

@router.post("/verify", response_model=VerifyResponse)
async def verify_text(request: VerifyRequest):
    pool = get_pool()
    async with pool.connection() as conn:
        result = await search_document(conn, request.document_text)
        
        if not result:
            return VerifyResponse(
                can_prove_human="no",
                confidence=0.0,
                matched_session_id=None
            )
        
        prob = result.get("human_probability", 0.0)
        if prob > 0.9:
            verdict = "yes"
        elif prob > 0.5:
            verdict = "maybe"
        else:
            verdict = "no"
        
        return VerifyResponse(
            can_prove_human=verdict,
            confidence=prob,
            matched_session_id=str(result["session_id"])
        )