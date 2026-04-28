# Engine REST API

All endpoints except `/healthz` and `/readyz` require the
`X-API-Token: <ENGINE_API_TOKEN>` header.

The engine also serves OpenAPI at `/docs` and `/openapi.json`.

## Filters

| Method | Path                                    | Purpose                                             |
|--------|-----------------------------------------|-----------------------------------------------------|
| GET    | `/filters?include_retired&q&host&sid`   | List filters. `include_retired=true` adds retired.  |
| POST   | `/filters`                              | Create a filter.                                    |
| GET    | `/filters/{id}`                         | Read a filter.                                      |
| PUT    | `/filters/{id}`                         | Update a filter.                                    |
| POST   | `/filters/{id}/enable`                  | Enable.                                             |
| POST   | `/filters/{id}/disable`                 | Disable.                                            |
| POST   | `/filters/{id}/retire`                  | Soft-delete. Audit history is preserved.            |
| POST   | `/filters/{id}/unretire`                | Restore to disabled state.                          |
| POST   | `/filters/{id}/duplicate`               | Clone; returns the new filter.                      |
| POST   | `/filters/{id}/preview`                 | Match the saved filter against the ring buffer.     |
| POST   | `/filters/preview`                      | Match a draft filter (body) against the ring buffer.|
| POST   | `/filters/from-event`                   | Suggest a filter draft from a known event id.       |
| GET    | `/filters/{id}/matches?limit=100`       | Recent audit rows for a filter.                     |

## Ingest

| Method | Path             | Purpose                                  |
|--------|------------------|------------------------------------------|
| POST   | `/ingest/event`  | Single EVE JSON event.                   |
| POST   | `/ingest/bulk`   | NDJSON body or JSON array of events.     |

## Events / audit

| Method | Path                          | Purpose                                              |
|--------|-------------------------------|------------------------------------------------------|
| GET    | `/events/{id}`                | Look up a recent event from the in-memory ring.      |
| GET    | `/events/{id}/why-hidden`     | Replay classifier; return all rules considered.      |

## Stats / health

| Method | Path             | Purpose                                          |
|--------|------------------|--------------------------------------------------|
| GET    | `/stats/filters` | Aggregate counts: top SIDs, hide rate, hits 24h. |
| GET    | `/healthz`       | Liveness.                                        |
| GET    | `/readyz`        | Readiness (DB + Loki ping).                      |
