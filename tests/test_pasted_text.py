"""
Test pasted text detection and categorization in verify endpoint.

This test verifies that when paste events include pastedText,
the verify endpoint correctly identifies which text was pasted.
"""

import pytest
from httpx import AsyncClient
from app.main import app
from app.models.requests import CollectRequest, KeystrokeEvent
from datetime import datetime


@pytest.mark.asyncio
async def test_verify_identifies_pasted_text(db_pool):
    """Verify endpoint should identify pasted text segments"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Simulate typing "Hello " then pasting "World"
        document_text = "Hello World"
        
        collect_events = [
            # Type "Hello " (6 keystrokes)
            KeystrokeEvent(
                eventType="keydown", key="H", timestamp=datetime(2023, 1, 1, 0, 0, 0),
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
            KeystrokeEvent(
                eventType="keydown", key="l", timestamp=datetime(2023, 1, 1, 0, 0, 0, 450000),
                dwellTimeMicros=100000, sequence=4
            ),
            KeystrokeEvent(
                eventType="keydown", key="o", timestamp=datetime(2023, 1, 1, 0, 0, 0, 600000),
                dwellTimeMicros=105000, sequence=5
            ),
            KeystrokeEvent(
                eventType="keydown", key=" ", timestamp=datetime(2023, 1, 1, 0, 0, 0, 750000),
                dwellTimeMicros=80000, sequence=6
            ),
            # Paste "World"
            KeystrokeEvent(
                eventType="paste", timestamp=datetime(2023, 1, 1, 0, 0, 1),
                pastedText="World", cursorPosition=6, sequence=7
            ),
        ]
        
        collect_request = CollectRequest(
            session_id="paste-test-session",
            user_id="paste-test-user",
            document_text=document_text,
            events=collect_events
        )
        
        collect_response = await client.post(
            "/api/v1/keystroke/collect",
            json=collect_request.model_dump(mode='json')
        )
        assert collect_response.status_code == 200
        
        # Now verify with the same document text
        from app.models.requests import VerifyRequest
        verify_request = VerifyRequest(document_text=document_text)
        verify_response = await client.post(
            "/api/v1/keystroke/verify",
            json=verify_request.model_dump(mode='json')
        )
        
        assert verify_response.status_code == 200
        data = verify_response.json()
        
        # Should have text categorization
        assert data["text_categorization"] is not None
        assert len(data["text_categorization"]) > 0
        
        # Find pasted segment
        pasted_segments = [s for s in data["text_categorization"] if s.get("source") == "pasted"]
        assert len(pasted_segments) > 0, "Should have at least one pasted segment"
        
        # Verify pasted segment contains "World"
        pasted_text = "".join(s["text"] for s in pasted_segments)
        assert "World" in pasted_text, f"Pasted text should contain 'World', got: {pasted_text}"
        
        # Verify keystroke segment contains "Hello "
        keystroke_segments = [s for s in data["text_categorization"] if s.get("source") == "keystroke"]
        assert len(keystroke_segments) > 0, "Should have keystroke segments"
        keystroke_text = "".join(s["text"] for s in keystroke_segments)
        assert "Hello " in keystroke_text, f"Keystroke text should contain 'Hello ', got: {keystroke_text}"


@pytest.mark.asyncio
async def test_verify_no_pasted_text_all_keystrokes(db_pool):
    """Verify endpoint should mark everything as keystroke when no paste events"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        document_text = "All typed"
        
        collect_events = [
            KeystrokeEvent(
                eventType="keydown", key="A", timestamp=datetime(2023, 1, 1, 0, 0, 0),
                dwellTimeMicros=100000, sequence=1
            ),
            KeystrokeEvent(
                eventType="keydown", key="l", timestamp=datetime(2023, 1, 1, 0, 0, 0, 150000),
                dwellTimeMicros=95000, sequence=2
            ),
            KeystrokeEvent(
                eventType="keydown", key="l", timestamp=datetime(2023, 1, 1, 0, 0, 0, 300000),
                dwellTimeMicros=110000, sequence=3
            ),
            KeystrokeEvent(
                eventType="keydown", key=" ", timestamp=datetime(2023, 1, 1, 0, 0, 0, 450000),
                dwellTimeMicros=100000, sequence=4
            ),
            KeystrokeEvent(
                eventType="keydown", key="t", timestamp=datetime(2023, 1, 1, 0, 0, 0, 600000),
                dwellTimeMicros=105000, sequence=5
            ),
            KeystrokeEvent(
                eventType="keydown", key="y", timestamp=datetime(2023, 1, 1, 0, 0, 0, 750000),
                dwellTimeMicros=80000, sequence=6
            ),
            KeystrokeEvent(
                eventType="keydown", key="p", timestamp=datetime(2023, 1, 1, 0, 0, 0, 900000),
                dwellTimeMicros=95000, sequence=7
            ),
            KeystrokeEvent(
                eventType="keydown", key="e", timestamp=datetime(2023, 1, 1, 0, 0, 1, 50000),
                dwellTimeMicros=100000, sequence=8
            ),
            KeystrokeEvent(
                eventType="keydown", key="d", timestamp=datetime(2023, 1, 1, 0, 0, 1, 200000),
                dwellTimeMicros=105000, sequence=9
            ),
        ]
        
        collect_request = CollectRequest(
            session_id="no-paste-test-session",
            user_id="no-paste-test-user",
            document_text=document_text,
            events=collect_events
        )
        
        collect_response = await client.post(
            "/api/v1/keystroke/collect",
            json=collect_request.model_dump(mode='json')
        )
        assert collect_response.status_code == 200
        
        # Verify
        from app.models.requests import VerifyRequest
        verify_request = VerifyRequest(document_text=document_text)
        verify_response = await client.post(
            "/api/v1/keystroke/verify",
            json=verify_request.model_dump(mode='json')
        )
        
        assert verify_response.status_code == 200
        data = verify_response.json()
        
        # All should be keystroke source
        assert data["text_categorization"] is not None
        for segment in data["text_categorization"]:
            assert segment.get("source") == "keystroke" or segment.get("category") == "VERIFIED_HUMAN"
