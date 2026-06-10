"""Internal SSE stream reader running in a background daemon thread."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING, Any, Callable

import httpx
from httpx_sse import EventSource

from . import errors
from .models import ValueChange

if TYPE_CHECKING:
    from ._transport import Transport

logger = logging.getLogger("i3x.sse")

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


class SSEStream:
    """Manages an SSE connection to a subscription stream in a background thread.

    The stream endpoint is POST /subscriptions/stream, which accepts
    {clientId, subscriptionId} and returns an SSE response. If the stream
    drops, the thread reconnects with exponential backoff until stop() is
    called or the server reports a non-retryable error (subscription gone,
    auth rejected, streaming unsupported).
    """

    def __init__(
        self,
        transport: Transport,
        client_id: str | None,
        subscription_id: str,
        on_event: Callable[[list[ValueChange]], None],
        on_error: Callable[[Exception], None],
    ):
        self._transport = transport
        self._client_id = client_id
        self._subscription_id = subscription_id
        self._on_event = on_event
        self._on_error = on_error
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._response: httpx.Response | None = None
        self._dispatched_events = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the background SSE listener thread."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"i3x-sse-{self._subscription_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        # Close the in-flight response to unblock a thread waiting on the
        # next SSE chunk (the read timeout is disabled for streams).
        response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _run(self) -> None:
        """Background thread entry point: connect, read, reconnect on failure."""
        body: dict[str, Any] = {"subscriptionId": self._subscription_id}
        if self._client_id is not None:
            body["clientId"] = self._client_id
        backoff = _INITIAL_BACKOFF

        while not self._stop_event.is_set():
            try:
                response = self._transport.stream_post("/subscriptions/stream", json=body)
            except (
                errors.NotFoundError,
                errors.AuthenticationError,
                errors.NotSupportedError,
            ) as exc:
                self._on_error(errors.StreamError(f"Cannot open SSE stream: {exc}"))
                return
            except Exception as exc:
                if self._stop_event.is_set():
                    return
                self._on_error(errors.StreamError(f"Failed to open SSE stream: {exc}"))
                if self._stop_event.wait(backoff):
                    return
                backoff = min(backoff * 2, _MAX_BACKOFF)
                continue

            self._response = response
            self._dispatched_events = False
            try:
                self._read_events(response)
                return  # Server ended the stream cleanly.
            except Exception as exc:
                if self._stop_event.is_set():
                    return
                self._on_error(errors.StreamError(f"SSE stream error: {exc}"))
            finally:
                self._response = None
                response.close()

            if self._dispatched_events:
                backoff = _INITIAL_BACKOFF
            if self._stop_event.wait(backoff):
                return
            backoff = min(backoff * 2, _MAX_BACKOFF)

    def _read_events(self, response: httpx.Response) -> None:
        """Read SSE events from the response stream until it ends."""
        for sse in EventSource(response).iter_sse():
            if self._stop_event.is_set():
                return
            self._process_data(sse.data)

    def _process_data(self, data_str: str) -> None:
        """Parse and dispatch a single SSE event payload.

        The stream sends arrays of value change objects:
          data: [{"elementId": "...", "value": ..., "quality": "...", "timestamp": "..."}]
        """
        if not data_str:
            return
        try:
            parsed = json.loads(data_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse SSE event data: %s", data_str)
            return

        if isinstance(parsed, list):
            changes = [ValueChange.from_dict(item) for item in parsed if isinstance(item, dict)]
            if changes:
                self._dispatched_events = True
                self._on_event(changes)
        elif isinstance(parsed, dict):
            # Single-item event
            self._dispatched_events = True
            self._on_event([ValueChange.from_dict(parsed)])
