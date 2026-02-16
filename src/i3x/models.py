"""Frozen dataclasses representing I3X/CMIP data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Namespace:
    """A namespace that organizes types and elements."""

    uri: str
    display_name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Namespace:
        return cls(
            uri=data["uri"],
            display_name=data.get("displayName", ""),
        )


@dataclass(frozen=True)
class ObjectType:
    """Defines the schema for object instances."""

    element_id: str
    display_name: str
    namespace_uri: str
    schema: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectType:
        return cls(
            element_id=data["elementId"],
            display_name=data.get("displayName", ""),
            namespace_uri=data.get("namespaceUri", ""),
            schema=data.get("schema", {}),
        )


@dataclass(frozen=True)
class RelationshipType:
    """Defines a type of relationship between object instances."""

    element_id: str
    display_name: str
    namespace_uri: str
    reverse_of: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelationshipType:
        return cls(
            element_id=data["elementId"],
            display_name=data.get("displayName", ""),
            namespace_uri=data.get("namespaceUri", ""),
            reverse_of=data.get("reverseOf", ""),
        )


@dataclass(frozen=True)
class ObjectInstance:
    """An object instance in the CMIP system."""

    element_id: str
    display_name: str
    type_id: str
    namespace_uri: str
    parent_id: str | None = None
    is_composition: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectInstance:
        return cls(
            element_id=data["elementId"],
            display_name=data.get("displayName", ""),
            type_id=data.get("typeId", ""),
            namespace_uri=data.get("namespaceUri", ""),
            parent_id=data.get("parentId"),
            is_composition=data.get("isComposition", False),
        )


@dataclass(frozen=True)
class VQT:
    """A Value/Quality/Timestamp triple."""

    value: Any
    quality: str = ""
    timestamp: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VQT:
        return cls(
            value=data.get("value"),
            quality=data.get("quality", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass(frozen=True)
class LastKnownValue:
    """Last known value for an element, optionally including child values."""

    element_id: str
    data: list[VQT] = field(default_factory=list)
    children: dict[str, LastKnownValue] = field(default_factory=dict)

    @classmethod
    def from_response(cls, element_id: str, value_data: dict[str, Any]) -> LastKnownValue:
        """Parse a single element's value entry from the API response."""
        vqts = [VQT.from_dict(v) for v in value_data.get("data", [])]
        children = {}
        for key, child_data in value_data.items():
            if key == "data":
                continue
            children[key] = cls.from_response(key, child_data)
        return cls(element_id=element_id, data=vqts, children=children)


@dataclass(frozen=True)
class ValueChange:
    """A value change event received from a subscription stream."""

    element_id: str
    data: list[VQT] = field(default_factory=list)
    children: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_stream_event(cls, event_data: dict[str, Any]) -> list[ValueChange]:
        """Parse a stream event dict into ValueChange objects.

        Each stream event is a dict mapping elementId -> value structure.
        """
        changes = []
        for element_id, value_data in event_data.items():
            vqts = [VQT.from_dict(v) for v in value_data.get("data", [])]
            child_data = {k: v for k, v in value_data.items() if k != "data"}
            changes.append(cls(element_id=element_id, data=vqts, children=child_data))
        return changes


@dataclass(frozen=True)
class Subscription:
    """Represents an active subscription."""

    subscription_id: str
    created: str = ""
    is_streaming: bool = False
    queued_updates: int = 0
    objects: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Subscription:
        return cls(
            subscription_id=data["subscriptionId"],
            created=data.get("created", ""),
            is_streaming=data.get("isStreaming", False),
            queued_updates=data.get("queuedUpdates", 0),
            objects=data.get("objects", []),
        )
