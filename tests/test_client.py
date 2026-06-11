"""Tests for i3x.Client."""

import pytest
import respx

import i3x
from i3x.errors import (
    InvalidServerResponseError,
    NotFoundError,
    NotSupportedError,
    UnsupportedVersionError,
)

from .conftest import (
    SAMPLE_DELETE_BULK,
    SAMPLE_HISTORY_BULK,
    SAMPLE_NAMESPACES,
    SAMPLE_OBJECT_TYPES,
    SAMPLE_OBJECT_TYPES_BULK,
    SAMPLE_OBJECTS,
    SAMPLE_OBJECTS_BULK,
    SAMPLE_OBJECT_BULK_SINGLE,
    SAMPLE_REGISTER_BULK,
    SAMPLE_RELATED_BULK,
    SAMPLE_RELATIONSHIP_TYPES,
    SAMPLE_RELATIONSHIP_TYPES_BULK,
    SAMPLE_SERVER_INFO,
    SAMPLE_SUBSCRIPTION_CREATE,
    SAMPLE_SUBSCRIPTION_LIST,
    SAMPLE_SYNC_RESPONSE,
    SAMPLE_VALUE_BULK,
    bulk,
    bulk_item_err,
    bulk_item_ok,
    success,
)


@pytest.fixture()
def mock_api():
    with respx.mock(base_url="http://test-server:8080") as router:
        # Connectivity check and version detection during connect() use GET /info
        router.get("/info").respond(json=SAMPLE_SERVER_INFO)
        yield router


@pytest.fixture()
def client(mock_api):
    c = i3x.Client("http://test-server:8080", client_id="test-client")
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

    def test_client_id_auto_generated(self, mock_api):
        c = i3x.Client("http://test-server:8080")
        assert len(c.client_id) > 0
        c.connect()
        c.disconnect()

    def test_client_id_custom(self, mock_api):
        c = i3x.Client("http://test-server:8080", client_id="my-client")
        assert c.client_id == "my-client"
        c.connect()
        c.disconnect()


class TestClientVersionDetection:
    def test_alpha_server_raises(self):
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(status_code=404)
            c = i3x.Client("http://test-server:8080")
            with pytest.raises(UnsupportedVersionError, match="alpha"):
                c.connect()
            assert c.is_connected is False

    @pytest.mark.parametrize("spec_version", ["1.0-beta", "0.9", "beta"])
    def test_pre_release_server_warns(self, spec_version):
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(json=success({
                "specVersion": spec_version,
                "capabilities": {},
            }))
            c = i3x.Client("http://test-server:8080")
            with pytest.warns(DeprecationWarning, match="beta"):
                c.connect()
            c.disconnect()

    def test_beta_server_version_warns_despite_spec_1_0(self):
        # Beta servers report specVersion "1.0" like release; only serverVersion differs.
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(json=success({
                "specVersion": "1.0",
                "serverVersion": "beta",
                "capabilities": {},
            }))
            c = i3x.Client("http://test-server:8080")
            with pytest.warns(DeprecationWarning, match="beta"):
                c.connect()
            assert c._is_beta_server is True
            c.disconnect()

    def test_orange_colors_only_for_tty(self, monkeypatch):
        from i3x import client as client_module

        class FakeStderr:
            def __init__(self, tty): self._tty = tty
            def isatty(self): return self._tty

        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr(client_module.sys, "stderr", FakeStderr(True))
        assert client_module._orange("hi") == "\033[38;5;208mhi\033[0m"

        monkeypatch.setattr(client_module.sys, "stderr", FakeStderr(False))
        assert client_module._orange("hi") == "hi"  # piped/redirected: no codes

        monkeypatch.setattr(client_module.sys, "stderr", FakeStderr(True))
        monkeypatch.setenv("NO_COLOR", "1")
        assert client_module._orange("hi") == "hi"  # NO_COLOR honored

    def test_release_server_version_no_warning(self, recwarn):
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(json=success({
                "specVersion": "1.0",
                "serverVersion": "release",
                "capabilities": {},
            }))
            c = i3x.Client("http://test-server:8080")
            c.connect()
            dep = [w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]
            assert dep == []
            assert c._is_beta_server is False
            c.disconnect()

    def test_missing_spec_version_is_invalid(self):
        # A JSON object with no specVersion is not identifiable as i3X.
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(json=success({"capabilities": {}}))
            c = i3x.Client("http://test-server:8080")
            with pytest.raises(InvalidServerResponseError):
                c.connect()
            assert c.is_connected is False

    def test_v1_server_no_warning(self, mock_api, recwarn):
        c = i3x.Client("http://test-server:8080")
        c.connect()
        dep_warnings = [w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]
        assert dep_warnings == []
        c.disconnect()

    def test_server_info_captured_on_connect(self, mock_api):
        c = i3x.Client("http://test-server:8080")
        assert c.server_info is None
        c.connect()
        assert c.server_info is not None
        assert c.server_info.spec_version == "1.0"
        c.disconnect()
        assert c.server_info is None


