# network-dashboard

A free, self-hosted Suricata alert triage stack. OPNsense forwards EVE JSON over
syslog; a small Python pipeline normalizes events, classifies them against a
SQLite-backed allowlist, ships only the filtered stream to Loki, and surfaces
results in Grafana. Raw events are retained on disk for audit.

## Architecture

```
OPNsense Suricata (EVE JSON, geo-enriched)
        |  syslog TCP 5140
        v
Fluent Bit -- file --> infra/data/raw-eve/eve-YYYYMMDD.ndjson  (raw archive)
        |  HTTP POST + X-API-Token
        v
Engine (FastAPI)
  eve.normalize -> ring_buffer.append -> classifier.classify
        | tag/passthrough           | hide
        v                           v
  Loki tenant "filtered"      dropped (still in raw NDJSON)
        v
  Grafana (provisioned dashboards)

UI (FastAPI / Jinja2 / HTMX) --HTTP+token--> Engine REST   (single SQLite writer = engine)
```

Two app containers (`engine`, `ui`) plus three infra containers (`fluent-bit`,
`loki`, `grafana`). SQLite holds only filter metadata; raw EVE retention is
file-based NDJSON. Auth is a single shared `X-API-Token` header enforced by the
engine on every non-health endpoint.

## Quickstart

```sh
cp .env.example .env
# edit .env: set ENGINE_API_TOKEN and GF_ADMIN_PASSWORD
make up
make smoke    # post a synthetic EVE event end-to-end
```

Then open:

- Grafana: <http://localhost:3000>  (admin / `GF_ADMIN_PASSWORD`)
- Filter UI: <http://localhost:8082>
- Engine OpenAPI: <http://localhost:8081/docs>
- Loki ready: <http://localhost:3100/ready>
- Fluent Bit metrics: <http://localhost:2020/api/v1/metrics>

## Ports

| Service      | Host port | Container | Purpose                      |
|--------------|-----------|-----------|------------------------------|
| engine       | 8081      | 8000      | FastAPI ingest + filter API  |
| ui           | 8082      | 8000      | FastAPI/Jinja2/HTMX UI       |
| loki         | 3100      | 3100      | Loki HTTP                    |
| grafana      | 3000      | 3000      | Grafana                      |
| fluent-bit   | 5140/tcp  | 5140      | Syslog from OPNsense         |
| fluent-bit   | 2020      | 2020      | Fluent Bit metrics           |

Override host ports per environment via `.env` (`ENGINE_HOST_PORT`, etc.).

## OPNsense setup

Enable EVE JSON logging in Suricata (**Services → Intrusion Detection →
Administration → Settings**), then add a remote syslog target (**System →
Settings → Logging → Targets**):

| Field | Value |
|---|---|
| Transport | TCP(4) |
| Hostname / IP | IP of this machine |
| Port | `5140` |
| Application | `suricata` |
| Format | RFC 5424 |

See [`docs/opnsense-setup.md`](docs/opnsense-setup.md) for the full walkthrough,
verification steps, and troubleshooting.

## Repository layout

```
docs/                 architecture, runbook, filter rules, API
services/engine/      FastAPI ingest + filter engine, SQLite (single writer)
services/ui/          FastAPI + Jinja2 + HTMX allowlist editor
infra/                docker-compose, Fluent Bit, Loki, Grafana provisioning
infra/data/           gitignored bind volumes (engine SQLite, Loki, Grafana, raw NDJSON)
tools/                synth_eve, post_eve, load_test
```

See [`docs/opnsense-setup.md`](docs/opnsense-setup.md) for the full OPNsense
configuration walkthrough, [`docs/architecture.md`](docs/architecture.md) for
component responsibilities, [`docs/filter-rules.md`](docs/filter-rules.md) for
matching order and examples, and [`docs/runbook.md`](docs/runbook.md) for
restart and restore procedures.

## Development

```sh
cd services/engine && pip install -e .[dev] && pytest -q
cd services/ui    && pip install -e .[dev] && pytest -q
make lint
make fmt
```

## License

See `LICENSE`.
