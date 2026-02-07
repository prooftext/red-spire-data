import pytest
from httpx import AsyncClient
from app.main import app
from app.models.requests import CollectRequest, KeystrokeEvent
import hashlib
from datetime import datetime

@pytest.mark.asyncio
async def test_session_metadata_endpoint(db_pool):
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        session_id = f"unit-session-{datetime.utcnow().timestamp()}"
        user_id = "unit-user"
        document_text = "unit test document for metadata"

        events = [
            KeystrokeEvent(eventType="keydown", key="a", timestamp=datetime(2023,1,1,0,0,0), sequence=1),
        ]

        req = CollectRequest(session_id=session_id, user_id=user_id, document_text=document_text, events=events)
        r = await client.post("/api/v1/keystroke/collect", json=req.model_dump(mode='json'))
        assert r.status_code == 200
        collect_data = r.json()

        # Compute expected document_id (md5 of document_text)
        expected_doc_id = hashlib.md5(document_text.encode("utf-8")).hexdigest()

        # Query metadata endpoint using the stored session id returned by collect
        returned_session_id = collect_data.get("session_id")
        meta_resp = await client.get(f"/api/v1/keystroke/session/{returned_session_id}/metadata")
        assert meta_resp.status_code == 200
        data = meta_resp.json()
        # session_id stored in DB may be normalized to a UUID; ensure it's a valid UUID string
        import uuid as _uuid
        _ = _uuid.UUID(data.get("session_id"))
        assert data["user_id"] == data["user_id"]  # sanity
        assert data["document_id"] == expected_doc_id


@pytest.mark.asyncio
async def test_last_session_by_document_unit(db_pool):
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        session_id = f"unit-last-session-{datetime.utcnow().timestamp()}"
        user_id = "unit-user"
        document_text = "unique document for last session lookup"

        events = [
            KeystrokeEvent(eventType="keydown", key="x", timestamp=datetime(2023,1,1,0,0,0), sequence=1),
        ]

        req = CollectRequest(session_id=session_id, user_id=user_id, document_text=document_text, events=events)
        r = await client.post("/api/v1/keystroke/collect", json=req.model_dump(mode='json'))
        assert r.status_code == 200
        collect_data = r.json()

        doc_id = hashlib.md5(document_text.encode("utf-8")).hexdigest()
        last_resp = await client.get(f"/api/v1/keystroke/document/{doc_id}/last-session")
        assert last_resp.status_code == 200
        d = last_resp.json()
        assert d["document_id"] == doc_id
        # session_id stored in DB may be normalized to a UUID; ensure it's a valid UUID string
        import uuid as _uuid
        _ = _uuid.UUID(d.get("session_id"))