class TestClientInvalidServerResponse:
    """A reachable endpoint that is not a valid i3X server raises a distinct
    InvalidServerResponseError — never the alpha (UnsupportedVersionError)."""

    def _expect_invalid(self, setup):
        with respx.mock(base_url="http://test-server:8080") as router:
            setup(router)
            c = i3x.Client("http://test-server:8080")
            with pytest.raises(InvalidServerResponseError):
                c.connect()
            assert c.is_connected is False
            assert c.server_info is None

    def test_html_login_page(self):
        # SSO/gateway redirect lands on an HTML page, not an alpha server.
        self._expect_invalid(lambda r: r.get("/info").respond(
            status_code=200, html="<!doctype html><html>login</html>"))

    def test_json_with_wrong_content_type(self):
        # Valid-looking JSON but served as text/plain (proxy/server misconfig).
        self._expect_invalid(lambda r: r.get("/info").respond(
            status_code=200,
            text='{"success":true,"result":{"specVersion":"1.0"}}',
            headers={"content-type": "text/plain"}))

    def test_204_no_content(self):
        self._expect_invalid(lambda r: r.get("/info").respond(status_code=204))

    def test_empty_body_json_content_type(self):
        # Must not crash with a JSONDecodeError.
        self._expect_invalid(lambda r: r.get("/info").respond(
            status_code=200, headers={"content-type": "application/json"}))

    def test_bulk_envelope_unwraps_to_list(self):
        self._expect_invalid(lambda r: r.get("/info").respond(
            json={"success": True, "results": [{"specVersion": "1.0"}]}))

    def test_non_object_json_result(self):
        self._expect_invalid(lambda r: r.get("/info").respond(json=success(None)))

    def test_message_reports_status_and_content_type(self):
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(status_code=200, html="<html></html>")
            c = i3x.Client("http://test-server:8080")
            with pytest.raises(InvalidServerResponseError, match="text/html"):
                c.connect()


class TestClientServerInfo:
    def test_get_info(self, mock_api, client):
        info = client.get_info()
        assert info.spec_version == "1.0"
        assert info.server_version == "2.0.0"
        assert info.server_name == "TestServer"
        assert info.capabilities["subscribe"]["stream"] is True


