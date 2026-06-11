import i3x
from collections import deque

BASE_URL = "https://api.i3x.dev/v1"

# ── Connect ──────────────────────────────────────────────────────────────────

client = i3x.Client(BASE_URL)
client.connect()
print(f"Connected: specVersion={client.server_info.spec_version}  serverVersion={client.server_info.server_version}")

# ── Basic exploration ─────────────────────────────────────────────────────────

info = client.get_info()
print(f"\nCapabilities: {info.capabilities}")

namespaces = client.get_namespaces()
print(f"\nNamespaces ({len(namespaces)}):")
for ns in namespaces:
    print(f"  {ns.uri}  ({ns.display_name})")

object_types = client.get_object_types()
print(f"\nObject types ({len(object_types)}):")
for t in object_types:
    print(f"  {t.element_id}  ({t.display_name})")

# ── Values ────────────────────────────────────────────────────────────────────

print("\nCurrent value (sensor-001):")
value = client.get_value("sensor-001")
print(f"  {value.value}  quality={value.quality}  ts={value.timestamp}")

print("\nHistorical values (sensor-001, from 2026-01-01):")
history = client.get_history("sensor-001", start_time="2026-01-01T00:00:00Z")
for vqt in history.values[:3]:
    print(f"  {vqt.value}  {vqt.timestamp}")
if len(history.values) > 3:
    print(f"  ... ({len(history.values)} total)")

print("\nWriting values ...")
client.update_value("sensor-001", 72.5)
client.update_value("sensor-001", {"value": 72.5, "quality": "Good", "timestamp": "2026-01-01T00:00:00Z"})
client.update_values({"sensor-001": 72.5, "sensor-002": 18.3})
print("  OK")

# ── Hierarchy traversal ───────────────────────────────────────────────────────

print("\nHierarchy (all objects, built from parent_id):")
objects = client.get_objects()
children_of = {}
for obj in objects:
    children_of.setdefault(obj.parent_id, []).append(obj)

def print_subtree(parent_id=None, depth=0):
    for obj in children_of.get(parent_id, []):
        print("  " * (depth + 1) + f"{obj.display_name}  [{obj.type_element_id}]")
        print_subtree(obj.element_id, depth + 1)

print_subtree()

print("\nComposition of pump-101 (via HasComponent):")
def walk_components(element_id, depth=0):
    obj = client.get_object(element_id)
    print("  " * (depth + 1) + obj.display_name)
    for rel in client.get_related_objects([element_id], relationship_type="HasComponent"):
        walk_components(rel.object.element_id, depth + 1)

walk_components("pump-101")

# ── Graph traversal ───────────────────────────────────────────────────────────

print("\nProcess flow (pump-101 SuppliesTo):")
for rel in client.get_related_objects(["pump-101"], relationship_type="SuppliesTo"):
    print(f"  pump-101 → {rel.object.display_name}")

print("\nInstrumentation (tank-201 MonitoredBy):")
for rel in client.get_related_objects(["tank-201"], relationship_type="MonitoredBy"):
    print(f"  {rel.object.display_name} monitors tank-201")

print("\nBFS from pump-101 via SuppliesTo + MonitoredBy:")
def bfs(start_id, rel_types):
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

for obj in bfs("pump-101", ["SuppliesTo", "MonitoredBy"]):
    print(f"  {obj.display_name}")

# ── Done ──────────────────────────────────────────────────────────────────────

client.disconnect()
print("\nDone.")
