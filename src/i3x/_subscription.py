"""Internal subscription lifecycle tracker."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from .models import Subscription, ValueChange
from ._sse import SSEStream

if TYPE_CHECKING:
    from ._transport import Transport

logger = logging.getLogger("i3x.subscription")


class SubscriptionManager:
    """Tracks active subscriptions and their SSE streams."""

    def __init__(
        self,
        transport: Transport,
        on_event: Callable[[list[ValueChange]], None],
        on_error: Callable[[Exception], None],
    ):
        self._transport = transport
        self._on_event = on_event
        self._on_error = on_error
        self._streams: dict[str, SSEStream] = {}

    def add(self, subscription_id: str) -> None:
        """Start an SSE stream for a subscription."""
        if subscription_id in self._streams:
            return
        stream = SSEStream(
            transport=self._transport,
            subscription_id=subscription_id,
            on_event=self._on_event,
            on_error=self._on_error,
        )
        self._streams[subscription_id] = stream
        stream.start()

    def remove(self, subscription_id: str) -> None:
        """Stop and remove the SSE stream for a subscription."""
        stream = self._streams.pop(subscription_id, None)
        if stream is not None:
            stream.stop()

    def stop_all(self) -> None:
        """Stop all active SSE streams."""
        for stream in self._streams.values():
            stream.stop()
        self._streams.clear()

    def is_streaming(self, subscription_id: str) -> bool:
        stream = self._streams.get(subscription_id)
        return stream is not None and stream.is_running
