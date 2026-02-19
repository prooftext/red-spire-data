"""Test documentation endpoints"""

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_get_supported_event_types(db_pool):
    """Test that the event-types endpoint returns all supported event types"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/api/v1/keystroke/event-types")
        
        assert response.status_code == 200
        event_types = response.json()
        
        # Should be a list
        assert isinstance(event_types, list)
        assert len(event_types) > 0
        
        # Each event type should have required fields
        for event_type in event_types:
            assert "name" in event_type
            assert "description" in event_type
            assert "fields" in event_type
            assert "example" in event_type
        
        # Check for key event types
        event_type_names = [e["name"] for e in event_types]
        assert "keydown" in event_type_names
        assert "paste" in event_type_names
        assert "navigation" in event_type_names


@pytest.mark.asyncio
async def test_get_api_schema(db_pool):
    """Test that the api-schema endpoint returns API documentation"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/api/v1/keystroke/api-schema")
        
        assert response.status_code == 200
        schema = response.json()
        
        # Should have required fields
        assert "version" in schema
        assert "title" in schema
        assert "endpoints" in schema
        
        # Should document key endpoints
        endpoints = schema["endpoints"]
        assert "collect" in endpoints
        assert "verify" in endpoints
        assert "event-types" in endpoints


@pytest.mark.asyncio
async def test_paste_event_documentation_includes_pasted_text(db_pool):
    """Test that paste event documentation emphasizes pastedText field"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/api/v1/keystroke/event-types")
        
        event_types = response.json()
        paste_event = next((e for e in event_types if e["name"] == "paste"), None)
        
        assert paste_event is not None, "Paste event type should be documented"
        
        # Should have pastedText field
        assert "pastedText" in paste_event["fields"]
        
        # Example should show pastedText
        assert "pastedText" in paste_event["example"]
        assert paste_event["example"]["pastedText"] is not None

@pytest.mark.asyncio
async def test_navigation_event_documentation(db_pool):
    """Test that navigation event type documentation includes proper examples"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/api/v1/keystroke/event-types")
        
        event_types = response.json()
        nav_event = next((e for e in event_types if e["name"] == "navigation"), None)
        
        assert nav_event is not None, "Navigation event type should be documented"
        assert "Page Up, Page Down, or arrow keys" in nav_event["description"]
        
        # Should document navigation key types
        assert "key" in nav_event["fields"]
        assert "ArrowLeft" in nav_event["fields"]["key"] or "arrow" in nav_event["description"].lower()
        
        # Example should show valid navigation parameters
        example = nav_event["example"]
        assert example["eventType"] == "navigation"
        assert example["key"] in ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown"]
        assert "keyCode" in example
        assert "cursorPosition" in example

