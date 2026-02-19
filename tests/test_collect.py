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
    """Root endpoint should serve landing page or redirect to API documentation"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/", follow_redirects=False)
        
        # Should either serve the landing page (200) or redirect to docs (307)
        assert response.status_code in [200, 307]
        if response.status_code == 307:
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

@pytest.mark.asyncio
async def test_collect_merges_multiple_submissions_to_same_session(db_pool):
    """Client can submit keystroke data in multiple calls to the same session, and data gets merged"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        session_id = "merge-test-session"
        user_id = "merge-test-user"
        
        # First submission: type "hel"
        events_1 = [
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
        request_1 = CollectRequest(
            session_id=session_id,
            user_id=user_id,
            document_text="hel",
            events=events_1
        )
        
        response_1 = await client.post("/api/v1/keystroke/collect", json=request_1.model_dump(mode='json'))
        assert response_1.status_code == 200
        data_1 = response_1.json()
        
        # Second submission: complete with "lo"
        events_2 = [
            KeystrokeEvent(
                eventType="keydown", key="l", timestamp=datetime(2023, 1, 1, 0, 0, 0, 450000),
                dwellTimeMicros=105000, sequence=4
            ),
            KeystrokeEvent(
                eventType="keydown", key="o", timestamp=datetime(2023, 1, 1, 0, 0, 0, 600000),
                dwellTimeMicros=120000, sequence=5
            ),
        ]
        request_2 = CollectRequest(
            session_id=session_id,
            user_id=user_id,
            document_text="hello",
            events=events_2
        )
        
        response_2 = await client.post("/api/v1/keystroke/collect", json=request_2.model_dump(mode='json'))
        assert response_2.status_code == 200
        data_2 = response_2.json()
        
        # Both responses should reference the same session
        assert data_1["session_id"] == session_id
        assert data_2["session_id"] == session_id
        
        # The second response should show updated metrics based on all events
        assert "human_probability" in data_2
        assert 0 <= data_2["human_probability"] <= 1

@pytest.mark.asyncio
async def test_collect_with_navigation_events(db_pool):
    """Sessions with navigation events (arrow keys, PageUp/Down) should be accepted"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Simulate typing with navigation (selecting/editing)
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
                eventType="navigation", key="ArrowLeft", keyCode=37, timestamp=datetime(2023, 1, 1, 0, 0, 0, 300000),
                cursorPosition=1, sequence=3
            ),
            KeystrokeEvent(
                eventType="navigation", key="ArrowUp", keyCode=38, timestamp=datetime(2023, 1, 1, 0, 0, 0, 400000),
                cursorPosition=0, sequence=4
            ),
            KeystrokeEvent(
                eventType="keydown", key="l", timestamp=datetime(2023, 1, 1, 0, 0, 0, 500000),
                dwellTimeMicros=110000, sequence=5
            ),
        ]
        request_data = CollectRequest(
            session_id="navigation-test-session",
            user_id="test-user-nav",
            document_text="hel",
            events=events
        )
        
        response = await client.post("/api/v1/keystroke/collect", json=request_data.model_dump(mode='json'))
        
        assert response.status_code == 200, f"Navigation events should be accepted, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data["session_id"] == "navigation-test-session"
        assert "human_probability" in data
        assert 0 <= data["human_probability"] <= 1
        assert data["verification_status"] in ["yes", "maybe", "no"]
