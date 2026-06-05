---
name: fastapi-testing
description: Pattern for writing pytest autotests for FastAPI backends with mocked external API clients
source: auto-skill
extracted_at: '2026-06-04T21:34:51.388Z'
---

# Testing FastAPI Backends with Mocked External Clients

## Architecture-aware mocking strategy

When the backend follows a layered architecture (`api/` → `services/` → `clients/`), **mock at the layer where the function is imported, NOT at its defining module**. Due to how Python's `from X import Y` works, a local binding is created in the importing module. Patching the defining module after import has no effect on callers that already imported it.

### ⚠️ The `from X import Y` trap

```python
# api/places.py
from clients.places import google_nearby_search  # ← creates local binding

async def api_places(...):
    items = await google_nearby_search(...)  # ← uses local binding
```

Patching `clients.places.google_nearby_search` does NOT affect `api.places.google_nearby_search` because the latter is a separate reference created at import time. You must patch where the function is **used**, not where it's **defined**:

```python
# ❌ WON'T WORK — patches the definition, but api/places.py has its own reference
with patch("clients.places.google_nearby_search", ...) as m:

# ✅ CORRECT — patches the local binding where it's called
with patch("api.places.google_nearby_search", ...) as m:
```

**Rule of thumb:** identify the `from ... import` line and use the importing module's path:

