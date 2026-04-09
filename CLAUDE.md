# CLAUDE.md

## Project Overview

**i3x-client** is a Python client library for i3X servers, published to PyPI as `i3x-client`. It provides a paho-mqtt-style developer experience for interacting with i3X APIs. Maintained by CESMII.

- **Repo:** https://github.com/cesmii/python-i3x-client
- **Package name on PyPI:** `i3x-client`
- **Import name:** `import i3x`

## Terminology

- The proper name is **i3X** (lowercase i, 3, uppercase X). Never use "CMIP" — that is a deprecated term.
- Author/org is **CESMII**, not "i3X Working Group".

## Project Structure

```
src/i3x/           # Source (src layout)
├── __init__.py     # Public API re-exports, __version__
├── client.py       # Main Client class (all public methods)
├── models.py       # Frozen dataclasses (Namespace, ObjectType, ObjectInstance, etc.)
├── errors.py       # I3XError hierarchy
├── _transport.py   # Internal httpx wrapper, error mapping
├── _sse.py         # SSE stream reader (background daemon thread)
└── _subscription.py # Subscription lifecycle tracker
tests/              # Unit tests using pytest + respx
```

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

Tests use `respx` to mock `httpx` calls — no live server needed.

## Version Management

Version is tracked in **two places** — both must be updated together:
- `pyproject.toml` → `version = "x.y.z"`
- `src/i3x/__init__.py` → `__version__ = "x.y.z"`

## Building & Publishing

```bash
rm -rf dist
python -m build
twine check dist/*
twine upload dist/*
```

PyPI does not allow re-uploading the same version. Always bump the version before rebuilding.

## Key Design Decisions

- **Sync-first** — No async. Background threads for SSE only.
- **Callbacks receive `(client, data)`** — Client ref lets handlers call back into the client.
- **`subscribe()` is high-level** — Combines create + register + stream into one call. Low-level methods also available.
- **No pydantic** — Plain frozen dataclasses with `from_dict()` classmethods.
- **Two runtime deps only** — `httpx` and `httpx-sse`.

## Reference Server

The reference i3X server lives at `~/Projects/API/demo/server/`. To run it locally:

```bash
cd ~/Projects/API/demo/server
source venv/bin/activate
python app.py
```

Runs on `http://localhost:8080` with Swagger UI at `/docs`.
