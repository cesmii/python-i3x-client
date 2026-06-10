"""i3x - Python client library for i3X servers."""

__version__ = "0.6.0"

from .client import Client
from .errors import (
    AuthenticationError,
    ConnectionError,
    I3XError,
    NotFoundError,
    NotSupportedError,
    ServerError,
    StreamError,
    SubscriptionError,
    TimeoutError,
    UnsupportedVersionError,
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
    SyncBatch,
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
    "NotSupportedError",
    "ServerError",
    "TimeoutError",
    "SubscriptionError",
    "StreamError",
    "UnsupportedVersionError",
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
    "SyncBatch",
    "Subscription",
]
