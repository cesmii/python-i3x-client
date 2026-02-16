"""Tests for i3x.Client."""

import pytest
import respx

import i3x
from i3x.errors import NotFoundError

from .conftest import (
    SAMPLE_HISTORY_RESPONSE,
    SAMPLE_NAMESPACES,
    SAMPLE_OBJECT_TYPES,
    SAMPLE_OBJECTS,
    SAMPLE_RELATIONSHIP_TYPES,
    SAMPLE_VALUE_RESPONSE,
)


@pytest.fixture()
def mock_api():
    with respx.mock(base_url="http://test-server:8080") as router:
        router.get("/namespaces").respond(json=SAMPLE_NAMESPACES)
        yield router


@pytest.fixture()
def client(mock_api):
    c = i3x.Client("http://test-server:8080")
    c.connect()
    yield c
    c.disconnect()


class TestClientLifecycle:
    def test_connect_disconnect(self, mock_api):
        c = i3x.Client("http://test-server:8080")
        assert not c.is_connected
        c.connect()
        assert c.is_connected
        c.disconnect()
        assert not c.is_connected

    def test_context_manager(self, mock_api):
        with i3x.Client("http://test-server:8080") as c:
            assert c.is_connected
        assert not c.is_connected

    def test_on_connect_callback(self, mock_api):
        called_with = []
        c = i3x.Client("http://test-server:8080")
        c.on_connect = lambda client: called_with.append(client)
        c.connect()
        assert len(called_with) == 1
        assert called_with[0] is c
        c.disconnect()

    def test_on_disconnect_callback(self, mock_api):
        called_with = []
        c = i3x.Client("http://test-server:8080")
        c.on_disconnect = lambda client: called_with.append(client)
        c.connect()
        c.disconnect()
        assert len(called_with) == 1


class TestClientExploratory:
    def test_get_namespaces(self, client):
        namespaces = client.get_namespaces()
        assert len(namespaces) == 2
        assert namespaces[0].uri == "http://example.com/ns1"
        assert namespaces[0].display_name == "Namespace One"

    def test_get_object_types(self, mock_api, client):
        mock_api.get("/objecttypes").respond(json=SAMPLE_OBJECT_TYPES)
        types = client.get_object_types()
        assert len(types) == 1
        assert types[0].element_id == "type-1"

    def test_get_object_types_filtered(self, mock_api, client):
        mock_api.get("/objecttypes").respond(json=SAMPLE_OBJECT_TYPES)
        types = client.get_object_types(namespace_uri="http://example.com/ns1")
        assert len(types) == 1

    def test_query_object_types(self, mock_api, client):
        mock_api.post("/objecttypes/query").respond(json=SAMPLE_OBJECT_TYPES)
        types = client.query_object_types(["type-1"])
        assert len(types) == 1

    def test_get_relationship_types(self, mock_api, client):
        mock_api.get("/relationshiptypes").respond(json=SAMPLE_RELATIONSHIP_TYPES)
        types = client.get_relationship_types()
        assert len(types) == 1
        assert types[0].reverse_of == "Is Component Of"

    def test_query_relationship_types(self, mock_api, client):
        mock_api.post("/relationshiptypes/query").respond(json=SAMPLE_RELATIONSHIP_TYPES)
        types = client.query_relationship_types(["rel-1"])
        assert len(types) == 1

    def test_get_objects(self, mock_api, client):
        mock_api.get("/objects").respond(json=SAMPLE_OBJECTS)
        objects = client.get_objects()
        assert len(objects) == 2

    def test_get_objects_filtered(self, mock_api, client):
        mock_api.get("/objects").respond(json=[SAMPLE_OBJECTS[0]])
        objects = client.get_objects(type_id="type-1")
        assert len(objects) == 1

    def test_get_object(self, mock_api, client):
        mock_api.post("/objects/list").respond(json=[SAMPLE_OBJECTS[0]])
        obj = client.get_object("obj-1")
        assert obj.element_id == "obj-1"
        assert obj.display_name == "Sensor A"

    def test_get_object_not_found(self, mock_api, client):
        mock_api.post("/objects/list").respond(json=[])
        with pytest.raises(NotFoundError):
            client.get_object("nonexistent")

    def test_list_objects(self, mock_api, client):
        mock_api.post("/objects/list").respond(json=SAMPLE_OBJECTS)
        objects = client.list_objects(["obj-1", "obj-2"])
        assert len(objects) == 2

    def test_get_related_objects(self, mock_api, client):
        mock_api.post("/objects/related").respond(json=[SAMPLE_OBJECTS[1]])
        related = client.get_related_objects(["obj-1"], "rel-1")
        assert len(related) == 1
        assert related[0].element_id == "obj-2"


