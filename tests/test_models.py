"""Tests for i3x.models."""

from i3x.models import (
    LastKnownValue,
    Namespace,
    ObjectInstance,
    ObjectType,
    RelationshipType,
    Subscription,
    ValueChange,
    VQT,
)


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
            "schema": {"type": "object"},
        })
        assert ot.element_id == "t1"
        assert ot.schema == {"type": "object"}

    def test_from_dict_defaults(self):
        ot = ObjectType.from_dict({"elementId": "t1"})
        assert ot.display_name == ""
        assert ot.schema == {}


class TestRelationshipType:
    def test_from_dict(self):
        rt = RelationshipType.from_dict({
            "elementId": "r1",
            "displayName": "Has Component",
            "namespaceUri": "http://example.com",
            "reverseOf": "Is Component Of",
        })
        assert rt.element_id == "r1"
        assert rt.reverse_of == "Is Component Of"


class TestObjectInstance:
    def test_from_dict(self):
        obj = ObjectInstance.from_dict({
            "elementId": "o1",
            "displayName": "Object 1",
            "typeId": "t1",
            "namespaceUri": "http://example.com",
            "parentId": "parent-1",
            "isComposition": True,
        })
        assert obj.element_id == "o1"
        assert obj.parent_id == "parent-1"
        assert obj.is_composition is True

    def test_from_dict_defaults(self):
        obj = ObjectInstance.from_dict({"elementId": "o1"})
        assert obj.parent_id is None
        assert obj.is_composition is False


class TestVQT:
    def test_from_dict(self):
        vqt = VQT.from_dict({"value": 42, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"})
        assert vqt.value == 42
        assert vqt.quality == "Good"

    def test_from_dict_defaults(self):
        vqt = VQT.from_dict({"value": None})
        assert vqt.quality == ""
        assert vqt.timestamp == ""


class TestLastKnownValue:
    def test_from_response_simple(self):
        lkv = LastKnownValue.from_response("obj-1", {
            "data": [{"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"}]
        })
        assert lkv.element_id == "obj-1"
        assert len(lkv.data) == 1
        assert lkv.data[0].value == 72.5

    def test_from_response_with_children(self):
        lkv = LastKnownValue.from_response("parent", {
            "data": [{"value": 1, "quality": "Good", "timestamp": "t1"}],
            "child-1": {
                "data": [{"value": 2, "quality": "Good", "timestamp": "t2"}]
            },
        })
        assert len(lkv.children) == 1
        assert "child-1" in lkv.children
        assert lkv.children["child-1"].data[0].value == 2


class TestValueChange:
    def test_from_stream_event(self):
        changes = ValueChange.from_stream_event({
            "obj-1": {"data": [{"value": 99, "quality": "Good", "timestamp": "t1"}]},
            "obj-2": {"data": [{"value": 100, "quality": "Good", "timestamp": "t2"}]},
        })
        assert len(changes) == 2
        ids = {c.element_id for c in changes}
        assert ids == {"obj-1", "obj-2"}


class TestSubscription:
    def test_from_dict(self):
        sub = Subscription.from_dict({
            "subscriptionId": "sub-1",
            "created": "2026-01-01T00:00:00Z",
            "isStreaming": True,
            "queuedUpdates": 5,
            "objects": ["obj-1", "obj-2"],
        })
        assert sub.subscription_id == "sub-1"
        assert sub.is_streaming is True
        assert sub.objects == ["obj-1", "obj-2"]
