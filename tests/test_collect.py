import pytest
from httpx import AsyncClient
from app.main import app
from app.models.requests import CollectRequest, KeystrokeEvent
from datetime import datetime

@pytest.mark.asyncio
async def test_health_endpoint(db_pool):
    """API should report healthy status"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

@pytest.mark.asyncio
async def test_root_endpoint_redirects_to_docs(db_pool):
    """Root endpoint should redirect to API documentation"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/", follow_redirects=False)
        
        assert response.status_code == 307
        assert response.headers.get("location") == "/docs"

@pytest.mark.asyncio
async def test_collect_keystroke_session(db_pool):
    """Collecting keystroke data should store session and return analysis"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Simulate typing "hello" with natural timing variance
        events = [
            KeystrokeEvent(
                eventType="keydown", key="h", timestamp=datetime(2023, 1, 1, 0, 0, 0),
                dwellTimeMicros=100000, sequence=1
            ),
            KeystrokeEvent(
                eventType="keydown", key="e", timestamp=datetime(2023, 1, 1, 0, 0, 0, 150000),
                dwellTimeMicros=95000, sequence=2
            ),
            KeystrokeEvent(
                eventType="keydown", key="l", timestamp=datetime(2023, 1, 1, 0, 0, 0, 300000),
                dwellTimeMicros=110000, sequence=3
            ),
        ]
        request_data = CollectRequest(
            session_id="test-session-123",
            user_id="test-user-456",
            document_text="hello",
            events=events
        )
        
        response = await client.post("/api/v1/keystroke/collect", json=request_data.model_dump(mode='json'))
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return analysis results
        assert data["session_id"] == "test-session-123"
        assert "human_probability" in data
        assert 0 <= data["human_probability"] <= 1
        assert data["verification_status"] in ["yes", "maybe", "no"]
        assert "metrics" in data

@pytest.mark.asyncio
async def test_collect_with_paste_behavior(db_pool):
    """Sessions with paste behavior should be flagged with lower human probability"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Simulate pasting a large block of text
        events = [
            KeystrokeEvent(
                eventType="keydown", key="v", timestamp=datetime(2023, 1, 1, 0, 0, 0),
                dwellTimeMicros=50000, sequence=1, pastedLength=100
            ),
        ]
        request_data = CollectRequest(
            session_id="paste-session",
            user_id="test-user-456",
            document_text="pasted text",
            events=events
        )
        
        response = await client.post("/api/v1/keystroke/collect", json=request_data.model_dump(mode='json'))
        
        assert response.status_code == 200
        data = response.json()
        
        # Paste behavior should result in lower human probability
        assert data["verification_status"] == "no", "Paste behavior should not verify as human"

@pytest.mark.asyncio
async def test_collect_endpoint_validates_input(db_pool):
    """API should reject invalid keystroke session data"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Missing required fields
        response = await client.post("/api/v1/keystroke/collect", json={})
        
        assert response.status_code == 422, "Invalid data should be rejected"