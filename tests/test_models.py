"""Tests for i3x.models."""

from i3x.models import (
    CurrentValue,
    HistoricalValue,
    Namespace,
    ObjectInstance,
    ObjectInstanceMetadata,
    ObjectType,
    RelatedObject,
    RelationshipType,
    ServerInfo,
    Subscription,
    SyncUpdate,
    ValueChange,
    VQT,
)


class TestServerInfo:
    def test_from_dict(self):
        info = ServerInfo.from_dict({
            "specVersion": "1.0",
            "serverVersion": "2.0.0",
            "serverName": "TestServer",
            "capabilities": {"query": {"history": True}},
        })
        assert info.spec_version == "1.0"
        assert info.server_version == "2.0.0"
        assert info.server_name == "TestServer"
        assert info.capabilities["query"]["history"] is True

    def test_from_dict_optional_fields(self):
        info = ServerInfo.from_dict({"specVersion": "1.0", "capabilities": {}})
        assert info.server_version is None
        assert info.server_name is None
        assert info.capabilities == {}


class TestNamespace:
    def test_from_dict(self):
        ns = Namespace.from_dict({"uri": "http://example.com", "displayName": "Example"})
        assert ns.uri == "http://example.com"
        assert ns.display_name == "Example"

    def test_from_dict_defaults(self):
        ns = Namespace.from_dict({"uri": "http://example.com"})
        assert ns.display_name == ""

    def test_frozen(self):
        ns = Namespace.from_dict({"uri": "http://example.com", "displayName": "Example"})
        try:
            ns.uri = "other"  # type: ignore[misc]
            assert False, "Should raise"
        except AttributeError:
            pass


class TestObjectType:
    def test_from_dict(self):
        ot = ObjectType.from_dict({
            "elementId": "t1",
            "displayName": "Type 1",
            "namespaceUri": "http://example.com",
            "sourceTypeId": "MyType",
            "version": "1.0.0",
            "schema": {"type": "object"},
        })
        assert ot.element_id == "t1"
        assert ot.source_type_id == "MyType"
        assert ot.version == "1.0.0"
        assert ot.schema == {"type": "object"}

    def test_from_dict_defaults(self):
        ot = ObjectType.from_dict({"elementId": "t1"})
        assert ot.display_name == ""
        assert ot.source_type_id == ""
        assert ot.version is None
        assert ot.schema == {}
        assert ot.related is None


class TestRelationshipType:
    def test_from_dict(self):
        rt = RelationshipType.from_dict({
            "elementId": "r1",
            "displayName": "Has Component",
            "namespaceUri": "http://example.com",
            "relationshipId": "HasComponent",
            "reverseOf": "ComponentOf",
        })
        assert rt.element_id == "r1"
        assert rt.relationship_id == "HasComponent"
        assert rt.reverse_of == "ComponentOf"

    def test_from_dict_defaults(self):
        rt = RelationshipType.from_dict({"elementId": "r1"})
        assert rt.relationship_id == ""
        assert rt.reverse_of == ""


class TestObjectInstanceMetadata:
    def test_from_dict(self):
        meta = ObjectInstanceMetadata.from_dict({
            "typeNamespaceUri": "http://example.com/ns",
            "sourceTypeId": "SomeType",
            "description": "A test object",
            "relationships": {"HasParent": "root"},
            "extendedAttributes": {"serial": {"type": "string"}},
            "system": {"vendor_id": "abc"},
        })
        assert meta.type_namespace_uri == "http://example.com/ns"
        assert meta.source_type_id == "SomeType"
        assert meta.description == "A test object"
        assert meta.relationships == {"HasParent": "root"}
        assert meta.extended_attributes == {"serial": {"type": "string"}}
        assert meta.system == {"vendor_id": "abc"}

    def test_from_dict_all_optional(self):
        meta = ObjectInstanceMetadata.from_dict({})
        assert meta.type_namespace_uri is None
        assert meta.relationships is None


