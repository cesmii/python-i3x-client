"""Main Client class for interacting with i3X servers."""

from __future__ import annotations

import logging
import uuid
import warnings
from typing import Any, Callable

from . import errors

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
    SyncBatch,
    ValueChange,
)

logger = logging.getLogger("i3x")


def _is_release_version(spec_version: str | None) -> bool:
    """True if specVersion reports i3X 1.0 or later (not an alpha/beta pre-release)."""
    if not spec_version:
        return False
    version = str(spec_version).strip().lower()
    if "alpha" in version or "beta" in version:
        return False
    try:
        major = int(version.split(".")[0])
    except ValueError:
        return False
    return major >= 1


def _item_error(item: dict[str, Any] | None, default_message: str) -> errors.I3XError:
    """Build an error from a failed bulk-result item's responseDetail."""
    detail = (item or {}).get("responseDetail")
    if not isinstance(detail, dict):
        detail = {}
    status = detail.get("status", 404)
    message = detail.get("detail") or detail.get("title") or default_message
    return errors.for_status(status)(message, status_code=status)


class Client:
    """High-level client for i3X servers.

    Usage::

        client = i3x.Client("https://i3x.example.com/v1")
        client.connect()
        namespaces = client.get_namespaces()
        client.disconnect()

    Or as a context manager::

        with i3x.Client("https://i3x.example.com/v1") as client:
            namespaces = client.get_namespaces()

    Note the i3X specification requires servers to expose the API under a
    versioned path, so ``base_url`` normally ends in ``/v1``.

    Authentication: the spec does not mandate a scheme, so pass whatever your
    server requires — ``token`` for ``Authorization: Bearer``, ``auth`` for
    anything httpx accepts (a ``(user, pass)`` tuple for HTTP Basic, or an
    ``httpx.Auth`` instance), or ``headers`` for custom header schemes.

    A ``client_id`` is used to scope subscriptions to this client instance.
    If not provided, a UUID is generated automatically.
    """

    def __init__(
        self,
        base_url: str,
        auth: Any = None,
        timeout: float = 30.0,
        client_id: str | None = None,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        all_headers = dict(headers or {})
        if token:
            all_headers["Authorization"] = f"Bearer {token}"
        self._transport = Transport(base_url, auth=auth, timeout=timeout, headers=all_headers)
        self._client_id = client_id or str(uuid.uuid4())
        self._sub_manager: SubscriptionManager | None = None
        self._server_info: ServerInfo | None = None

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

    @property
    def server_info(self) -> ServerInfo | None:
        """Server info captured during connect(), or None if not connected yet."""
        return self._server_info

    def connect(self) -> None:
        """Connect to the i3X server and detect its protocol version.

        The server's ``GET /info`` response (fetched as the connectivity
        check) is inspected for ``specVersion``:

        - No ``/info`` endpoint: the server is either pre-release (alpha) or
          ``base_url`` is wrong — raises :class:`~i3x.UnsupportedVersionError`.
        - ``specVersion`` earlier than 1.0 (or a pre-release such as
          ``1.0-beta``): emits a :class:`DeprecationWarning`.
        - ``specVersion`` 1.0 or later: connects silently.
        """
        try:
            info_data = self._transport.open()
        except errors.NotFoundError:
            raise errors.UnsupportedVersionError(
                "Cannot connect: this server does not expose a /info endpoint. "
                "Check that base_url includes the version prefix required by the "
                "spec (e.g. https://server.example.com/v1). Pre-release (alpha) "
                "i3X servers are not supported; upgrade the server to i3X 1.0."
            )

        self._server_info = (
            ServerInfo.from_dict(info_data) if isinstance(info_data, dict) else None
        )
        spec_version = self._server_info.spec_version if self._server_info else None
        if not _is_release_version(spec_version):
            warnings.warn(
                f"Connected to an i3X server reporting specVersion "
                f"{spec_version!r}. Pre-release (beta) server support is "
                "deprecated and will be removed in a future version of "
                "i3x-client. Please upgrade your server to i3X 1.0.",
                DeprecationWarning,
                stacklevel=2,
            )

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
        self._server_info = None
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
            raise _item_error(results[0] if results else None, f"Object not found: {element_id}")
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
        """Get the last known value for an element.

        ``max_depth`` controls recursion through HasComponent children:
        1 = no recursion (default), N = recurse N levels, 0 = infinite.
        """
        results = self._transport.post(
            "/objects/value",
            json={"elementIds": [element_id], "maxDepth": max_depth},
        )
        if not results or not results[0].get("success"):
            raise _item_error(results[0] if results else None, f"No value for: {element_id}")
        return CurrentValue.from_dict(element_id, results[0]["result"])

    def get_values(
        self,
        element_ids: list[str],
        max_depth: int = 1,
    ) -> dict[str, CurrentValue]:
        """Get last known values for multiple elements.

        ``max_depth`` controls recursion through HasComponent children:
        1 = no recursion (default), N = recurse N levels, 0 = infinite.
        """
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
        """Get historical values for an element.

        ``max_depth`` controls recursion through HasComponent children:
        1 = no recursion (default), N = recurse N levels, 0 = infinite.
        """
        body: dict[str, Any] = {"elementIds": [element_id], "maxDepth": max_depth}
        if start_time is not None:
            body["startTime"] = start_time
        if end_time is not None:
            body["endTime"] = end_time
        results = self._transport.post("/objects/history", json=body)
        if not results or not results[0].get("success"):
            raise _item_error(results[0] if results else None, f"No history for: {element_id}")
        return HistoricalValue.from_dict(element_id, results[0]["result"])

    # -- Update methods --

    @staticmethod
    def _as_vqt(value: Any, quality: str | None = None, timestamp: str | None = None) -> dict[str, Any]:
        """Normalize a raw value or VQT-shaped dict into a VQT request payload."""
        if isinstance(value, dict) and "value" in value:
            vqt = dict(value)
        else:
            vqt = {"value": value}
        if quality is not None:
            vqt["quality"] = quality
        if timestamp is not None:
            vqt["timestamp"] = timestamp
        return vqt

    @staticmethod
    def _raise_failed_updates(results: Any) -> None:
        if not isinstance(results, list):
            return
        for item in results:
            if isinstance(item, dict) and not item.get("success", True):
                element_id = item.get("elementId", "<unknown>")
                raise _item_error(item, f"Update failed for: {element_id}")

    def update_value(
        self,
        element_id: str,
        value: Any,
        quality: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Update the current value of an element.

        ``value`` may be a raw value (wrapped as ``{"value": ...}``) or a
        VQT-shaped dict. ``quality`` defaults to "Good" and ``timestamp`` to
        server time when omitted.
        """
        results = self._transport.put("/objects/value", json={
            "updates": [{"elementId": element_id, "value": self._as_vqt(value, quality, timestamp)}],
        })
        self._raise_failed_updates(results)

    def update_values(self, updates: dict[str, Any]) -> list[dict[str, Any]]:
        """Update current values for multiple elements in one request.

        ``updates`` maps element IDs to raw values or VQT-shaped dicts.
        Returns the per-element bulk result items; check each item's
        ``success`` flag for partial failures.
        """
        results = self._transport.put("/objects/value", json={
            "updates": [
                {"elementId": eid, "value": self._as_vqt(value)}
                for eid, value in updates.items()
            ],
        })
        return results if isinstance(results, list) else []

    def update_history(self, element_id: str, values: Any) -> None:
        """Update historical values for an element.

        ``values`` is a VQT dict (``{"value": ..., "quality": ..., "timestamp": ...}``,
        timestamp required) or a list of them. Servers that do not support
        history updates raise :class:`~i3x.NotSupportedError`.
        """
        items = values if isinstance(values, list) else [values]
        results = self._transport.put("/objects/history", json={
            "updates": [{"elementId": element_id, "value": v} for v in items],
        })
        self._raise_failed_updates(results)

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

        ``max_depth`` controls recursion through HasComponent children:
        1 = no recursion (default), N = recurse N levels, 0 = infinite.
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
    ) -> list[SyncBatch]:
        """Poll queued update batches for a subscription.

        Pass ``last_sequence_number`` (the highest ``sequence_number`` from
        the previously returned batches) to acknowledge those batches and
        receive only newer updates. Omit on the first call. Pass ``-1`` to
        clear the server-side queue.
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
        return [SyncBatch.from_dict(item) for item in (data or [])]

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
        raise _item_error(
            results[0] if results else None, f"Subscription not found: {subscription_id}"
        )

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
