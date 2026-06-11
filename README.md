# i3x-client

Python client library for i3X servers, provided by CESMII. Supports the i3X 1.0 release specification.

Connecting to pre-release servers is deprecated: servers without a `GET /info`
endpoint (alpha) are rejected with `UnsupportedVersionError`, and servers
reporting a pre-1.0 `specVersion` (beta) emit a `DeprecationWarning`.

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
client = i3x.Client("https://api.i3x.dev/v1")   # Replace with your server
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

# Write a value (quality defaults to "Good", timestamp to server time)
client.update_value("sensor-001", 72.5)
client.update_value("sensor-001", {"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"})

# Write several values in one request
client.update_values({"sensor-001": 72.5, "sensor-002": 18.3})

client.disconnect()
```

### Context Manager

```python
with i3x.Client("https://api.i3x.dev/v1") as client:
    namespaces = client.get_namespaces()
```

### Subscriptions (SSE Streaming)

```python
client = i3x.Client("https://api.i3x.dev/v1")
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
batches = client.sync_subscription(sub_id)
last_seq = batches[-1].sequence_number if batches else None

# Subsequent polls — ack previous batches, receive new ones
batches = client.sync_subscription(sub_id, last_sequence_number=last_seq)
for batch in batches:
    for u in batch.updates:
        print(batch.sequence_number, u.element_id, u.value)
```

### Hierarchy Traversal

`get_objects()` loads the full address space in a single call. Every object carries a `parent_id` that encodes the complete tree — both the organizational hierarchy (`HasChildren`) and the internal composition of each node (`HasComponent`). Group by `parent_id` to reconstruct the tree in memory without additional round-trips:

```python
client = i3x.Client("https://api.i3x.dev/v1")
client.connect()

objects = client.get_objects()

children_of = {}
for obj in objects:
    children_of.setdefault(obj.parent_id, []).append(obj)

def print_subtree(parent_id=None, depth=0):
    for obj in children_of.get(parent_id, []):
        print("  " * depth + f"{obj.display_name}  [{obj.type_element_id}]")
        print_subtree(obj.element_id, depth + 1)

print_subtree()   # parent_id=None → roots
client.disconnect()
```

To start from a known root and walk only one branch using relationship queries:

```python
def walk_components(element_id, depth=0):
    obj = client.get_object(element_id)
    print("  " * depth + obj.display_name)
    for rel in client.get_related_objects([element_id], relationship_type="HasComponent"):
        walk_components(rel.object.element_id, depth + 1)

walk_components("pump-101")
```

### Graph Traversal

Cross-branch relationships like `SuppliesTo` and `Monitors` connect objects that are unrelated in the hierarchy, making the address space a directed graph. Follow edges with `get_related_objects` and a specific relationship type:

```python
client = i3x.Client("https://api.i3x.dev/v1")
client.connect()

# Process flow: what does pump-101 feed into?
for rel in client.get_related_objects(["pump-101"], relationship_type="SuppliesTo"):
    print(f"pump-101 → {rel.object.display_name}")
# pump-101 → tank-201

# Instrumentation: which sensors cover tank-201?
for rel in client.get_related_objects(["tank-201"], relationship_type="MonitoredBy"):
    print(f"{rel.object.display_name} monitors tank-201")
# TempSensor-101 monitors tank-201

client.disconnect()
```

For multi-hop traversal, BFS over arbitrary relationship types:

```python
from collections import deque

def bfs(start_id, rel_types):
    """Yield every object reachable from start_id via rel_types (breadth-first)."""
    seen, queue = set(), deque([start_id])
    while queue:
        eid = queue.popleft()
        if eid in seen:
            continue
        seen.add(eid)
        yield client.get_object(eid)
        for rel_type in rel_types:
            for rel in client.get_related_objects([eid], relationship_type=rel_type):
                queue.append(rel.object.element_id)

# Trace everything downstream of pump-101 through the process chain
for obj in bfs("pump-101", ["SuppliesTo"]):
    print(obj.display_name)
# pump-101
# tank-201

# Walk instrumentation outward from pump-101: what does it supply, and what monitors those targets?
for obj in bfs("pump-101", ["SuppliesTo", "MonitoredBy"]):
    print(obj.display_name)
