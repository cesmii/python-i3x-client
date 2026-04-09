"""Main Client class for interacting with i3X servers."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable
from urllib.parse import quote

from ._subscription import SubscriptionManager
from ._transport import Transport
from .models import (
    CurrentValue,
    HistoricalValue,
    Namespace,
    ObjectInstance,
    ObjectType,
    RelatedObject,
    RelationshipType,
    ServerInfo,
    Subscription,
    SyncUpdate,
    ValueChange,
    VQT,
)

logger = logging.getLogger("i3x")


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

    A ``client_id`` is used to scope subscriptions to this client instance.
    If not provided, a UUID is generated automatically.
    """

    def __init__(
        self,
        base_url: str,
        auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
        client_id: str | None = None,
    ):
        self._transport = Transport(base_url, auth=auth, timeout=timeout)
        self._client_id = client_id or str(uuid.uuid4())
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

    @property
    def client_id(self) -> str:
        return self._client_id

    def connect(self) -> None:
        """Connect to the i3X server."""
        self._transport.open()
        self._sub_manager = SubscriptionManager(
            transport=self._transport,
            client_id=self._client_id,
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

    # -- Server info --

    def get_info(self) -> ServerInfo:
        """Get server version and capabilities."""
        data = self._transport.get("/info")
        return ServerInfo.from_dict(data)

    # -- Exploratory methods --

    def get_namespaces(self) -> list[Namespace]:
        """Get all namespaces from the server."""
        data = self._transport.get("/namespaces")
        return [Namespace.from_dict(item) for item in (data or [])]

    def get_object_types(self, namespace_uri: str | None = None) -> list[ObjectType]:
        """Get all object types, optionally filtered by namespace."""
        params = {}
        if namespace_uri is not None:
            params["namespaceUri"] = namespace_uri
        data = self._transport.get("/objecttypes", params=params or None)
        return [ObjectType.from_dict(item) for item in (data or [])]

    def query_object_types(self, element_ids: list[str]) -> list[ObjectType]:
        """Get one or more object types by element ID."""
        results = self._transport.post("/objecttypes/query", json={"elementIds": element_ids})
        return [ObjectType.from_dict(item["result"]) for item in (results or []) if item.get("success")]

    def get_relationship_types(self, namespace_uri: str | None = None) -> list[RelationshipType]:
        """Get all relationship types, optionally filtered by namespace."""
        params = {}
        if namespace_uri is not None:
            params["namespaceUri"] = namespace_uri
        data = self._transport.get("/relationshiptypes", params=params or None)
        return [RelationshipType.from_dict(item) for item in (data or [])]

    def query_relationship_types(self, element_ids: list[str]) -> list[RelationshipType]:
        """Get one or more relationship types by element ID."""
        results = self._transport.post("/relationshiptypes/query", json={"elementIds": element_ids})
        return [RelationshipType.from_dict(item["result"]) for item in (results or []) if item.get("success")]

    def get_objects(
        self,
        type_element_id: str | None = None,
        include_metadata: bool = False,
        root: bool | None = None,
    ) -> list[ObjectInstance]:
        """Get all object instances, optionally filtered by type or returning only root objects."""
        params: dict[str, Any] = {}
        if type_element_id is not None:
            params["typeElementId"] = type_element_id
        if include_metadata:
            params["includeMetadata"] = "true"
        if root is not None:
            params["root"] = "true" if root else "false"
        data = self._transport.get("/objects", params=params or None)
        return [ObjectInstance.from_dict(item) for item in (data or [])]

    def get_object(self, element_id: str, include_metadata: bool = False) -> ObjectInstance:
        """Get a single object instance by element ID."""
        results = self._transport.post(
            "/objects/list",
            json={"elementIds": [element_id], "includeMetadata": include_metadata},
        )
        if not results or not results[0].get("success"):
            from . import errors
            raise errors.NotFoundError(f"Object not found: {element_id}", status_code=404)
        return ObjectInstance.from_dict(results[0]["result"])

    def list_objects(
        self,
        element_ids: list[str],
        include_metadata: bool = False,
    ) -> list[ObjectInstance]:
        """Get multiple object instances by their element IDs."""
        results = self._transport.post(
            "/objects/list",
            json={"elementIds": element_ids, "includeMetadata": include_metadata},
        )
        return [ObjectInstance.from_dict(item["result"]) for item in (results or []) if item.get("success")]

    def get_related_objects(
        self,
        element_ids: list[str],
        relationship_type: str | None = None,
        include_metadata: bool = False,
    ) -> list[RelatedObject]:
        """Get objects related to the given elements, optionally filtered by relationship type."""
        body: dict[str, Any] = {"elementIds": element_ids, "includeMetadata": include_metadata}
        if relationship_type is not None:
            body["relationshipType"] = relationship_type
        results = self._transport.post("/objects/related", json=body)
        related: list[RelatedObject] = []
        for item in (results or []):
            if item.get("success"):
                for rel in (item.get("result") or []):
                    related.append(RelatedObject.from_dict(rel))
        return related

    # -- Value methods --

    def get_value(self, element_id: str, max_depth: int = 1) -> CurrentValue:
        """Get the last known value for an element."""
        results = self._transport.post(
            "/objects/value",
            json={"elementIds": [element_id], "maxDepth": max_depth},
        )
        if not results or not results[0].get("success"):
            from . import errors
            raise errors.NotFoundError(f"No value for: {element_id}", status_code=404)
        return CurrentValue.from_dict(element_id, results[0]["result"])

    def get_values(
        self,
        element_ids: list[str],
        max_depth: int = 1,
    ) -> dict[str, CurrentValue]:
        """Get last known values for multiple elements."""
        results = self._transport.post(
            "/objects/value",
            json={"elementIds": element_ids, "maxDepth": max_depth},
        )
        return {
            item["elementId"]: CurrentValue.from_dict(item["elementId"], item["result"])
            for item in (results or [])
            if item.get("success")
        }

    def get_history(
        self,
        element_id: str,
        start_time: str | None = None,
        end_time: str | None = None,
        max_depth: int = 1,
    ) -> HistoricalValue:
        """Get historical values for an element."""
        body: dict[str, Any] = {"elementIds": [element_id], "maxDepth": max_depth}
        if start_time is not None:
            body["startTime"] = start_time
        if end_time is not None:
            body["endTime"] = end_time
        results = self._transport.post("/objects/history", json=body)
        if not results or not results[0].get("success"):
            from . import errors
            raise errors.NotFoundError(f"No history for: {element_id}", status_code=404)
        return HistoricalValue.from_dict(element_id, results[0]["result"])

    # -- Update methods --

    def update_value(self, element_id: str, value: Any) -> None:
        """Update the current value of an element."""
        encoded_id = quote(element_id, safe="")
        self._transport.put(f"/objects/{encoded_id}/value", json=value)

    def update_history(self, element_id: str, value: Any) -> None:
        """Update historical values for an element."""
        encoded_id = quote(element_id, safe="")
        self._transport.put(f"/objects/{encoded_id}/history", json=value)

    # -- Subscription methods (high-level) --

    def subscribe(
        self,
        element_ids: list[str],
        max_depth: int = 1,
        display_name: str | None = None,
    ) -> Subscription:
        """Create a subscription, register items, and start SSE streaming.

        Combines:
        1. Create a subscription (POST /subscriptions)
        2. Register monitored items (POST /subscriptions/register)
        3. Start the SSE background stream
        """
        result = self._transport.post("/subscriptions", json={
            "clientId": self._client_id,
            "displayName": display_name,
        })
        subscription_id = result["subscriptionId"]

        self._transport.post("/subscriptions/register", json={
            "clientId": self._client_id,
            "subscriptionId": subscription_id,
            "elementIds": element_ids,
            "maxDepth": max_depth,
        })

        if self._sub_manager:
            self._sub_manager.add(subscription_id)

        sub = Subscription(
            subscription_id=subscription_id,
            client_id=self._client_id,
            display_name=result.get("displayName"),
            monitored_objects=[{"elementId": eid, "maxDepth": max_depth} for eid in element_ids],
        )

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
        self._transport.post("/subscriptions/delete", json={
            "clientId": self._client_id,
            "subscriptionIds": [sub_id],
        })

    def sync_subscription(
        self,
        subscription: Subscription | str,
        last_sequence_number: int | None = None,
    ) -> list[SyncUpdate]:
        """Poll queued updates for a subscription.

        Pass ``last_sequence_number`` (the highest sequenceNumber from the
        previous call) to acknowledge that batch and receive only newer updates.
        Omit on the first call.
        """
        sub_id = (
            subscription.subscription_id
            if isinstance(subscription, Subscription)
            else subscription
        )
        body: dict[str, Any] = {
            "clientId": self._client_id,
            "subscriptionId": sub_id,
        }
        if last_sequence_number is not None:
            body["lastSequenceNumber"] = last_sequence_number
        data = self._transport.post("/subscriptions/sync", json=body)
        return [SyncUpdate.from_dict(item) for item in (data or [])]

    # -- Subscription methods (low-level) --

    def create_subscription(self, display_name: str | None = None) -> str:
        """Create a new subscription and return its ID."""
        result = self._transport.post("/subscriptions", json={
            "clientId": self._client_id,
            "displayName": display_name,
        })
        return result["subscriptionId"]

    def register_items(
        self,
        subscription_id: str,
        element_ids: list[str],
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Register element IDs on an existing subscription."""
        return self._transport.post("/subscriptions/register", json={
            "clientId": self._client_id,
            "subscriptionId": subscription_id,
            "elementIds": element_ids,
            "maxDepth": max_depth,
        })

    def unregister_items(
        self,
        subscription_id: str,
        element_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Unregister element IDs from a subscription."""
        return self._transport.post("/subscriptions/unregister", json={
            "clientId": self._client_id,
            "subscriptionId": subscription_id,
            "elementIds": element_ids,
        })

    def get_subscription(self, subscription_id: str) -> Subscription:
        """Get details for a specific subscription."""
        results = self._transport.post("/subscriptions/list", json={
            "clientId": self._client_id,
            "subscriptionIds": [subscription_id],
        })
        if results and results[0].get("success"):
            return Subscription.from_dict(results[0]["result"])
        from . import errors
        raise errors.NotFoundError(f"Subscription not found: {subscription_id}", status_code=404)

    def list_subscriptions(self, subscription_ids: list[str]) -> list[Subscription]:
        """Get details for one or more subscriptions by ID."""
        results = self._transport.post("/subscriptions/list", json={
            "clientId": self._client_id,
            "subscriptionIds": subscription_ids,
        })
        return [Subscription.from_dict(item["result"]) for item in (results or []) if item.get("success")]

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
        if self.on_value_change:
            for change in changes:
                try:
                    self.on_value_change(self, change)
                except Exception:
                    logger.exception("Error in on_value_change callback")

    def _handle_error(self, error: Exception) -> None:
        if self.on_error:
            try:
                self.on_error(self, error)
            except Exception:
                logger.exception("Error in on_error callback")
        else:
            logger.error("Unhandled i3x error: %s", error)