class TestObjectInstance:
    def test_from_dict(self):
        obj = ObjectInstance.from_dict({
            "elementId": "o1",
            "displayName": "Object 1",
            "typeElementId": "t1",
            "parentId": "parent-1",
            "isComposition": True,
            "isExtended": True,
        })
        assert obj.element_id == "o1"
        assert obj.type_element_id == "t1"
        assert obj.parent_id == "parent-1"
        assert obj.is_composition is True
        assert obj.is_extended is True
        assert obj.metadata is None

    def test_from_dict_with_metadata(self):
        obj = ObjectInstance.from_dict({
            "elementId": "o1",
            "displayName": "Object 1",
            "typeElementId": "t1",
            "isComposition": False,
            "metadata": {
                "typeNamespaceUri": "http://example.com",
                "sourceTypeId": "T1",
            },
        })
        assert obj.metadata is not None
        assert obj.metadata.type_namespace_uri == "http://example.com"

    def test_from_dict_defaults(self):
        obj = ObjectInstance.from_dict({"elementId": "o1"})
        assert obj.parent_id is None
        assert obj.is_composition is False
        assert obj.is_extended is False


class TestVQT:
    def test_from_dict(self):
        vqt = VQT.from_dict({"value": 42, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"})
        assert vqt.value == 42
        assert vqt.quality == "Good"
        assert vqt.timestamp == "2026-01-01T00:00:00Z"

    def test_from_dict_defaults(self):
        vqt = VQT.from_dict({"value": None})
        assert vqt.quality == ""
        assert vqt.timestamp == ""


class TestCurrentValue:
    def test_from_dict_simple(self):
        cv = CurrentValue.from_dict("obj-1", {
            "isComposition": False,
            "value": 72.5,
            "quality": "Good",
            "timestamp": "2026-01-01T00:00:00Z",
        })
        assert cv.element_id == "obj-1"
        assert cv.is_composition is False
        assert cv.value == 72.5
        assert cv.quality == "Good"
        assert cv.components is None

    def test_from_dict_with_components(self):
        cv = CurrentValue.from_dict("pump-101", {
            "isComposition": True,
            "value": None,
            "quality": "GoodNoData",
            "timestamp": "2026-01-01T00:00:00Z",
            "components": {
                "bearing-temp": {"value": 70.34, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"},
            },
        })
        assert cv.is_composition is True
        assert cv.components is not None
        assert "bearing-temp" in cv.components
        assert cv.components["bearing-temp"].value == 70.34


class TestHistoricalValue:
    def test_from_dict(self):
        hv = HistoricalValue.from_dict("obj-1", {
            "isComposition": False,
            "values": [
                {"value": 70.0, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"},
                {"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T01:00:00Z"},
            ],
        })
        assert hv.element_id == "obj-1"
        assert hv.is_composition is False
        assert len(hv.values) == 2
        assert hv.values[0].value == 70.0
        assert hv.values[1].value == 72.5

    def test_from_dict_empty(self):
        hv = HistoricalValue.from_dict("obj-1", {"isComposition": False, "values": []})
        assert len(hv.values) == 0


class TestRelatedObject:
    def test_from_dict(self):
        ro = RelatedObject.from_dict({
            "sourceRelationship": "HasChildren",
            "object": {
                "elementId": "child-1",
                "displayName": "Child 1",
                "typeElementId": "type-1",
                "isComposition": False,
            },
        })
        assert ro.source_relationship == "HasChildren"
        assert ro.object.element_id == "child-1"


class TestValueChange:
    def test_from_dict(self):
        vc = ValueChange.from_dict({
            "elementId": "obj-1",
            "value": 99.5,
            "quality": "Good",
            "timestamp": "2026-01-01T00:00:00Z",
        })
        assert vc.element_id == "obj-1"
        assert vc.value == 99.5
        assert vc.quality == "Good"
        assert vc.timestamp == "2026-01-01T00:00:00Z"


class TestSyncUpdate:
    def test_from_dict(self):
        su = SyncUpdate.from_dict({
            "sequenceNumber": 5,
            "elementId": "obj-1",
            "value": 42.0,
            "quality": "Good",
            "timestamp": "2026-01-01T00:00:00Z",
        })
        assert su.sequence_number == 5
        assert su.element_id == "obj-1"
        assert su.value == 42.0


class TestSubscription:
    def test_from_dict(self):
        sub = Subscription.from_dict({
            "subscriptionId": "sub-1",
            "clientId": "client-abc",
            "displayName": "My Sub",
            "monitoredObjects": [{"elementId": "obj-1", "maxDepth": 1}],
        })
        assert sub.subscription_id == "sub-1"
        assert sub.client_id == "client-abc"
        assert sub.display_name == "My Sub"
        assert len(sub.monitored_objects) == 1

    def test_from_dict_minimal(self):
        sub = Subscription.from_dict({"subscriptionId": "sub-1"})
        assert sub.subscription_id == "sub-1"
        assert sub.client_id is None
        assert sub.display_name is None
        assert sub.monitored_objects == []
