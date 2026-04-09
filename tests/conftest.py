"""Shared fixtures and sample data for tests."""

import pytest
import respx

# Standard i3X v1 response envelope helpers
def success(result):
    return {"success": True, "result": result}

def bulk(results):
    all_ok = all(r.get("success") for r in results)
    return {"success": all_ok, "results": results}

def bulk_item_ok(element_id, result):
    return {"success": True, "elementId": element_id, "result": result}

def bulk_item_err(element_id, code, message):
    return {"success": False, "elementId": element_id, "error": {"code": code, "message": message}}


SAMPLE_SERVER_INFO = success({
    "specVersion": "1.0",
    "serverVersion": "2.0.0",
    "serverName": "TestServer",
    "capabilities": {
        "query": {"history": True},
        "update": {"current": True, "history": False},
        "subscribe": {"stream": True},
    },
})

SAMPLE_NAMESPACES = success([
    {"uri": "http://example.com/ns1", "displayName": "Namespace One"},
    {"uri": "http://example.com/ns2", "displayName": "Namespace Two"},
])

SAMPLE_OBJECT_TYPES = success([
    {
        "elementId": "type-1",
        "displayName": "Temperature Sensor",
        "namespaceUri": "http://example.com/ns1",
        "sourceTypeId": "TemperatureSensorType",
        "version": "1.0.0",
        "schema": {"type": "object", "properties": {"temperature": {"type": "number"}}},
    },
])

SAMPLE_OBJECT_TYPES_BULK = bulk([
    bulk_item_ok("type-1", {
        "elementId": "type-1",
        "displayName": "Temperature Sensor",
        "namespaceUri": "http://example.com/ns1",
        "sourceTypeId": "TemperatureSensorType",
        "version": "1.0.0",
        "schema": {"type": "object", "properties": {"temperature": {"type": "number"}}},
    }),
])

SAMPLE_RELATIONSHIP_TYPES = success([
    {
        "elementId": "rel-1",
        "displayName": "Has Component",
        "namespaceUri": "http://example.com/ns1",
        "relationshipId": "HasComponent",
        "reverseOf": "ComponentOf",
    },
])

SAMPLE_RELATIONSHIP_TYPES_BULK = bulk([
    bulk_item_ok("rel-1", {
        "elementId": "rel-1",
        "displayName": "Has Component",
        "namespaceUri": "http://example.com/ns1",
        "relationshipId": "HasComponent",
        "reverseOf": "ComponentOf",
    }),
])

_OBJ_1 = {
    "elementId": "obj-1",
    "displayName": "Sensor A",
    "typeElementId": "type-1",
    "parentId": None,
    "isComposition": False,
    "isExtended": False,
}

_OBJ_2 = {
    "elementId": "obj-2",
    "displayName": "Sensor B",
    "typeElementId": "type-1",
    "parentId": None,
    "isComposition": False,
    "isExtended": False,
}

SAMPLE_OBJECTS = success([_OBJ_1, _OBJ_2])

SAMPLE_OBJECTS_BULK = bulk([
    bulk_item_ok("obj-1", _OBJ_1),
    bulk_item_ok("obj-2", _OBJ_2),
])

SAMPLE_OBJECT_BULK_SINGLE = bulk([bulk_item_ok("obj-1", _OBJ_1)])

SAMPLE_RELATED_BULK = bulk([
    bulk_item_ok("obj-1", [
        {"sourceRelationship": "HasChildren", "object": _OBJ_2},
    ]),
])

SAMPLE_VALUE_BULK = bulk([
    bulk_item_ok("obj-1", {
        "isComposition": False,
        "value": 72.5,
        "quality": "Good",
        "timestamp": "2026-01-01T00:00:00Z",
    }),
])

SAMPLE_HISTORY_BULK = bulk([
    bulk_item_ok("obj-1", {
        "isComposition": False,
        "values": [
            {"value": 70.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"},
            {"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T01:00:00Z"},
        ],
    }),
])

SAMPLE_SUBSCRIPTION_CREATE = success({
    "clientId": "test-client",
    "subscriptionId": "sub-1",
    "displayName": None,
})

SAMPLE_SUBSCRIPTION_DETAIL = {
    "subscriptionId": "sub-1",
    "displayName": None,
    "monitoredObjects": [{"elementId": "obj-1", "maxDepth": 1}],
}

SAMPLE_SUBSCRIPTION_LIST = bulk([
    bulk_item_ok("sub-1", SAMPLE_SUBSCRIPTION_DETAIL),
])

SAMPLE_REGISTER_BULK = bulk([
    bulk_item_ok("obj-1", None),
    bulk_item_ok("obj-2", None),
])

SAMPLE_SYNC_RESPONSE = success([
    {"sequenceNumber": 1, "elementId": "obj-1", "value": 72.5, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"},
    {"sequenceNumber": 2, "elementId": "obj-2", "value": 18.3, "quality": "Good", "timestamp": "2026-01-01T00:00:01Z"},
])

SAMPLE_DELETE_BULK = bulk([
    {"success": True, "subscriptionId": "sub-1", "result": None},
])


@pytest.fixture()
def mock_api():
    """Provide a respx mock router pre-configured with common endpoints."""
    with respx.mock(base_url="http://test-server:8080") as router:
        # Connectivity check for connect() uses GET /info
        router.get("/info").respond(json=SAMPLE_SERVER_INFO)
        yield router
