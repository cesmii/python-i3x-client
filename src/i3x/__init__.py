"""i3x - Python client library for i3X servers."""

__version__ = "0.5.1"

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
    CurrentValue,
    HistoricalValue,
    Namespace,
    ObjectInstance,
    ObjectInstanceMetadata,
    ObjectType,
    RelatedObject,
    RelationshipType,
    ServerInfo,
    Subscription,
    SyncUpdate,
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
    "ServerInfo",
    "Namespace",
    "ObjectType",
    "RelationshipType",
    "ObjectInstance",
    "ObjectInstanceMetadata",
    "RelatedObject",
    "VQT",
    "CurrentValue",
    "HistoricalValue",
    "ValueChange",
    "SyncUpdate",
    "Subscription",
]
