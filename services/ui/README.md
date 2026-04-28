# suricata-filter-ui

FastAPI + Jinja2 + HTMX admin UI for the suricata-filter-engine allowlist.

The UI never touches SQLite directly. All reads and writes go through the
engine REST API; the UI sends the shared `X-API-Token` on every request.

## Local dev

```sh
pip install -e .[dev]
UI_ENGINE_BASE_URL=http://localhost:8081 UI_ENGINE_API_TOKEN=dev \
  uvicorn app.main:app --reload
pytest -q
```
