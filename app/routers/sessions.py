from fastapi import APIRouter, HTTPException
from app.database import get_pool
from app.repositories.sessions import get_session_metadata, get_last_session_id_by_document
from app.models.responses import SessionMetadata, LastSessionResponse

router = APIRouter()

@router.get("/session/{session_id}/metadata", response_model=SessionMetadata)
async def session_metadata(session_id: str):
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection not initialized")
    async with pool.connection() as conn:
        metadata = await get_session_metadata(conn, session_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Session not found")
        return metadata

@router.get("/document/{document_id}/last-session", response_model=LastSessionResponse)
async def last_session(document_id: str):
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection not initialized")
    async with pool.connection() as conn:
        session_id = await get_last_session_id_by_document(conn, document_id)
        return LastSessionResponse(document_id=document_id, session_id=session_id)
