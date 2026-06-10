"""Exception hierarchy for the i3x client library."""

from __future__ import annotations


class I3XError(Exception):
    """Base exception for all i3x errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ConnectionError(I3XError):
    """Failed to connect to the i3X server."""


class AuthenticationError(I3XError):
    """Authentication credentials were rejected."""


class NotFoundError(I3XError):
    """The requested resource was not found."""


class ServerError(I3XError):
    """The server returned an internal error."""


class TimeoutError(I3XError):
    """The request timed out."""


class NotSupportedError(I3XError):
    """The server does not support this optional feature (HTTP 501)."""


class SubscriptionError(I3XError):
    """Error related to subscription operations."""


class StreamError(I3XError):
    """Error related to SSE streaming."""


class UnsupportedVersionError(I3XError):
    """The server is running an unsupported version of the i3X specification."""


_STATUS_MAP: dict[int, type[I3XError]] = {
    401: AuthenticationError,
    403: AuthenticationError,
    404: NotFoundError,
    501: NotSupportedError,
}


def for_status(status_code: int) -> type[I3XError]:
    """Return the error class for an HTTP status code."""
    error_cls = _STATUS_MAP.get(status_code)
    if error_cls is not None:
        return error_cls
    if status_code >= 500:
        return ServerError
    return I3XError
