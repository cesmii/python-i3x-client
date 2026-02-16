"""Exception hierarchy for the i3x client library."""


class I3XError(Exception):
    """Base exception for all i3x errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ConnectionError(I3XError):
    """Failed to connect to the CMIP server."""


class AuthenticationError(I3XError):
    """Authentication credentials were rejected."""


class NotFoundError(I3XError):
    """The requested resource was not found."""


class ServerError(I3XError):
    """The server returned an internal error."""


class TimeoutError(I3XError):
    """The request timed out."""


class SubscriptionError(I3XError):
    """Error related to subscription operations."""


class StreamError(I3XError):
    """Error related to SSE streaming."""
