"""
Integration tests for the live Red Spire server running on Render.
These tests verify that the live API and database are properly configured.

Run with: pytest tests/test_live_server.py -v
"""

import pytest
import httpx
import json
from datetime import datetime

# Live server endpoint
LIVE_API_URL = "https://red-spire-data.onrender.com"


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify the live server health endpoint responds correctly"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{LIVE_API_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_docs_endpoint():
    """Verify the API documentation endpoint is accessible"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{LIVE_API_URL}/docs")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_collect_endpoint_with_valid_keystroke_data():
    """Test collecting keystroke data on the live server"""
    async with httpx.AsyncClient() as client:
        collect_payload = {
            "session_id": "live-test-001",
            "user_id": "live-test-user",
            "document_text": "The quick brown fox jumps over the lazy dog",
            "events": [
                {
                    "eventType": "keypress",
                    "key": "T",
                    "keyCode": 84,
                    "timestamp": "2026-01-29T12:00:00Z",
                    "sequence": 1
                },
                {
                    "eventType": "keypress",
                    "key": "h",
                    "keyCode": 72,
                    "timestamp": "2026-01-29T12:00:00.05Z",
                    "sequence": 2
                },
                {
                    "eventType": "keypress",
                    "key": "e",
                    "keyCode": 69,
                    "timestamp": "2026-01-29T12:00:00.1Z",
                    "sequence": 3
                },
            ]
        }
        
        response = await client.post(
            f"{LIVE_API_URL}/api/v1/keystroke/collect",
            json=collect_payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "human_probability" in data
        assert "verification_status" in data
        assert 0 <= data["human_probability"] <= 1


@pytest.mark.asyncio
async def test_verify_endpoint_with_collected_data():
    """Test verifying a document on the live server"""
    async with httpx.AsyncClient() as client:
        # First, collect some data
        collect_payload = {
            "session_id": "live-test-002",
            "user_id": "live-test-user",
            "document_text": "The quick brown fox",
            "events": [
                {
                    "eventType": "keypress",
                    "key": "T",
                    "keyCode": 84,
                    "timestamp": "2026-01-29T12:01:00Z",
                    "sequence": 1
                },
                {
                    "eventType": "keypress",
                    "key": "h",
                    "keyCode": 72,
                    "timestamp": "2026-01-29T12:01:00.05Z",
                    "sequence": 2
                },
            ]
        }
        
        collect_response = await client.post(
            f"{LIVE_API_URL}/api/v1/keystroke/collect",
            json=collect_payload
        )
        assert collect_response.status_code == 200
        
        # Now verify with the same document
        verify_payload = {
            "document_text": "The quick brown fox"
        }
        
        verify_response = await client.post(
            f"{LIVE_API_URL}/api/v1/keystroke/verify",
            json=verify_payload
        )
        
        assert verify_response.status_code == 200, f"Expected 200, got {verify_response.status_code}: {verify_response.text}"
        data = verify_response.json()
        assert "session_id" in data
        assert "confidence" in data


@pytest.mark.asyncio
async def test_collect_endpoint_rejects_invalid_data():
    """Test that the collect endpoint validates input properly"""
    async with httpx.AsyncClient() as client:
        # Missing required fields
        invalid_payload = {
            "session_id": "test-001",
            # Missing user_id, document_text, and events
        }
        
        response = await client.post(
            f"{LIVE_API_URL}/api/v1/keystroke/collect",
            json=invalid_payload
        )
        
        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_database_connectivity():
    """Verify the live database is properly connected by collecting and querying data"""
    async with httpx.AsyncClient() as client:
        # Create a unique test document
        test_doc = f"Database connectivity test {datetime.now().isoformat()}"
        
        collect_payload = {
            "session_id": "db-connectivity-test",
            "user_id": "db-test-user",
            "document_text": test_doc,
            "events": [
                {
                    "eventType": "keypress",
                    "key": "d",
                    "keyCode": 68,
                    "timestamp": "2026-01-29T12:02:00Z",
                    "sequence": 1
                },
            ]
        }
        
        # Collect data
        collect_response = await client.post(
            f"{LIVE_API_URL}/api/v1/keystroke/collect",
            json=collect_payload
        )
        assert collect_response.status_code == 200
        
        # Verify we can query it back
        verify_payload = {
            "document_text": test_doc
        }
        
        verify_response = await client.post(
            f"{LIVE_API_URL}/api/v1/keystroke/verify",
            json=verify_payload
        )
        assert verify_response.status_code == 200
        data = verify_response.json()
        # Should find the session we just created
        assert data["session_id"] is not None


@pytest.mark.asyncio
async def test_collect_merges_multiple_submissions_to_same_session():
    """Verify that multiple collect calls to the same session merge the data"""
    async with httpx.AsyncClient() as client:
        session_id = f"merge-test-{datetime.now().isoformat()}"
        user_id = "merge-test-user"
        
        # First submission
        collect_payload_1 = {
            "session_id": session_id,
            "user_id": user_id,
            "document_text": "The quick brown",
            "events": [
                {
                    "eventType": "keypress",
                    "key": "T",
                    "keyCode": 84,
                    "timestamp": "2026-01-29T12:03:00Z",
                    "sequence": 1
                },
                {
                    "eventType": "keypress",
                    "key": "h",
                    "keyCode": 72,
                    "timestamp": "2026-01-29T12:03:00.05Z",
                    "sequence": 2
                },
            ]
        }
        
        response_1 = await client.post(
            f"{LIVE_API_URL}/api/v1/keystroke/collect",
            json=collect_payload_1
        )
        assert response_1.status_code == 200
        data_1 = response_1.json()
        assert data_1["session_id"] == session_id
        
        # Second submission to same session (complete the sentence)
        collect_payload_2 = {
            "session_id": session_id,
            "user_id": user_id,
            "document_text": "The quick brown fox",
            "events": [
                {
                    "eventType": "keypress",
                    "key": "f",
                    "keyCode": 102,
                    "timestamp": "2026-01-29T12:03:00.1Z",
                    "sequence": 3
                },
                {
                    "eventType": "keypress",
                    "key": "o",
                    "keyCode": 111,
                    "timestamp": "2026-01-29T12:03:00.15Z",
                    "sequence": 4
                },
                {
                    "eventType": "keypress",
                    "key": "x",
                    "keyCode": 120,
                    "timestamp": "2026-01-29T12:03:00.2Z",
                    "sequence": 5
                },
            ]
        }
        
        response_2 = await client.post(
            f"{LIVE_API_URL}/api/v1/keystroke/collect",
            json=collect_payload_2
        )
        assert response_2.status_code == 200
        data_2 = response_2.json()
        
        # Should use same session ID
        assert data_2["session_id"] == session_id
        
        # Metrics should be recalculated based on merged events
        assert "human_probability" in data_2
        assert 0 <= data_2["human_probability"] <= 1


@pytest.mark.asyncio
async def test_live_session_metadata_and_last_session():
    """Create a live session, then query the metadata and last-session endpoints."""
    async with httpx.AsyncClient() as client:
        doc_text = f"Live test document {datetime.now().isoformat()}"
        session_id = f"live-meta-{datetime.now().timestamp()}"
        payload = {
            "session_id": session_id,
            "user_id": "live-meta-user",
            "document_text": doc_text,
            "events": [
                {
                    "eventType": "keypress",
                    "key": "L",
                    "timestamp": datetime.now().isoformat(),
                    "sequence": 1
                }
            ]
        }

        collect_resp = await client.post(f"{LIVE_API_URL}/api/v1/keystroke/collect", json=payload)
        assert collect_resp.status_code == 200

        # compute expected document_id
        import hashlib as _hash
        doc_id = _hash.md5(doc_text.encode('utf-8')).hexdigest()

        # metadata
        meta = await client.get(f"{LIVE_API_URL}/api/v1/keystroke/session/{session_id}/metadata")
        assert meta.status_code == 200
        mdata = meta.json()
        assert mdata.get("document_id") == doc_id

        # last-session
        last = await client.get(f"{LIVE_API_URL}/api/v1/keystroke/document/{doc_id}/last-session")
        assert last.status_code == 200
        ldata = last.json()
        assert ldata.get("session_id") == session_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