| `from clients.places import google_nearby_search` → patch target | `from services.geocode_service import geocode_address` → patch target |
|---|---|
| `api.places.google_nearby_search` | `api.places.geocode_address` (or wherever it's imported) |
| `services.chat_service.gigachat_request` | `api.chat.gigachat_complete` (or `services.chat_service.gigachat_request`) |

### Why: Mocking httpx directly requires constructing complex `AsyncMock` objects with `__aenter__`/`__aexit__` and is fragile. Mocking the wrapper function is one line: `patch("api.places.google_nearby_search", new_callable=AsyncMock)`.

### Mock priority list (with correct paths):

| What to mock | Correct patch target | Wrong target |
|---|---|---|
| Google Places Nearby Search | `api.places.google_nearby_search` | `clients.places.google_nearby_search` |
| Geocode address | `services.geocode_service.geocode_address` | (same — used from multiple api modules) |
| GigaChat chat completion | `services.chat_service.gigachat_request` | `clients.gigachat_client.gigachat_request` |
| Google Autocomplete | `api.suggestions.google_autocomplete` | `clients.google_autocomplete.google_autocomplete` |

## Integration tests — endpoint-level

Use `httpx.ASGITransport` to test FastAPI endpoints end-to-end without a running server:

```python
from httpx import AsyncClient, ASGITransport
from main import app

transport = ASGITransport(app=app)

@pytest.mark.asyncio
async def test_endpoint(mock_fixture):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/places", params={"lat": 55.75, "lng": 37.62})
    assert r.status_code == 200
```

### Fixture pattern for mocked async functions

```python
@pytest.fixture
def mock_nearby():
    with patch("api.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.return_value = [ ... ]  # fake Google Places results
        yield m
```

### ⚠️ Fixture scope trap: keep mock active during request

Nest the `async with AsyncClient(...)` INSIDE the `with patch(...)` block, not after it:

```python
# ❌ WRONG — mock is already deactivated when AsyncClient runs
@pytest.mark.asyncio
async def test_places_zero_results():
    with patch("api.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.return_value = []
    async with AsyncClient(transport=transport, base_url="http://test") as c:  # ← mock already gone
        r = await c.get(...)

# ✅ CORRECT — mock stays active during request
@pytest.mark.asyncio
async def test_places_zero_results():
    with patch("api.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.return_value = []
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get(...)
    assert r.status_code == 200
```

## Unit tests — pure functions

Pure functions (haversine, convert_google_place, build_places_context, _price_label) get their own test files with **no mocking at all**. Group by module:

- `test_haversine.py` → `utils/haversine.py`
- `test_utils.py` → `utils/categories.py` + service helper functions
- `test_places_service.py` → `services/places_service.py:convert_google_place()`
- `test_chat_service.py` → `services/chat_service.py:build_places_context()`

### ⚠️ Config dependency: functions that read env vars aren't truly pure

Some helper functions read `core.config` at module level. For example, `_photo_url()` checks `GOOGLE_MAPS_API_KEY` — which is `None` when running without `.env`. Tests that assert `image_url is not None` will fail locally.

**Fix:** patch the config value at the importing module:

```python
from unittest.mock import patch

@patch("services.places_service.GOOGLE_MAPS_API_KEY", "test_key")
def test_convert_full_item():
    p = convert_google_place(...)
    assert p["image_url"] is not None
```

The same pattern applies to any function that uses a module-level config import (`from core.config import ...`). Patch at `{module_where_imported}.{CONSTANT_NAME}`.

## Required dependencies

- `pytest-asyncio` must be in `requirements.txt` (not just `pytest`)
- `pytest.ini` must have `asyncio_mode = strict` under the `[pytest]` section header:

### ⚠️ `pythonpath` — prevents ModuleNotFoundError on local runs

Without `PYTHONPATH`, `pytest` can't find `main`, `services`, `models`, `utils` when running locally. Fix by adding `pythonpath = .` to `pytest.ini`:

```ini
[pytest]
asyncio_mode = strict
testpaths = tests
python_files = test_*.py
python_functions = test_*
pythonpath = .
```

**Why:** `pythonpath = .` tells pytest to append the project root (where `main.py` lives) to `sys.path`, so imports like `from main import app`, `from models.places import ChatPlace`, `from utils.haversine import haversine` resolve correctly. Without this, you'd need `set PYTHONPATH=. && pytest` on every run.

### ⚠️ Critical: When editing pytest.ini (or any INI file), the `[pytest]` section header must remain on its own line. Do NOT replace the section header with content — this breaks the entire config file.

## Test structure convention

```
backend/tests/
├── test_haversine.py        # pure function unit tests
├── test_utils.py            # categories dict, price_label, photo_url helpers
├── test_places_service.py   # convert_google_place mapping logic
├── test_chat_service.py     # build_places_context context builder
├── test_api.py              # integration tests (all endpoints, mocked clients)
└── test_smoke.py            # trivial sanity check
```

## Key test cases to cover per endpoint

**GET /api/places:**
- by coords (lat+lng)
- by address (auto geocode)
- no params → 422
- invalid coords → 422
- category filter
- limit param
- sorted by distance
- upstream error (Google 502)
- zero results

**POST /api/geocode:**
- success
- not found → 422
- empty body → 422

**POST /api/chat:**
- success (choices-based response)
- success (reply-based response — both formats exist)
- with context (address + places)
- with history
- GigaChat error → 502
- GigaChat not configured → 503
- empty/no reply in response → 502

**GET /api/suggestions:**
- success (returns list of address strings)
- with coords (lat+lng)
- empty q → 422
- missing q → 422
- upstream error → 502

## Running tests in CI/CD with Docker

### ⚠️ Use `docker compose run`, NOT `docker compose exec`

When running pytest in a CI pipeline via Docker, use `run` instead of `exec`:

```yaml
# WRONG — exec runs pytest alongside uvicorn in the same container (OOM risk)
- name: Run tests
  run: docker compose exec -T backend pytest -v

# CORRECT — run creates a separate container with pytest as CMD (no uvicorn)
- name: Run tests
  run: docker compose run -T --rm backend pytest -v
```

**Why:** `exec` requires the container to already be running (with uvicorn as CMD), so pytest and uvicorn compete for memory → exit code 137 (SIGKILL / OOM). `run` creates a fresh container with pytest as the entrypoint, no uvicorn overhead.

**Full CI pattern:**
```yaml
- name: Build image
  run: docker compose build backend

- name: Run tests
  run: docker compose run -T --rm backend pytest -v

- name: Cleanup
  if: always()
  run: docker compose down --remove-orphans
```

No need for `docker compose up -d` before tests — the backend container doesn't need to serve requests during testing, and nginx is irrelevant.