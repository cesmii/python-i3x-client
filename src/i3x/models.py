"""Frozen dataclasses representing i3X data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ServerInfo:
    """Server version and capabilities returned by GET /info."""

    spec_version: str
    server_version: str | None = None
    server_name: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerInfo:
        return cls(
            spec_version=data["specVersion"],
            server_version=data.get("serverVersion"),
            server_name=data.get("serverName"),
            capabilities=data.get("capabilities", {}),
        )


@dataclass(frozen=True)
class Namespace:
    """A namespace that organizes types in the i3X address space."""

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
    source_type_id: str = ""
    version: str | None = None
    schema: dict[str, Any] = field(default_factory=dict)
    related: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectType:
        return cls(
            element_id=data["elementId"],
            display_name=data.get("displayName", ""),
            namespace_uri=data.get("namespaceUri", ""),
            source_type_id=data.get("sourceTypeId", ""),
            version=data.get("version"),
            schema=data.get("schema", {}),
            related=data.get("related"),
        )


@dataclass(frozen=True)
class RelationshipType:
    """Defines a type of relationship between object instances."""

    element_id: str
    display_name: str
    namespace_uri: str
    relationship_id: str = ""
    reverse_of: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelationshipType:
        return cls(
            element_id=data["elementId"],
            display_name=data.get("displayName", ""),
            namespace_uri=data.get("namespaceUri", ""),
            relationship_id=data.get("relationshipId", ""),
            reverse_of=data.get("reverseOf", ""),
        )


@dataclass(frozen=True)
class ObjectInstanceMetadata:
    """Extended metadata for an object instance (returned when includeMetadata=true)."""

    type_namespace_uri: str | None = None
    source_type_id: str | None = None
    description: str | None = None
    relationships: dict[str, Any] | None = None
    extended_attributes: dict[str, Any] | None = None
    system: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectInstanceMetadata:
        return cls(
            type_namespace_uri=data.get("typeNamespaceUri"),
            source_type_id=data.get("sourceTypeId"),
            description=data.get("description"),
            relationships=data.get("relationships"),
            extended_attributes=data.get("extendedAttributes"),
            system=data.get("system"),
        )


@dataclass(frozen=True)
class ObjectInstance:
    """An object instance in the i3X address space."""

    element_id: str
    display_name: str
    type_element_id: str
    parent_id: str | None = None
    is_composition: bool = False
    is_extended: bool = False
    metadata: ObjectInstanceMetadata | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectInstance:
        raw_meta = data.get("metadata")
        return cls(
            element_id=data["elementId"],
            display_name=data.get("displayName", ""),
            type_element_id=data.get("typeElementId", ""),
            parent_id=data.get("parentId"),
            is_composition=data.get("isComposition", False),
            is_extended=data.get("isExtended", False),
            metadata=ObjectInstanceMetadata.from_dict(raw_meta) if raw_meta else None,
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
class CurrentValue:
    """Last known value for an element, returned by POST /objects/value."""

    element_id: str
    is_composition: bool
    value: Any
    quality: str
    timestamp: str
    components: dict[str, VQT] | None = None

    @classmethod
    def from_dict(cls, element_id: str, data: dict[str, Any]) -> CurrentValue:
        raw_components = data.get("components")
        components = (
            {k: VQT.from_dict(v) for k, v in raw_components.items()}
            if raw_components
            else None
        )
        return cls(
            element_id=element_id,
            is_composition=data.get("isComposition", False),
            value=data.get("value"),
            quality=data.get("quality", ""),
            timestamp=data.get("timestamp", ""),
            components=components,
        )


@dataclass(frozen=True)
class HistoricalValue:
    """Historical values for an element, returned by POST /objects/history."""

    element_id: str
    is_composition: bool
    values: list[VQT] = field(default_factory=list)

    @classmethod
    def from_dict(cls, element_id: str, data: dict[str, Any]) -> HistoricalValue:
        return cls(
            element_id=element_id,
            is_composition=data.get("isComposition", False),
            values=[VQT.from_dict(v) for v in data.get("values", [])],
        )


@dataclass(frozen=True)
class RelatedObject:
    """An object returned by POST /objects/related, with its relationship context."""

    source_relationship: str
    object: ObjectInstance

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelatedObject:
        return cls(
            source_relationship=data["sourceRelationship"],
            object=ObjectInstance.from_dict(data["object"]),
        )


@dataclass(frozen=True)
class ValueChange:
    """A single value change event received from a subscription stream."""

    element_id: str
    value: Any
    quality: str
    timestamp: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValueChange:
        return cls(
            element_id=data["elementId"],
            value=data.get("value"),
            quality=data.get("quality", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass(frozen=True)
class SyncUpdate:
    """A queued update returned by POST /subscriptions/sync."""

    sequence_number: int
    element_id: str
    value: Any
    quality: str
    timestamp: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SyncUpdate:
        return cls(
            sequence_number=data["sequenceNumber"],
            element_id=data["elementId"],
            value=data.get("value"),
            quality=data.get("quality", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass(frozen=True)
class Subscription:
    """Represents an active subscription."""

    subscription_id: str
    client_id: str | None = None
    display_name: str | None = None
    monitored_objects: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Subscription:
        return cls(
            subscription_id=data["subscriptionId"],
            client_id=data.get("clientId"),
            display_name=data.get("displayName"),
            monitored_objects=data.get("monitoredObjects", []),
        )