class TestClientExploratory:
    def test_get_namespaces(self, mock_api, client):
        mock_api.get("/namespaces").respond(json=SAMPLE_NAMESPACES)
        namespaces = client.get_namespaces()
        assert len(namespaces) == 2
        assert namespaces[0].uri == "http://example.com/ns1"
        assert namespaces[0].display_name == "Namespace One"

    def test_get_object_types(self, mock_api, client):
        mock_api.get("/objecttypes").respond(json=SAMPLE_OBJECT_TYPES)
        types = client.get_object_types()
        assert len(types) == 1
        assert types[0].element_id == "type-1"
        assert types[0].source_type_id == "TemperatureSensorType"
        assert types[0].version == "1.0.0"

    def test_get_object_types_filtered(self, mock_api, client):
        mock_api.get("/objecttypes").respond(json=SAMPLE_OBJECT_TYPES)
        types = client.get_object_types(namespace_uri="http://example.com/ns1")
        assert len(types) == 1

    def test_query_object_types(self, mock_api, client):
        mock_api.post("/objecttypes/query").respond(json=SAMPLE_OBJECT_TYPES_BULK)
        types = client.query_object_types(["type-1"])
        assert len(types) == 1
        assert types[0].element_id == "type-1"

    def test_get_relationship_types(self, mock_api, client):
        mock_api.get("/relationshiptypes").respond(json=SAMPLE_RELATIONSHIP_TYPES)
        types = client.get_relationship_types()
        assert len(types) == 1
        assert types[0].reverse_of == "ComponentOf"
        assert types[0].relationship_id == "HasComponent"

    def test_query_relationship_types(self, mock_api, client):
        mock_api.post("/relationshiptypes/query").respond(json=SAMPLE_RELATIONSHIP_TYPES_BULK)
        types = client.query_relationship_types(["rel-1"])
        assert len(types) == 1

    def test_get_objects(self, mock_api, client):
        mock_api.get("/objects").respond(json=SAMPLE_OBJECTS)
        objects = client.get_objects()
        assert len(objects) == 2
        assert objects[0].type_element_id == "type-1"

    def test_get_objects_filtered_by_type(self, mock_api, client):
        mock_api.get("/objects").respond(json=success([SAMPLE_OBJECTS["result"][0]]))
        objects = client.get_objects(type_element_id="type-1")
        assert len(objects) == 1

    def test_get_objects_root(self, mock_api, client):
        mock_api.get("/objects").respond(json=SAMPLE_OBJECTS)
        objects = client.get_objects(root=True)
        assert len(objects) == 2

    def test_get_object(self, mock_api, client):
        mock_api.post("/objects/list").respond(json=SAMPLE_OBJECT_BULK_SINGLE)
        obj = client.get_object("obj-1")
        assert obj.element_id == "obj-1"
        assert obj.display_name == "Sensor A"
        assert obj.type_element_id == "type-1"

    def test_get_object_not_found(self, mock_api, client):
        mock_api.post("/objects/list").respond(json=bulk([
            bulk_item_err("nonexistent", 404, "Element not found: nonexistent", title="Not Found"),
        ]))
        with pytest.raises(NotFoundError, match="Element not found: nonexistent"):
            client.get_object("nonexistent")

    def test_list_objects(self, mock_api, client):
        mock_api.post("/objects/list").respond(json=SAMPLE_OBJECTS_BULK)
        objects = client.list_objects(["obj-1", "obj-2"])
        assert len(objects) == 2

    def test_get_related_objects(self, mock_api, client):
        mock_api.post("/objects/related").respond(json=SAMPLE_RELATED_BULK)
        related = client.get_related_objects(["obj-1"])
        assert len(related) == 1
        assert related[0].source_relationship == "HasChildren"
        assert related[0].object.element_id == "obj-2"

    def test_get_related_objects_with_relationship_filter(self, mock_api, client):
        mock_api.post("/objects/related").respond(json=SAMPLE_RELATED_BULK)
        related = client.get_related_objects(["obj-1"], relationship_type="HasChildren")
        assert len(related) == 1