class TestClientValues:
    def test_get_value(self, mock_api, client):
        mock_api.post("/objects/value").respond(json=SAMPLE_VALUE_RESPONSE)
        val = client.get_value("obj-1")
        assert val.element_id == "obj-1"
        assert len(val.data) == 1
        assert val.data[0].value == 72.5
        assert val.data[0].quality == "Good"

    def test_get_value_not_found(self, mock_api, client):
        mock_api.post("/objects/value").respond(json={})
        with pytest.raises(NotFoundError):
            client.get_value("nonexistent")

    def test_get_values(self, mock_api, client):
        mock_api.post("/objects/value").respond(json=SAMPLE_VALUE_RESPONSE)
        values = client.get_values(["obj-1"])
        assert "obj-1" in values
        assert values["obj-1"].data[0].value == 72.5

    def test_get_history(self, mock_api, client):
        mock_api.post("/objects/history").respond(json=SAMPLE_HISTORY_RESPONSE)
        history = client.get_history("obj-1", start_time="2026-01-01T00:00:00Z")
        assert len(history.data) == 2
        assert history.data[0].value == 70.0
        assert history.data[1].value == 72.5

    def test_get_history_not_found(self, mock_api, client):
        mock_api.post("/objects/history").respond(json={})
        with pytest.raises(NotFoundError):
            client.get_history("nonexistent")


class TestClientUpdates:
    def test_update_value(self, mock_api, client):
        mock_api.put("/objects/obj-1/value").respond(json={
            "elementId": "obj-1", "success": True, "message": "Updated"
        })
        result = client.update_value("obj-1", {"temperature": 75.0})
        assert result["success"] is True

    def test_update_value_url_encodes(self, mock_api, client):
        mock_api.put("/objects/obj%2F1/value").respond(json={
            "elementId": "obj/1", "success": True, "message": "Updated"
        })
        result = client.update_value("obj/1", {"temperature": 75.0})
        assert result["success"] is True


class TestClientSubscriptions:
    def test_create_subscription(self, mock_api, client):
        mock_api.post("/subscriptions").respond(json={
            "subscriptionId": "sub-1", "message": "Created"
        })
        sub_id = client.create_subscription()
        assert sub_id == "sub-1"

    def test_register_items(self, mock_api, client):
        mock_api.post("/subscriptions/sub-1/register").respond(json={
            "message": "Registered", "totalObjects": 2
        })
        result = client.register_items("sub-1", ["obj-1", "obj-2"])
        assert result["totalObjects"] == 2

    def test_unregister_items(self, mock_api, client):
        mock_api.post("/subscriptions/sub-1/unregister").respond(json={
            "message": "Unregistered"
        })
        result = client.unregister_items("sub-1", ["obj-1"])
        assert result["message"] == "Unregistered"

    def test_get_subscriptions(self, mock_api, client):
        mock_api.get("/subscriptions").respond(json={
            "subscriptionIds": [
                {"subscriptionId": "sub-1", "created": "2026-01-01T00:00:00Z"}
            ]
        })
        subs = client.get_subscriptions()
        assert len(subs) == 1

    def test_get_subscription(self, mock_api, client):
        mock_api.get("/subscriptions/sub-1").respond(json={
            "subscriptionId": "sub-1",
            "created": "2026-01-01T00:00:00Z",
            "isStreaming": False,
            "queuedUpdates": 0,
            "objects": ["obj-1"],
        })
        sub = client.get_subscription("sub-1")
        assert sub.subscription_id == "sub-1"
        assert sub.objects == ["obj-1"]

    def test_unsubscribe_by_object(self, mock_api, client):
        mock_api.delete("/subscriptions/sub-1").respond(json={
            "message": "Deleted", "unsubscribed": ["sub-1"], "not_found": []
        })
        sub = i3x.Subscription(subscription_id="sub-1")
        client.unsubscribe(sub)

    def test_unsubscribe_by_string(self, mock_api, client):
        mock_api.delete("/subscriptions/sub-1").respond(json={
            "message": "Deleted", "unsubscribed": ["sub-1"], "not_found": []
        })
        client.unsubscribe("sub-1")

    def test_subscribe_high_level(self, mock_api, client):
        mock_api.post("/subscriptions").respond(json={
            "subscriptionId": "sub-1", "message": "Created"
        })
        mock_api.post("/subscriptions/sub-1/register").respond(json={
            "message": "Registered", "totalObjects": 2
        })
        mock_api.get("/subscriptions/sub-1").respond(json={
            "subscriptionId": "sub-1",
            "created": "2026-01-01T00:00:00Z",
            "isStreaming": True,
            "queuedUpdates": 0,
            "objects": ["obj-1", "obj-2"],
        })
        sub = client.subscribe(["obj-1", "obj-2"])
        assert sub.subscription_id == "sub-1"
        assert sub.objects == ["obj-1", "obj-2"]

    def test_on_subscribe_callback(self, mock_api, client):
        called_with = []
        client.on_subscribe = lambda c, s: called_with.append(s)
        mock_api.post("/subscriptions").respond(json={
            "subscriptionId": "sub-1", "message": "Created"
        })
        mock_api.post("/subscriptions/sub-1/register").respond(json={
            "message": "Registered", "totalObjects": 1
        })
        mock_api.get("/subscriptions/sub-1").respond(json={
            "subscriptionId": "sub-1",
            "created": "2026-01-01T00:00:00Z",
            "isStreaming": False,
            "queuedUpdates": 0,
            "objects": ["obj-1"],
        })
        client.subscribe(["obj-1"])
        assert len(called_with) == 1
        assert called_with[0].subscription_id == "sub-1"

    def test_sync_subscription(self, mock_api, client):
        mock_api.post("/subscriptions/sub-1/sync").respond(json=[
            {"obj-1": {"data": [{"value": 99, "quality": "Good", "timestamp": "t1"}]}}
        ])
        updates = client.sync_subscription("sub-1")
        assert len(updates) == 1
