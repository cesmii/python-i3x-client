"""Shared fixtures and sample data for tests."""

import pytest
import respx

SAMPLE_NAMESPACES = [
    {"uri": "http://example.com/ns1", "displayName": "Namespace One"},
    {"uri": "http://example.com/ns2", "displayName": "Namespace Two"},
]

SAMPLE_OBJECT_TYPES = [
    {
        "elementId": "type-1",
        "displayName": "Temperature Sensor",
        "namespaceUri": "http://example.com/ns1",
        "schema": {"type": "object", "properties": {"temperature": {"type": "number"}}},
    },
]

SAMPLE_RELATIONSHIP_TYPES = [
    {
        "elementId": "rel-1",
        "displayName": "Has Component",
        "namespaceUri": "http://example.com/ns1",
        "reverseOf": "Is Component Of",
    },
]

SAMPLE_OBJECTS = [
    {
        "elementId": "obj-1",
        "displayName": "Sensor A",
        "typeId": "type-1",
        "namespaceUri": "http://example.com/ns1",
        "parentId": None,
        "isComposition": False,
    },
    {
        "elementId": "obj-2",
        "displayName": "Sensor B",
        "typeId": "type-1",
        "namespaceUri": "http://example.com/ns1",
        "parentId": None,
        "isComposition": False,
    },
]

SAMPLE_VALUE_RESPONSE = {
    "obj-1": {
        "data": [
            {"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"}
        ]
    }
}

SAMPLE_HISTORY_RESPONSE = {
    "obj-1": {
        "data": [
            {"value": 70.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"},
            {"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T01:00:00Z"},
        ]
    }
}


@pytest.fixture()
def mock_api():
    """Provide a respx mock router pre-configured with common endpoints."""
    with respx.mock(base_url="http://test-server:8080") as router:
        # Connectivity check for connect()
        router.get("/namespaces").respond(json=SAMPLE_NAMESPACES)
        yield router