# pump-101
# tank-201
# TempSensor-101
```

### Authentication

The i3X spec requires authentication, but does not mandate an authentication scheme, so pass whatever your
server requires:

```python
# Bearer token (Authorization: Bearer <token>)
client = i3x.Client("https://my-i3x-server/v1", token="my-token")

# HTTP Basic (or any httpx auth object)
client = i3x.Client("https://my-i3x-server/v1", auth=("user", "password"))

# Custom header scheme
client = i3x.Client("https://my-i3x-server/v1", headers={"X-API-Key": "my-key"})
```

### TLS / Self-Signed Certificates

By default the client verifies the server's TLS certificate. Development and
test servers often use a self-signed certificate; pass `verify` to handle that:

```python
# Skip certificate verification entirely (dev/test only)
client = i3x.Client("https://localhost:8443/v1", verify=False)

# Or trust a custom CA bundle instead of disabling verification
client = i3x.Client("https://my-dev-server/v1", verify="/path/to/ca.pem")
```

Leave `verify=True` (the default) in production. If verification fails, the
client raises `ConnectionError` with guidance on using `verify`.

> **Note:** If `http://` URLs are used, and redirected to `https://` by the server — the
> client follows redirects.

### Custom Client ID

A `client_id` is auto-generated as a UUID and used to scope subscriptions. You can provide your own:

```python
client = i3x.Client("https://my-i3x-server/v1", client_id="my-app-instance-1")
```

## API Reference

### Client

```python
i3x.Client(base_url, auth=None, timeout=30.0, client_id=None, token=None, headers=None, verify=True)
```

`base_url` must include the version prefix required by the spec, e.g.
`https://server.example.com/v1`.

#### Connection
- `connect()` — Connect to the server (verifies via `GET /info` and checks `specVersion`)
- `disconnect()` — Disconnect and stop all subscriptions
- `is_connected` — Connection state
- `client_id` — The client ID used to scope subscriptions
- `server_info` — `ServerInfo` captured during `connect()`

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

`max_depth` controls recursion through HasComponent children: `1` = no
recursion (default), `N` = recurse N levels, `0` = infinite.

#### Updates
- `update_value(element_id, value, quality=None, timestamp=None)` — Write a value (raw or VQT dict)
- `update_values(updates)` — Write values for multiple elements (`{element_id: value}`)
- `update_history(element_id, values)` — Write historical VQTs (timestamp required); raises `NotSupportedError` if the server doesn't support it

#### Subscriptions (High-Level)
- `subscribe(element_ids, max_depth=1, display_name=None)` → `Subscription` — Create + register + stream
- `unsubscribe(subscription)` — Stop stream and delete subscription
- `sync_subscription(subscription, last_sequence_number=None)` → `list[SyncBatch]` — pass `-1` to clear the queue

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
| `ObjectInstanceMetadata` | `type_namespace_uri`, `source_type_id`, `description`, `relationships`, `schema_extensions`, `system` |
| `RelatedObject` | `source_relationship`, `object` |
| `VQT` | `value`, `quality`, `timestamp` |
| `CurrentValue` | `element_id`, `is_composition`, `value`, `quality`, `timestamp`, `components` |
| `HistoricalValue` | `element_id`, `is_composition`, `values` (list of VQT) |
| `ValueChange` | `element_id`, `value`, `quality`, `timestamp` |
| `SyncBatch` | `sequence_number`, `updates` (list of ValueChange) |
| `Subscription` | `subscription_id`, `client_id`, `display_name`, `monitored_objects` |

### Errors

All errors inherit from `i3x.I3XError`:

- `ConnectionError` — Failed to connect (including TLS/certificate failures)
- `AuthenticationError` — Auth rejected (401/403)
- `NotFoundError` — Resource not found (404)
- `NotSupportedError` — Optional feature not supported by the server (501)
- `ServerError` — Server error (5xx)
- `TimeoutError` — Request timed out
- `SubscriptionError` — Subscription operation failed
- `StreamError` — SSE streaming error
- `UnsupportedVersionError` — `GET /info` returned 404: a pre-release (alpha) server, or a wrong `base_url`
- `InvalidServerResponseError` — `GET /info` responded but not with a valid i3X document (e.g. `base_url` points at a web page, login portal, or non-i3X service)

## License

MIT
