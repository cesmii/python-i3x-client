# i3x-client

Python client library for I3X CMIP servers.

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

# Connect to a CMIP server
client = i3x.Client("http://localhost:8080")
client.connect()

# Explore the data model
namespaces = client.get_namespaces()
object_types = client.get_object_types()
objects = client.get_objects(type_id="some-type")

# Read values
value = client.get_value("element-id-1")
print(value.data[0].value, value.data[0].quality)

# Read historical values
history = client.get_history("element-id-1", start_time="2026-01-01T00:00:00Z")

# Write values
client.update_value("element-id-1", {"temperature": 72.5})

# Disconnect
client.disconnect()
```

### Context Manager

```python
with i3x.Client("http://localhost:8080") as client:
    namespaces = client.get_namespaces()
```

### Subscriptions

```python
client = i3x.Client("http://localhost:8080")
client.on_value_change = lambda client, change: print(f"{change.element_id}: {change.data}")
client.connect()

# Subscribe to value changes (creates subscription + registers + starts SSE stream)
sub = client.subscribe(["element-id-1", "element-id-2"])

# ... on_value_change fires automatically when values change ...

# Unsubscribe when done
client.unsubscribe(sub)
client.disconnect()
```

### Authentication

```python
client = i3x.Client("http://localhost:8080", auth=("api-key", "secret"))
```

## API Reference

### Client Methods

#### Connection
- `connect()` — Connect to the server
- `disconnect()` — Disconnect and stop all subscriptions
- `is_connected` — Property indicating connection state

#### Callbacks
- `on_connect(client)` — Called after successful connection
- `on_disconnect(client)` — Called after disconnection
- `on_value_change(client, change)` — Called when a subscribed value changes
- `on_subscribe(client, subscription)` — Called after a subscription is created
- `on_error(client, error)` — Called on stream/subscription errors

#### Exploration
- `get_namespaces()` — List all namespaces
- `get_object_types(namespace_uri=None)` — List object types
- `query_object_types(element_ids)` — Query types by ID
- `get_relationship_types(namespace_uri=None)` — List relationship types
- `query_relationship_types(element_ids)` — Query relationship types by ID
- `get_objects(type_id=None, include_metadata=False)` — List object instances
- `get_object(element_id)` — Get a single object
- `list_objects(element_ids)` — Get multiple objects by ID
- `get_related_objects(element_ids, relationship_type)` — Get related objects

#### Values
- `get_value(element_id, max_depth=1)` — Get last known value
- `get_values(element_ids, max_depth=1)` — Get multiple last known values
- `get_history(element_id, start_time=None, end_time=None, max_depth=1)` — Get historical values

#### Updates
- `update_value(element_id, value)` — Update an element's value
- `update_history(element_id, value)` — Update historical values

#### Subscriptions (High-Level)
- `subscribe(element_ids, max_depth=0)` — Create subscription + register + start stream
- `unsubscribe(subscription)` — Stop stream and delete subscription
- `sync_subscription(subscription)` — Poll queued updates

#### Subscriptions (Low-Level)
- `create_subscription()` — Create an empty subscription
- `register_items(subscription_id, element_ids, max_depth=0)` — Register items
- `unregister_items(subscription_id, element_ids)` — Unregister items
- `get_subscriptions()` — List all subscriptions
- `get_subscription(subscription_id)` — Get subscription details
- `start_stream(subscription_id)` — Start SSE for an existing subscription
- `stop_stream(subscription_id)` — Stop SSE without deleting subscription

### Models

All models are frozen dataclasses with `from_dict()` classmethods.

- `Namespace` — `uri`, `display_name`
- `ObjectType` — `element_id`, `display_name`, `namespace_uri`, `schema`
- `RelationshipType` — `element_id`, `display_name`, `namespace_uri`, `reverse_of`
- `ObjectInstance` — `element_id`, `display_name`, `type_id`, `namespace_uri`, `parent_id`, `is_composition`
- `VQT` — `value`, `quality`, `timestamp`
- `LastKnownValue` — `element_id`, `data` (list of VQT), `children`
- `ValueChange` — `element_id`, `data` (list of VQT), `children`
- `Subscription` — `subscription_id`, `created`, `is_streaming`, `queued_updates`, `objects`

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
