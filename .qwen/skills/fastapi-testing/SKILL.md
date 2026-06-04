---
name: fastapi-testing
description: Pattern for writing pytest autotests for FastAPI backends with mocked external API clients
source: auto-skill
extracted_at: '2026-06-03T08:50:30.972Z'
---

# Testing FastAPI Backends with Mocked External Clients

## Architecture-aware mocking strategy

When the backend follows a layered architecture (`api/` → `services/` → `clients/`), **mock at the client/service layer, NOT at the httpx level**. This keeps tests simple and resilient to internal refactorings.

```
Mock targets (by priority):
1. client-layer async functions  →  clients.places.google_nearby_search, clients.gigachat_client.gigachat_request
2. service-layer async functions →  services.geocode_service.geocode_address
3. httpx.AsyncClient itself      →  ONLY when no client wrapper exists (avoid if possible)
```

### Why: Mocking httpx directly requires constructing complex `AsyncMock` objects with `__aenter__`/`__aexit__` and is fragile. Mocking the wrapper function is one line: `patch("clients.places.google_nearby_search", new_callable=AsyncMock)`.

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
    with patch("clients.places.google_nearby_search", new_callable=AsyncMock) as m:
        m.return_value = [ ... ]  # fake Google Places results
        yield m
```

## Unit tests — pure functions

Pure functions (haversine, convert_google_place, build_places_context, _price_label) get their own test files with **no mocking at all**. Group by module:

- `test_haversine.py` → `utils/haversine.py`
- `test_utils.py` → `utils/categories.py` + service helper functions
- `test_places_service.py` → `services/places_service.py:convert_google_place()`
- `test_chat_service.py` → `services/chat_service.py:build_places_context()`

## Required dependencies

- `pytest-asyncio` must be in `requirements.txt` (not just `pytest`)
- `pytest.ini` must have `asyncio_mode = strict` under the `[pytest]` section header:

```ini
[pytest]
asyncio_mode = strict
testpaths = tests
python_files = test_*.py
python_functions = test_*
```

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