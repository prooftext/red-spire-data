import pytest
from httpx import AsyncClient
from app.main import app
from app.models.requests import VerifyRequest, CollectRequest, KeystrokeEvent
from datetime import datetime, timedelta

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
        assert data["session_id"] is None

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
        assert data["session_id"] is not None
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


@pytest.mark.asyncio
async def test_verify_returns_transcription_likelihood_and_transcribed_segments(db_pool):
    """Verification should surface transcription likelihood and transcribed segment category when detected."""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        document_text = (
            "this sentence is intentionally long to simulate dictated speech typing behavior "
            "without natural corrections or long pauses"
        )

        start_time = datetime(2023, 1, 1, 0, 0, 0)
        collect_events = [
            KeystrokeEvent(
                eventType="keydown",
                key=char,
                timestamp=start_time + timedelta(microseconds=120000 * idx),
                dwellTimeMicros=70000,
                sequence=idx + 1,
            )
            for idx, char in enumerate(document_text)
        ]

        collect_request = CollectRequest(
            session_id="verify-transcription-session",
            user_id="verify-transcription-user",
            document_text=document_text,
            events=collect_events,
        )

        collect_response = await client.post(
            "/api/v1/keystroke/collect",
            json=collect_request.model_dump(mode='json')
        )
        assert collect_response.status_code == 200

        verify_request = VerifyRequest(document_text=document_text)
        verify_response = await client.post(
            "/api/v1/keystroke/verify",
            json=verify_request.model_dump(mode='json')
        )

        assert verify_response.status_code == 200
        data = verify_response.json()

        assert isinstance(data.get("transcription_likelihood"), float)
        assert data["transcription_likelihood"] >= 0.7

        text_categorization = data.get("text_categorization") or []
        assert any(
            (segment.get("category") or "").upper() == "LIKELY_TRANSCRIBED"
            for segment in text_categorization
        )


@pytest.mark.asyncio
async def test_verify_returns_only_searched_text_not_full_document(db_pool):
    """Verify response should return and categorize only the searched text snippet."""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        full_text = "Alpha beta gamma"
        query_text = "beta"

        start_time = datetime(2023, 1, 2, 0, 0, 0)
        collect_events = [
            KeystrokeEvent(
                eventType="keydown",
                key=char,
                timestamp=start_time + timedelta(microseconds=100000 * idx),
                dwellTimeMicros=80000,
                sequence=idx + 1,
            )
            for idx, char in enumerate(full_text)
        ]

        collect_request = CollectRequest(
            session_id="verify-query-snippet-session",
            user_id="verify-query-snippet-user",
            document_text=full_text,
            events=collect_events,
        )

        collect_response = await client.post(
            "/api/v1/keystroke/collect",
            json=collect_request.model_dump(mode="json"),
        )
        assert collect_response.status_code == 200

        verify_response = await client.post(
            "/api/v1/keystroke/verify",
            json=VerifyRequest(document_text=query_text).model_dump(mode="json"),
        )

        assert verify_response.status_code == 200
        data = verify_response.json()
        assert data.get("document_text") == query_text
        assert data.get("document_text") != full_text

        segments = data.get("text_categorization") or []
        rebuilt = "".join(segment.get("text") or "" for segment in segments)
        assert rebuilt == query_text


@pytest.mark.asyncio
async def test_verify_no_match_marks_query_as_not_in_system(db_pool):
    """When no match exists, the entire searched text should be returned as NOT_IN_SYSTEM."""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        query_text = "this phrase does not exist in records"
        verify_response = await client.post(
            "/api/v1/keystroke/verify",
            json=VerifyRequest(document_text=query_text).model_dump(mode="json"),
        )

        assert verify_response.status_code == 200
        data = verify_response.json()

        assert data.get("can_prove_human") == "no"
        assert data.get("document_text") == query_text

        segments = data.get("text_categorization") or []
        assert len(segments) == 1
        assert segments[0].get("text") == query_text
        assert (segments[0].get("category") or "").upper() == "NOT_IN_SYSTEM"


@pytest.mark.asyncio
async def test_verify_returns_ranked_top_hits_for_multiple_matches(db_pool):
    """Verify should return ranked top_hits when multiple documents match a query."""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        query_text = "shared phrase"

        docs = [
            "first document contains shared phrase and extra words",
            "second document also contains shared phrase for ranking",
        ]

        for idx, doc in enumerate(docs):
            events = [
                KeystrokeEvent(
                    eventType="keydown",
                    key=char,
                    timestamp=datetime(2023, 1, 3, 0, 0, 0, idx * 100000 + j * 1000),
                    dwellTimeMicros=75000,
                    sequence=j + 1,
                )
                for j, char in enumerate(doc)
            ]
            collect_request = CollectRequest(
                session_id=f"verify-top-hit-session-{idx}",
                user_id=f"verify-top-hit-user-{idx}",
                document_text=doc,
                events=events,
            )
            collect_response = await client.post(
                "/api/v1/keystroke/collect",
                json=collect_request.model_dump(mode="json"),
            )
            assert collect_response.status_code == 200

        verify_response = await client.post(
            "/api/v1/keystroke/verify",
            json={"document_text": query_text, "top_k": 5},
        )

        assert verify_response.status_code == 200
        data = verify_response.json()

        top_hits = data.get("top_hits") or []
        assert len(top_hits) >= 2
        for hit in top_hits:
            assert hit.get("document_text") == query_text
            rebuilt = "".join(seg.get("text") or "" for seg in (hit.get("text_categorization") or []))
            assert rebuilt == query_text