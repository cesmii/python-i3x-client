"""i3x - Python client library for I3X servers."""

__version__ = "0.1.6"

from .client import Client
from .errors import (
    AuthenticationError,
    ConnectionError,
    I3XError,
    NotFoundError,
    ServerError,
    StreamError,
    SubscriptionError,
    TimeoutError,
)
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

__all__ = [
    "__version__",
    "Client",
    # Errors
    "I3XError",
    "ConnectionError",
    "AuthenticationError",
    "NotFoundError",
    "ServerError",
    "TimeoutError",
    "SubscriptionError",
    "StreamError",
    # Models
    "Namespace",
    "ObjectType",
    "RelationshipType",
    "ObjectInstance",
    "LastKnownValue",
    "ValueChange",
    "Subscription",
    "VQT",
]
