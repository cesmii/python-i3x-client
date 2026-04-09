"""Internal SSE stream reader running in a background daemon thread."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING, Any, Callable

import httpx

from . import errors
from .models import ValueChange

if TYPE_CHECKING:
    from ._transport import Transport

logger = logging.getLogger("i3x.sse")


class SSEStream:
    """Manages an SSE connection to a subscription stream in a background thread.

    The stream endpoint is POST /subscriptions/stream, which accepts
    {clientId, subscriptionId} and returns an SSE response.
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
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _run(self) -> None:
        """Background thread entry point."""
        body: dict[str, Any] = {"subscriptionId": self._subscription_id}
        if self._client_id is not None:
            body["clientId"] = self._client_id
        try:
            response = self._transport.stream_post("/subscriptions/stream", json=body)
        except Exception as exc:
            self._on_error(errors.StreamError(f"Failed to open SSE stream: {exc}"))
            return

        try:
            self._read_events(response)
        except Exception as exc:
            if not self._stop_event.is_set():
                self._on_error(errors.StreamError(f"SSE stream error: {exc}"))
        finally:
            response.close()

    def _read_events(self, response: httpx.Response) -> None:
        """Read SSE events from the response stream."""
        buffer = ""
        for chunk in response.iter_text():
            if self._stop_event.is_set():
                return
            buffer += chunk
            while "\n\n" in buffer:
                event_text, buffer = buffer.split("\n\n", 1)
                self._process_event_text(event_text)

    def _process_event_text(self, event_text: str) -> None:
        """Parse and dispatch a single SSE event.

        The stream sends arrays of value change objects:
          data: [{"elementId": "...", "value": ..., "quality": "...", "timestamp": "..."}]
        """
        data_lines = []
        for line in event_text.split("\n"):
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())

        if not data_lines:
            return

        data_str = "\n".join(data_lines)
        try:
            parsed = json.loads(data_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse SSE event data: %s", data_str)
            return

        if isinstance(parsed, list):
            changes = [ValueChange.from_dict(item) for item in parsed if isinstance(item, dict)]
            if changes:
                self._on_event(changes)
        elif isinstance(parsed, dict):
            # Single-item event
            change = ValueChange.from_dict(parsed)
            self._on_event([change])