class TestClientValues:
    def test_get_value(self, mock_api, client):
        mock_api.post("/objects/value").respond(json=SAMPLE_VALUE_BULK)
        val = client.get_value("obj-1")
        assert val.element_id == "obj-1"
        assert val.value == 72.5
        assert val.quality == "Good"
        assert val.timestamp == "2026-01-01T00:00:00Z"
        assert val.is_composition is False
        assert val.components is None

    def test_get_value_not_found(self, mock_api, client):
        mock_api.post("/objects/value").respond(json=bulk([
            bulk_item_err("nonexistent", 404, "Element not found: nonexistent", title="Not Found"),
        ]))
        with pytest.raises(NotFoundError):
            client.get_value("nonexistent")

    def test_get_values(self, mock_api, client):
        mock_api.post("/objects/value").respond(json=SAMPLE_VALUE_BULK)
        values = client.get_values(["obj-1"])
        assert "obj-1" in values
        assert values["obj-1"].value == 72.5

    def test_get_value_with_components(self, mock_api, client):
        mock_api.post("/objects/value").respond(json={
            "success": True,
            "results": [{
                "success": True,
                "elementId": "pump-101",
                "result": {
                    "isComposition": True,
                    "value": None,
                    "quality": "GoodNoData",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "components": {
                        "bearing-temp": {"value": 70.34, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"},
                    },
                },
            }],
        })
        val = client.get_value("pump-101")
        assert val.is_composition is True
        assert val.components is not None
        assert val.components["bearing-temp"].value == 70.34

    def test_get_history(self, mock_api, client):
        mock_api.post("/objects/history").respond(json=SAMPLE_HISTORY_BULK)
        history = client.get_history("obj-1", start_time="2026-01-01T00:00:00Z")
        assert len(history.values) == 2
        assert history.values[0].value == 70.0
        assert history.values[1].value == 72.5
        assert history.is_composition is False

    def test_get_history_not_found(self, mock_api, client):
        mock_api.post("/objects/history").respond(json=bulk([
            bulk_item_err("nonexistent", 404, "Element not found: nonexistent", title="Not Found"),
        ]))
        with pytest.raises(NotFoundError):
            client.get_history("nonexistent")


class TestClientUpdates:
    def test_update_value_with_vqt_dict(self, mock_api, client):
        route = mock_api.put("/objects/value").respond(json=bulk([bulk_item_ok("obj-1", None)]))
        client.update_value("obj-1", {"value": 75.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"})
        import json
        payload = json.loads(route.calls.last.request.content)
        assert payload == {"updates": [{
            "elementId": "obj-1",
            "value": {"value": 75.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"},
        }]}

    def test_update_value_with_raw_value(self, mock_api, client):
        route = mock_api.put("/objects/value").respond(json=bulk([bulk_item_ok("obj-1", None)]))
        client.update_value("obj-1", 75.0)
        import json
        payload = json.loads(route.calls.last.request.content)
        assert payload == {"updates": [{"elementId": "obj-1", "value": {"value": 75.0}}]}

    def test_update_value_failure_raises(self, mock_api, client):
        mock_api.put("/objects/value").respond(json=bulk([
            bulk_item_err("obj-x", 404, "Element not found: obj-x", title="Not Found"),
        ]))
        with pytest.raises(NotFoundError, match="Element not found: obj-x"):
            client.update_value("obj-x", 75.0)

    def test_update_values_bulk(self, mock_api, client):
        route = mock_api.put("/objects/value").respond(json=bulk([
            bulk_item_ok("obj-1", None),
            bulk_item_ok("obj-2", None),
        ]))
        results = client.update_values({"obj-1": 75.0, "obj-2": {"value": 18.3, "quality": "Good"}})
        assert len(results) == 2
        assert all(item["success"] for item in results)
        import json
        payload = json.loads(route.calls.last.request.content)
        assert payload == {"updates": [
            {"elementId": "obj-1", "value": {"value": 75.0}},
            {"elementId": "obj-2", "value": {"value": 18.3, "quality": "Good"}},
        ]}

    def test_update_history(self, mock_api, client):
        route = mock_api.put("/objects/history").respond(json=bulk([bulk_item_ok("obj-1", None)]))
        client.update_history("obj-1", [
            {"value": 70.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"},
            {"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T01:00:00Z"},
        ])
        import json
        payload = json.loads(route.calls.last.request.content)
        assert [u["elementId"] for u in payload["updates"]] == ["obj-1", "obj-1"]
        assert payload["updates"][0]["value"]["value"] == 70.0

    def test_update_history_not_supported(self, mock_api, client):
        mock_api.put("/objects/history").respond(status_code=501, json={
            "success": False,
            "responseDetail": {
                "title": "Not Implemented",
                "status": 501,
                "detail": "This server does not support history updates",
            },
        })
        with pytest.raises(NotSupportedError, match="history updates"):
            client.update_history("obj-1", {"value": 70.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"})


class TestClientBetaUpdates:
    """Beta servers route value updates to per-element PUT /objects/{id}/value."""

    @pytest.fixture()
    def beta_client(self):
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(json=success({
                "specVersion": "1.0",
                "serverVersion": "beta",
                "capabilities": {},
            }))
            c = i3x.Client("http://test-server:8080", client_id="test-client")
            with pytest.warns(DeprecationWarning):
                c.connect()
            yield c, router
            c.disconnect()

    def test_update_value_uses_per_element_endpoint(self, beta_client):
        c, router = beta_client
        route = router.put("/objects/obj-1/value").respond(json=success(None))
        c.update_value("obj-1", 75.0)
        import json
        assert route.called
        assert json.loads(route.calls.last.request.content) == {"value": 75.0}

    def test_update_value_sends_bare_vqt(self, beta_client):
        c, router = beta_client
        route = router.put("/objects/obj-1/value").respond(json=success(None))
        c.update_value("obj-1", {"value": 75.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"})
        import json
        assert json.loads(route.calls.last.request.content) == {
            "value": 75.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z",
        }

    def test_update_value_encodes_element_id(self, beta_client):
        c, router = beta_client
        route = router.put("/objects/ns%3Aobj%2F1/value").respond(json=success(None))
        c.update_value("ns:obj/1", 75.0)
        assert route.called

    def test_update_values_routes_per_element(self, beta_client):
        c, router = beta_client
        r1 = router.put("/objects/obj-1/value").respond(json=success(None))
        r2 = router.put("/objects/obj-2/value").respond(json=success(None))
        results = c.update_values({"obj-1": 75.0, "obj-2": {"value": 18.3, "quality": "Good"}})
        assert r1.called and r2.called
        assert [item["elementId"] for item in results] == ["obj-1", "obj-2"]
        assert all(item["success"] for item in results)


class TestClientSubscriptions:
    def test_create_subscription(self, mock_api, client):
        mock_api.post("/subscriptions").respond(json=SAMPLE_SUBSCRIPTION_CREATE)
        sub_id = client.create_subscription()
        assert sub_id == "sub-1"

    def test_create_subscription_sends_client_id(self, mock_api, client):
        route = mock_api.post("/subscriptions").respond(json=SAMPLE_SUBSCRIPTION_CREATE)
        client.create_subscription()
        body = route.calls.last.request
        import json
        payload = json.loads(body.content)
        assert payload["clientId"] == "test-client"

    def test_register_items(self, mock_api, client):
        mock_api.post("/subscriptions/register").respond(json=SAMPLE_REGISTER_BULK)
        results = client.register_items("sub-1", ["obj-1", "obj-2"])
        assert len(results) == 2
        assert results[0]["success"] is True

    def test_unregister_items(self, mock_api, client):
        mock_api.post("/subscriptions/unregister").respond(json={
            "success": True,
            "results": [{"success": True, "elementId": "obj-1", "result": None}],
        })
        results = client.unregister_items("sub-1", ["obj-1"])
        assert len(results) == 1

    def test_get_subscription(self, mock_api, client):
        mock_api.post("/subscriptions/list").respond(json=SAMPLE_SUBSCRIPTION_LIST)
        sub = client.get_subscription("sub-1")
        assert sub.subscription_id == "sub-1"
        assert len(sub.monitored_objects) == 1

    def test_get_subscription_not_found(self, mock_api, client):
        mock_api.post("/subscriptions/list").respond(json=bulk([
            bulk_item_err("sub-x", 404, "Subscription not found: sub-x", title="Not Found"),
        ]))
        with pytest.raises(NotFoundError):
            client.get_subscription("sub-x")

    def test_list_subscriptions(self, mock_api, client):
        mock_api.post("/subscriptions/list").respond(json=SAMPLE_SUBSCRIPTION_LIST)
        subs = client.list_subscriptions(["sub-1"])
        assert len(subs) == 1
        assert subs[0].subscription_id == "sub-1"

    def test_unsubscribe_by_object(self, mock_api, client):
        mock_api.post("/subscriptions/delete").respond(json=SAMPLE_DELETE_BULK)
        sub = i3x.Subscription(subscription_id="sub-1")
        client.unsubscribe(sub)

    def test_unsubscribe_by_string(self, mock_api, client):
        mock_api.post("/subscriptions/delete").respond(json=SAMPLE_DELETE_BULK)
        client.unsubscribe("sub-1")

    def test_subscribe_high_level(self, mock_api, client):
        mock_api.post("/subscriptions").respond(json=SAMPLE_SUBSCRIPTION_CREATE)
        mock_api.post("/subscriptions/register").respond(json=SAMPLE_REGISTER_BULK)
        sub = client.subscribe(["obj-1", "obj-2"])
        assert sub.subscription_id == "sub-1"
        assert sub.client_id == "test-client"
        assert len(sub.monitored_objects) == 2

    def test_on_subscribe_callback(self, mock_api, client):
        called_with = []
        client.on_subscribe = lambda c, s: called_with.append(s)
        mock_api.post("/subscriptions").respond(json=SAMPLE_SUBSCRIPTION_CREATE)
        mock_api.post("/subscriptions/register").respond(json=SAMPLE_REGISTER_BULK)
        client.subscribe(["obj-1"])
        assert len(called_with) == 1
        assert called_with[0].subscription_id == "sub-1"

    def test_sync_subscription(self, mock_api, client):
        mock_api.post("/subscriptions/sync").respond(json=SAMPLE_SYNC_RESPONSE)
        batches = client.sync_subscription("sub-1")
        assert len(batches) == 2
        assert batches[0].sequence_number == 1
        assert len(batches[0].updates) == 1
        assert batches[0].updates[0].element_id == "obj-1"
        assert batches[0].updates[0].value == 72.5
        assert batches[1].sequence_number == 2
        assert len(batches[1].updates) == 2

    def test_sync_subscription_empty(self, mock_api, client):
        mock_api.post("/subscriptions/sync").respond(json=success([]))
        assert client.sync_subscription("sub-1") == []

    def test_sync_subscription_with_last_sequence(self, mock_api, client):
        route = mock_api.post("/subscriptions/sync").respond(json=SAMPLE_SYNC_RESPONSE)
        client.sync_subscription("sub-1", last_sequence_number=3)
        import json
        payload = json.loads(route.calls.last.request.content)
        assert payload["lastSequenceNumber"] == 3

    def test_sync_subscription_by_object(self, mock_api, client):
        mock_api.post("/subscriptions/sync").respond(json=SAMPLE_SYNC_RESPONSE)
        sub = i3x.Subscription(subscription_id="sub-1")
        batches = client.sync_subscription(sub)
        assert len(batches) == 2
