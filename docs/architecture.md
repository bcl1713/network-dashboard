# Architecture

## Pipeline

```
OPNsense Suricata ──syslog/TCP 5140──▶ Fluent Bit ──┬──▶ data/raw-eve/eve-YYYYMMDD.ndjson
                                                    └──HTTP+token──▶ Engine /ingest/event
                                                                       │
                                                                       ▼
                                              eve.normalize → ring_buffer.append
                                                                       │
                                                                       ▼
                                              classifier.classify(rule_index)
                                                       │             │
                                                       │ tag         │ hide
                                                       ▼             ▼
                                            Loki (filtered)        dropped
                                                       │
                                                       ▼
                                                  Grafana

UI ──HTTP+token──▶ Engine REST  (engine is the single SQLite writer)
```

## Component responsibilities

- **Suricata on OPNsense** — sensor; emits EVE JSON; performs GeoIP enrichment.
- **Fluent Bit** — receives syslog, parses inner EVE JSON, writes raw NDJSON to
  disk, posts each event to the engine.
- **Engine** (`services/engine`) — normalizes, ring-buffers, classifies, pushes
  the visible stream to Loki, owns the SQLite filter store. Single writer.
- **UI** (`services/ui`) — HTMX/Jinja2 admin app; calls the engine REST API
  for all reads and writes, never touches SQLite directly.
- **Loki** — stores only the filtered/tagged stream. `auth_enabled: true` so we
  can scope by tenant header.
- **Grafana** — provisioned datasource pointing at Loki tenant `filtered`,
  plus six dashboards for triage and geomap.
- **Raw NDJSON** — file-based archive under `infra/data/raw-eve/`. Hidden
  events remain queryable here even when dropped from Loki.

## Why a separate engine and UI

- The ingest hot path stays small and restart-friendly.
- The UI can be redeployed (templates, static assets, page logic) without
  bouncing the ingest service.
- One process owns SQLite, which keeps WAL semantics simple.

## Data ownership

- **SQLite** — filter rules and audit (engine only).
- **Ring buffer** — last ~750 normalized events for preview (engine memory).
- **Raw NDJSON** — full firehose, file-rotated daily by Fluent Bit.
- **Loki** — visible/tagged stream only.

## Failure modes

- Loki down: engine still accepts events; pushes are retried with backoff.
  Raw NDJSON keeps recording.
- Engine down: Fluent Bit's HTTP retry queue holds events briefly; raw NDJSON
  still records.
- UI down: ingest is unaffected; reads/writes via the engine API still work
  (e.g. `curl`).
- SQLite locked: WAL mode + `busy_timeout=5000` smooths over short contention;
  the engine is the only writer.
