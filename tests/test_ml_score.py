import pytest
from datetime import datetime

from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_score_session_endpoint_returns_ml_payload(db_pool):
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        payload = {
            "user_id": "ml-score-user",
            "session_id": "ml-score-session",
            "document_text": "hi",
            "include_segments": True,
            "events": [
                {
                    "eventType": "keydown",
                    "key": "h",
                    "timestamp": datetime(2023, 1, 1, 0, 0, 0).isoformat(),
                    "dwellTimeMicros": 90000,
                    "flightTimeMicros": 70000,
                    "sequence": 1,
                },
                {
                    "eventType": "keydown",
                    "key": "i",
                    "timestamp": datetime(2023, 1, 1, 0, 0, 0, 180000).isoformat(),
                    "dwellTimeMicros": 85000,
                    "flightTimeMicros": 65000,
                    "sequence": 2,
                },
            ],
        }

        response = await client.post(
            "/api/v1/keystroke/score-session",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()

        assert "mode" in data
        assert "mode_confidence" in data
        assert "mode_probs" in data
        assert "user_match" in data
        assert "signals" in data
        assert "model_version" in data
        assert isinstance(data.get("mode_probs", {}), dict)
        assert isinstance(data.get("user_match", {}), dict)


@pytest.mark.asyncio
async def test_score_session_endpoint_can_omit_segments(db_pool):
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        payload = {
            "document_text": "a",
            "include_segments": False,
            "events": [
                {
                    "eventType": "keydown",
                    "key": "a",
                    "timestamp": datetime(2023, 1, 1, 0, 0, 0).isoformat(),
                    "dwellTimeMicros": 80000,
                    "sequence": 1,
                }
            ],
        }

        response = await client.post(
            "/api/v1/keystroke/score-session",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["segments"] is None
