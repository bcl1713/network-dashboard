# suricata-filter-engine

FastAPI service that:

- accepts EVE JSON events on `POST /ingest/event`
- normalizes them into a `NormalizedEvent`
- keeps a bounded ring of the last ~750 events for preview / lookup
- (Phase 2+) classifies them against SQLite-backed allowlist rules
- pushes the visible/tagged stream to Loki tenant `filtered`

Single writer to SQLite. WAL mode. API-token-authenticated.

## Local dev

```sh
pip install -e .[dev]
ENGINE_API_TOKEN=dev pytest -q
ENGINE_API_TOKEN=dev ENGINE_DB_PATH=./filters.db ENGINE_LOKI_URL=http://localhost:3100 \
  uvicorn app.main:app --reload
```

## Tests

`pytest` runs the engine test suite with an in-process FastAPI TestClient and a
stubbed Loki backend. No real network calls.
