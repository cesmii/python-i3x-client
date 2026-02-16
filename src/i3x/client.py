"""Main Client class for interacting with i3X servers."""

from __future__ import annotations

import logging
from typing import Any, Callable
from urllib.parse import quote

from ._subscription import SubscriptionManager
from ._transport import Transport
from .models import (
    LastKnownValue,
    Namespace,
    ObjectInstance,
    ObjectType,
    RelationshipType,
    Subscription,
    ValueChange,
    VQT,
)

logger = logging.getLogger("i3x")

# Callback type aliases for documentation
# on_connect(client)
# on_disconnect(client)
# on_value_change(client, change: ValueChange)
# on_subscribe(client, subscription: Subscription)
# on_error(client, error: Exception)


class Client:
    """High-level client for i3X servers.

    Usage::

        client = i3x.Client("https://i3x.example.com")
        client.connect()
        namespaces = client.get_namespaces()
        client.disconnect()

    Or as a context manager::

        with i3x.Client("https://i3x.example.com") as client:
            namespaces = client.get_namespaces()
    """

    def __init__(
        self,
        base_url: str,
        auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
    ):
        self._transport = Transport(base_url, auth=auth, timeout=timeout)
        self._sub_manager: SubscriptionManager | None = None

        # Callbacks
        self.on_connect: Callable[[Client], None] | None = None
        self.on_disconnect: Callable[[Client], None] | None = None
        self.on_value_change: Callable[[Client, ValueChange], None] | None = None
        self.on_subscribe: Callable[[Client, Subscription], None] | None = None
        self.on_error: Callable[[Client, Exception], None] | None = None

    # -- Connection lifecycle --

    @property
    def is_connected(self) -> bool:
        return self._transport.is_open

    def connect(self) -> None:
        """Connect to the i3X server."""
        self._transport.open()
        self._sub_manager = SubscriptionManager(
            transport=self._transport,
            on_event=self._handle_value_changes,
            on_error=self._handle_error,
        )
        if self.on_connect:
            self.on_connect(self)

    def disconnect(self) -> None:
        """Disconnect from the i3X server and stop all subscriptions."""
        if self._sub_manager:
            self._sub_manager.stop_all()
            self._sub_manager = None
        self._transport.close()
        if self.on_disconnect:
            self.on_disconnect(self)

    def __enter__(self) -> Client:
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disconnect()

    # -- Exploratory methods --

    def get_namespaces(self) -> list[Namespace]:
        """Get all namespaces from the server."""
        data = self._transport.get("/namespaces")
        return [Namespace.from_dict(item) for item in data]

    def get_object_types(self, namespace_uri: str | None = None) -> list[ObjectType]:
        """Get object types, optionally filtered by namespace."""
        params = {}
        if namespace_uri is not None:
            params["namespaceUri"] = namespace_uri
        data = self._transport.get("/objecttypes", params=params or None)
        return [ObjectType.from_dict(item) for item in data]

    def query_object_types(self, element_ids: list[str]) -> list[ObjectType]:
        """Query object types by their element IDs."""
        data = self._transport.post("/objecttypes/query", json={"elementIds": element_ids})
        return [ObjectType.from_dict(item) for item in data]

    def get_relationship_types(self, namespace_uri: str | None = None) -> list[RelationshipType]:
        """Get relationship types, optionally filtered by namespace."""
        params = {}
        if namespace_uri is not None:
            params["namespaceUri"] = namespace_uri
        data = self._transport.get("/relationshiptypes", params=params or None)
        return [RelationshipType.from_dict(item) for item in data]

    def query_relationship_types(self, element_ids: list[str]) -> list[RelationshipType]:
        """Query relationship types by their element IDs."""
        data = self._transport.post("/relationshiptypes/query", json={"elementIds": element_ids})
        return [RelationshipType.from_dict(item) for item in data]

    def get_objects(
        self,
        type_id: str | None = None,
        include_metadata: bool = False,
    ) -> list[ObjectInstance]:
        """Get object instances, optionally filtered by type."""
        params: dict[str, Any] = {}
        if type_id is not None:
            params["typeId"] = type_id
        if include_metadata:
            params["includeMetadata"] = "true"
        data = self._transport.get("/objects", params=params or None)
        return [ObjectInstance.from_dict(item) for item in data]

    def get_object(self, element_id: str) -> ObjectInstance:
        """Get a single object by element ID."""
        data = self._transport.post("/objects/list", json={"elementIds": [element_id]})
        if not data:
            from . import errors
            raise errors.NotFoundError(f"Object not found: {element_id}", status_code=404)
        return ObjectInstance.from_dict(data[0])

    def list_objects(self, element_ids: list[str]) -> list[ObjectInstance]:
        """Get multiple objects by their element IDs."""
        data = self._transport.post("/objects/list", json={"elementIds": element_ids})
        return [ObjectInstance.from_dict(item) for item in data]

    def get_related_objects(
        self,
        element_ids: list[str],
        relationship_type: str,
    ) -> list[ObjectInstance]:
        """Get objects related to the given elements by a relationship type."""
        data = self._transport.post(
            "/objects/related",
            json={"elementIds": element_ids, "relationshipType": relationship_type},
        )
        return [ObjectInstance.from_dict(item) for item in data]

    # -- Value methods --

    def get_value(self, element_id: str, max_depth: int = 1) -> LastKnownValue:
        """Get the last known value for an element."""
        data = self._transport.post(
            "/objects/value",
            json={"elementIds": [element_id], "maxDepth": max_depth},
        )
        if element_id not in data:
            from . import errors
            raise errors.NotFoundError(f"No value for: {element_id}", status_code=404)
        return LastKnownValue.from_response(element_id, data[element_id])

    def get_values(
        self,
        element_ids: list[str],
        max_depth: int = 1,
    ) -> dict[str, LastKnownValue]:
        """Get last known values for multiple elements."""
        data = self._transport.post(
            "/objects/value",
            json={"elementIds": element_ids, "maxDepth": max_depth},
        )
        return {
            eid: LastKnownValue.from_response(eid, val)
            for eid, val in data.items()
        }

    def get_history(
        self,
        element_id: str,
        start_time: str | None = None,
        end_time: str | None = None,
        max_depth: int = 1,
    ) -> LastKnownValue:
        """Get historical values for an element."""
        body: dict[str, Any] = {
            "elementIds": [element_id],
            "maxDepth": max_depth,
        }
        if start_time is not None:
            body["startTime"] = start_time
        if end_time is not None:
            body["endTime"] = end_time
        data = self._transport.post("/objects/history", json=body)
        if element_id not in data:
            from . import errors
            raise errors.NotFoundError(f"No history for: {element_id}", status_code=404)
        return LastKnownValue.from_response(element_id, data[element_id])

    # -- Update methods --

    def update_value(self, element_id: str, value: Any) -> dict[str, Any]:
        """Update the current value of an element."""
        encoded_id = quote(element_id, safe="")
        return self._transport.put(f"/objects/{encoded_id}/value", json=value)

    def update_history(self, element_id: str, value: Any) -> dict[str, Any]:
        """Update historical values for an element."""
        encoded_id = quote(element_id, safe="")
        return self._transport.put(f"/objects/{encoded_id}/history", json=value)

    # -- Subscription methods (high-level) --

    def subscribe(
        self,
        element_ids: list[str],
        max_depth: int = 0,
    ) -> Subscription:
        """Create a subscription, register items, and start SSE streaming.

        This is the high-level convenience method that combines:
        1. Create a subscription
        2. Register monitored items
        3. Start the SSE background stream
        """
        # 1. Create subscription
        result = self._transport.post("/subscriptions", json={})
        subscription_id = result["subscriptionId"]

        # 2. Register items
        self._transport.post(
            f"/subscriptions/{subscription_id}/register",
            json={"elementIds": element_ids, "maxDepth": max_depth},
        )

        # 3. Start SSE stream
        if self._sub_manager:
            self._sub_manager.add(subscription_id)

        # Fetch full subscription info
        sub_data = self._transport.get(f"/subscriptions/{subscription_id}")
        sub = Subscription.from_dict(sub_data)

        if self.on_subscribe:
            self.on_subscribe(self, sub)

        return sub

    def unsubscribe(self, subscription: Subscription | str) -> None:
        """Stop streaming and delete a subscription."""
        sub_id = (
            subscription.subscription_id
            if isinstance(subscription, Subscription)
            else subscription
        )
        if self._sub_manager:
            self._sub_manager.remove(sub_id)
        self._transport.delete(f"/subscriptions/{sub_id}")

    def sync_subscription(self, subscription: Subscription | str) -> list[dict[str, Any]]:
        """Poll queued updates for a subscription (QoS2 / sync mode)."""
        sub_id = (
            subscription.subscription_id
            if isinstance(subscription, Subscription)
            else subscription
        )
        return self._transport.post(f"/subscriptions/{sub_id}/sync")

    # -- Subscription methods (low-level) --

    def create_subscription(self) -> str:
        """Create a new subscription and return its ID."""
        result = self._transport.post("/subscriptions", json={})
        return result["subscriptionId"]

    def register_items(
        self,
        subscription_id: str,
        element_ids: list[str],
        max_depth: int = 0,
    ) -> dict[str, Any]:
        """Register element IDs on an existing subscription."""
        return self._transport.post(
            f"/subscriptions/{subscription_id}/register",
            json={"elementIds": element_ids, "maxDepth": max_depth},
        )

    def unregister_items(
        self,
        subscription_id: str,
        element_ids: list[str],
    ) -> dict[str, Any]:
        """Unregister element IDs from a subscription."""
        return self._transport.post(
            f"/subscriptions/{subscription_id}/unregister",
            json={"elementIds": element_ids},
        )

    def get_subscriptions(self) -> list[dict[str, Any]]:
        """List all subscriptions on the server."""
        data = self._transport.get("/subscriptions")
        return data.get("subscriptionIds", [])

    def get_subscription(self, subscription_id: str) -> Subscription:
        """Get details for a specific subscription."""
        data = self._transport.get(f"/subscriptions/{subscription_id}")
        return Subscription.from_dict(data)

    def start_stream(self, subscription_id: str) -> None:
        """Start SSE streaming for an existing subscription."""
        if self._sub_manager:
            self._sub_manager.add(subscription_id)

    def stop_stream(self, subscription_id: str) -> None:
        """Stop SSE streaming for a subscription without deleting it."""
        if self._sub_manager:
            self._sub_manager.remove(subscription_id)

    # -- Internal --

    def _handle_value_changes(self, changes: list[ValueChange]) -> None:
        """Dispatch value changes to the on_value_change callback."""
        if self.on_value_change:
            for change in changes:
                try:
                    self.on_value_change(self, change)
                except Exception:
                    logger.exception("Error in on_value_change callback")

    def _handle_error(self, error: Exception) -> None:
        """Dispatch errors to the on_error callback."""
        if self.on_error:
            try:
                self.on_error(self, error)
            except Exception:
                logger.exception("Error in on_error callback")
        else:
            logger.error("Unhandled i3x error: %s", error)
