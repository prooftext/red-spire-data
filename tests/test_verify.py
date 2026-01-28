import pytest
from httpx import AsyncClient
from app.main import app
from app.models.requests import VerifyRequest, CollectRequest, KeystrokeEvent
from datetime import datetime

@pytest.mark.asyncio
async def test_verify_with_no_matching_session(db_pool):
    """Verification should fail when no matching document has been collected"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Try to verify a document that was never collected
        request_data = VerifyRequest(document_text="This text was never typed before")
        
        response = await client.post("/api/v1/keystroke/verify", json=request_data.model_dump(mode='json'))
        
        assert response.status_code == 200
        data = response.json()
        
        # Should not match any session
        assert data["can_prove_human"] == "no"
        assert data["confidence"] == 0.0
        assert data["matched_session_id"] is None

@pytest.mark.asyncio
async def test_verify_finds_previously_collected_session(db_pool):
    """Verification should find and match document text from previously collected sessions"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # First, collect a typing session
        collect_events = [
            KeystrokeEvent(
                eventType="keydown", key="T", timestamp=datetime(2023, 1, 1, 0, 0, 0),
                dwellTimeMicros=100000, sequence=1
            ),
            KeystrokeEvent(
                eventType="keydown", key="e", timestamp=datetime(2023, 1, 1, 0, 0, 0, 150000),
                dwellTimeMicros=95000, sequence=2
            ),
            KeystrokeEvent(
                eventType="keydown", key="s", timestamp=datetime(2023, 1, 1, 0, 0, 0, 300000),
                dwellTimeMicros=110000, sequence=3
            ),
        ]
        collect_request = CollectRequest(
            session_id="verify-test-session",
            user_id="verify-test-user",
            document_text="Test document for verification",
            events=collect_events
        )
        
        collect_response = await client.post(
            "/api/v1/keystroke/collect",
            json=collect_request.model_dump(mode='json')
        )
        assert collect_response.status_code == 200
        
        # Now verify with the same document text
        verify_request = VerifyRequest(document_text="Test document for verification")
        verify_response = await client.post(
            "/api/v1/keystroke/verify",
            json=verify_request.model_dump(mode='json')
        )
        
        assert verify_response.status_code == 200
        data = verify_response.json()
        
        # Should find the matching session
        assert data["matched_session_id"] is not None
        assert data["confidence"] > 0.0
        # If the session was marked as human, it should show that
        if data["can_prove_human"] != "no":
            assert data["confidence"] > 0.5

@pytest.mark.asyncio
async def test_verify_endpoint_rejects_invalid_input(db_pool):
    """Verification API should validate input data"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Invalid request - missing document_text
        response = await client.post("/api/v1/keystroke/verify", json={})
        
        assert response.status_code == 422, "Invalid data should be rejected"