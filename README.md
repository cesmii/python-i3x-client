# i3x-client

Python client library for i3X servers. Supports the i3X 1.0 Beta specification.

## Installation

```bash
pip install i3x-client
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
import i3x

# Connect to an i3X server
client = i3x.Client("https://my-i3x-server/v1")
client.connect()

# Check server capabilities
info = client.get_info()
print(info.spec_version, info.capabilities)

# Explore the address space
namespaces = client.get_namespaces()
object_types = client.get_object_types()
objects = client.get_objects(root=True)

# Read a value
value = client.get_value("sensor-001")
print(value.value, value.quality, value.timestamp)

# Read historical values
history = client.get_history("sensor-001", start_time="2026-01-01T00:00:00Z")
for vqt in history.values:
    print(vqt.value, vqt.timestamp)

# Write a value
client.update_value("sensor-001", {"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"})

client.disconnect()
```

### Context Manager

```python
with i3x.Client("https://my-i3x-server/v1") as client:
    namespaces = client.get_namespaces()
```

### Subscriptions (SSE Streaming)

```python
client = i3x.Client("https://my-i3x-server/v1")
client.on_value_change = lambda client, change: print(f"{change.element_id}: {change.value} ({change.quality})")
client.connect()

# Creates subscription, registers items, and starts SSE stream in one call
sub = client.subscribe(["sensor-001", "sensor-002"])

# on_value_change fires automatically as values arrive

# Unsubscribe when done
client.unsubscribe(sub)
client.disconnect()
```

### Sync Mode (Polled, Acknowledged Delivery)

```python
sub_id = client.create_subscription()
client.register_items(sub_id, ["sensor-001"])

# First poll — no lastSequenceNumber
updates = client.sync_subscription(sub_id)
last_seq = updates[-1].sequence_number if updates else None

# Subsequent polls — ack previous batch, receive new ones
updates = client.sync_subscription(sub_id, last_sequence_number=last_seq)
for u in updates:
    print(u.sequence_number, u.element_id, u.value)
```

### Authentication

```python
client = i3x.Client("https://my-i3x-server/v1", auth=("api-key", "secret"))
```

### Custom Client ID

A `client_id` is auto-generated as a UUID and used to scope subscriptions. You can provide your own:

```python
client = i3x.Client("https://my-i3x-server/v1", client_id="my-app-instance-1")
```

## API Reference

### Client

```python
i3x.Client(base_url, auth=None, timeout=30.0, client_id=None)
```

#### Connection
- `connect()` — Connect to the server (verifies via `GET /info`)
- `disconnect()` — Disconnect and stop all subscriptions
- `is_connected` — Connection state
- `client_id` — The client ID used to scope subscriptions

#### Server Info
- `get_info()` → `ServerInfo` — Server version and capabilities

#### Exploration
- `get_namespaces()` → `list[Namespace]`
- `get_object_types(namespace_uri=None)` → `list[ObjectType]`
- `query_object_types(element_ids)` → `list[ObjectType]`
- `get_relationship_types(namespace_uri=None)` → `list[RelationshipType]`
- `query_relationship_types(element_ids)` → `list[RelationshipType]`
- `get_objects(type_element_id=None, include_metadata=False, root=None)` → `list[ObjectInstance]`
- `get_object(element_id, include_metadata=False)` → `ObjectInstance`
- `list_objects(element_ids, include_metadata=False)` → `list[ObjectInstance]`
- `get_related_objects(element_ids, relationship_type=None, include_metadata=False)` → `list[RelatedObject]`

#### Values
- `get_value(element_id, max_depth=1)` → `CurrentValue`
- `get_values(element_ids, max_depth=1)` → `dict[str, CurrentValue]`
- `get_history(element_id, start_time=None, end_time=None, max_depth=1)` → `HistoricalValue`

#### Updates
- `update_value(element_id, value)` — Write a value in VQT format
- `update_history(element_id, value)` — Write historical values

#### Subscriptions (High-Level)
- `subscribe(element_ids, max_depth=1, display_name=None)` → `Subscription` — Create + register + stream
- `unsubscribe(subscription)` — Stop stream and delete subscription
- `sync_subscription(subscription, last_sequence_number=None)` → `list[SyncUpdate]`

#### Subscriptions (Low-Level)
- `create_subscription(display_name=None)` → `str` — Returns subscription ID
- `register_items(subscription_id, element_ids, max_depth=1)`
- `unregister_items(subscription_id, element_ids)`
- `get_subscription(subscription_id)` → `Subscription`
- `list_subscriptions(subscription_ids)` → `list[Subscription]`
- `start_stream(subscription_id)` — Start SSE for an existing subscription
- `stop_stream(subscription_id)` — Stop SSE without deleting subscription

#### Callbacks
- `on_connect(client)`
- `on_disconnect(client)`
- `on_value_change(client, change: ValueChange)`
- `on_subscribe(client, subscription: Subscription)`
- `on_error(client, error: Exception)`

### Models

All models are frozen dataclasses.

| Model | Fields |
|-------|--------|
| `ServerInfo` | `spec_version`, `server_version`, `server_name`, `capabilities` |
| `Namespace` | `uri`, `display_name` |
| `ObjectType` | `element_id`, `display_name`, `namespace_uri`, `source_type_id`, `version`, `schema`, `related` |
| `RelationshipType` | `element_id`, `display_name`, `namespace_uri`, `relationship_id`, `reverse_of` |
| `ObjectInstance` | `element_id`, `display_name`, `type_element_id`, `parent_id`, `is_composition`, `is_extended`, `metadata` |
| `ObjectInstanceMetadata` | `type_namespace_uri`, `source_type_id`, `description`, `relationships`, `extended_attributes`, `system` |
| `RelatedObject` | `source_relationship`, `object` |
| `VQT` | `value`, `quality`, `timestamp` |
| `CurrentValue` | `element_id`, `is_composition`, `value`, `quality`, `timestamp`, `components` |
| `HistoricalValue` | `element_id`, `is_composition`, `values` (list of VQT) |
| `ValueChange` | `element_id`, `value`, `quality`, `timestamp` |
| `SyncUpdate` | `sequence_number`, `element_id`, `value`, `quality`, `timestamp` |
| `Subscription` | `subscription_id`, `client_id`, `display_name`, `monitored_objects` |

### Errors

All errors inherit from `i3x.I3XError`:

- `ConnectionError` — Failed to connect
- `AuthenticationError` — Auth rejected (401/403)
- `NotFoundError` — Resource not found (404)
- `ServerError` — Server error (5xx)
- `TimeoutError` — Request timed out
- `SubscriptionError` — Subscription operation failed
- `StreamError` — SSE streaming error

## License

MIT
