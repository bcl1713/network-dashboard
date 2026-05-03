# Agent Integration Guide

This document is written to be consumed directly by an AI agent tasked with
producing nightly network security briefings and managing Suricata alert
filters.

---

## Authentication

Every API call (except `/healthz` and `/readyz`) requires this header:

```
X-API-Token: <ENGINE_API_TOKEN>
```

`ENGINE_API_TOKEN` is set in the project `.env` file.  The engine is
reachable at `http://localhost:<ENGINE_HOST_PORT>` (default port **8081**) when
running on the host, or at `http://engine:8000` from inside Docker.

Verify connectivity before starting:

```bash
curl -s http://localhost:8081/healthz
# → {"status":"ok"}
```

---

## Pulling the Last 24 Hours of Detection Data

Call these three endpoints in order to build a complete picture.

### 1. Aggregate stats

```
GET /stats/filters
```

Returns a single JSON object:

```json
{
  "total_filters": 42,
  "active_filters": 38,
  "retired_filters": 4,
  "total_hits_24h": 1847,
  "top_sids": [
    { "sid": 2027865, "hits_24h": 610, "last_seen_at": "2026-05-03T05:12:33" },
    ...
  ]
}
```

`total_hits_24h` is the count of events that matched **any** active filter in
the last 24 hours (from `filter_audit`).  `top_sids` lists the 10 noisiest
Suricata signature IDs over that window.

### 2. All active filters with activity counters

```
GET /filters
```

Returns a JSON array.  Each element has:

| Field | Meaning |
|---|---|
| `id` | Numeric filter ID |
| `name` | Human-readable label |
| `action` | `"tag"`, `"hide"`, or `"allow"` |
| `enabled` | `true` / `false` |
| `hit_count` | Cumulative match count (all time) |
| `last_seen_at` | Timestamp of most recent match |
| `last_matched_event_id` | Event ID of that match |
| `source_host` / `source_subnet` | The IP or CIDR the rule targets |
| `sid` | Suricata signature ID (if scoped to one SID) |
| `notes` | Operator rationale |

A filter with `hit_count > 0` but `last_seen_at` many days ago may be stale
(the source changed or traffic stopped).  A filter with `hit_count == 0` was
never matched.

Use `?include_retired=true` to also retrieve retired (soft-deleted) filters.

### 3. Per-filter match audit trail

For any filter you want to inspect more closely:

```
GET /filters/{id}/matches?limit=100
```

Returns up to 100 recent audit rows:

```json
[
  {
    "event_id": "a3f9...",
    "matched_at": "2026-05-03T04:55:01",
    "decision": "hide",
    "matched_fields": { "source_host": "10.10.50.42", "sid": 2027865 }
  },
  ...
]
```

`matched_fields` shows exactly which fields on the event triggered the match —
useful for verifying a filter is doing what you expect.

### 4. Explain why a specific event was classified the way it was

```
GET /events/{event_id}/why-hidden
```

Replays the full classifier chain against all active rules and returns:

```json
{
  "event_id": "a3f9...",
  "decision": { "action": "hide", "filter_id": 7, "matched_fields": {...} },
  "chain": [
    { "filter_id": 12, "name": "Allow DNS from monitoring", "action": "allow", "matched": false, "matched_fields": {} },
    { "filter_id": 7,  "name": "Telegram noise",            "action": "hide", "matched": true,  "matched_fields": {...} }
  ]
}
```

Note: `event_id` values are only available while the event is in the in-memory
ring buffer (≈750 most-recent events).  Events that have aged out return 404.

---

## Reading Raw NDJSON Logs

The engine archives **every** inbound Suricata event — including those
suppressed by `hide` filters — to daily NDJSON files:

```
infra/data/raw-eve/eve-YYYYMMDD.ndjson
```

One JSON object per line.  Key fields in each alert event:

```json
{
  "timestamp": "2026-05-03T04:55:01.123456+0000",
  "event_type": "alert",
  "src_ip": "10.10.50.42",
  "src_port": 49201,
  "dest_ip": "149.154.167.41",
  "dest_port": 443,
  "proto": "TCP",
  "alert": {
    "signature_id": 2027865,
    "signature": "ET POLICY Telegram Outbound Bot API",
    "severity": 2,
    "category": "Potentially Bad Traffic"
  },
  "geoip_src_country": "United States",
  "geoip_country": "United Kingdom"
}
```

Only `event_type == "alert"` lines are Suricata detections.  Other types
(`"dns"`, `"http"`, `"tls"`, etc.) are flow metadata.

To find all events with a specific SID over the last 24 hours:

```bash
grep '"signature_id": 2027865' infra/data/raw-eve/eve-$(date +%Y%m%d).ndjson
```

**The NDJSON archive is the ground truth.**  Loki only receives events that
were *not* hidden.  If you need to audit what was suppressed, read the NDJSON
files directly.

---

## Creating and Managing Filters

### Check before creating

Before proposing a new filter, verify one doesn't already exist:

```
GET /filters?sid=2027865
GET /filters?host=10.10.50.42
```

### Preview a draft filter

Test a proposed filter against the engine's in-memory ring (≈750 most-recent
events) before committing:

```
POST /filters/preview?limit=20
Content-Type: application/json

{
  "name": "draft check",
  "action": "tag",
  "source_host": "10.10.50.42",
  "sid": 2027865
}
```

Response:

```json
{
  "match_count": 14,
  "scanned": 312,
  "samples": [
    { "event_id": "...", "timestamp": "...", "src_ip": "10.10.50.42",
      "dest_ip": "149.154.167.41", "sid": 2027865, "signature": "ET POLICY ..." }
  ]
}
```

A `match_count` that is a large fraction of `scanned` means the filter is
broad — consider adding more specificity (e.g., scoping to `source_host`
instead of just `sid`).

### Create a filter

```
POST /filters
Content-Type: application/json

{
  "name": "Telegram noise from media-server",
  "description": "Outbound HTTPS to Telegram bot API",
  "action": "hide",
  "enabled": false,
  "source_host": "10.10.50.42",
  "sid": 2027865,
  "notes": "Verified safe: media-server runs a Telegram notification bot. Observed 600+ hits/day.",
  "tags": ["ai-suggested"],
  "created_by": "daily-briefing-agent"
}
```

**Always create with `"enabled": false`** so a human can review before the
filter goes live.  Use `POST /filters/{id}/enable` to activate after review.

Returns the created filter object including its new numeric `id`.

### Full filter field reference

| Field | Type | Notes |
|---|---|---|
| `name` | string, required | Short label shown in the UI |
| `description` | string | Longer free-text description |
| `action` | `"tag"` \| `"hide"` \| `"allow"` | Default `"tag"` |
| `enabled` | bool | Start `false`; enable after review |
| `source_host` | string | Exact source IP. Mutually exclusive with `source_subnet` |
| `source_subnet` | string | CIDR, e.g. `"10.10.60.0/24"`. Mutually exclusive with `source_host` |
| `sid` | integer | Suricata signature ID |
| `generator_id` | integer | Suricata generator (rarely needed) |
| `destination` | string | Exact dest IP. Mutually exclusive with `destination_subnet` |
| `destination_subnet` | string | Dest CIDR. Mutually exclusive with `destination` |
| `destination_port` | integer 0–65535 | |
| `protocol` | string | `"TCP"`, `"UDP"`, etc. |
| `message_match` | string | Text matched against the alert signature string |
| `match_mode` | `"exact"` \| `"contains"` \| `"regex"` | How `message_match` is applied |
| `tags` | array of strings | e.g. `["ai-suggested", "needs-review"]` |
| `notes` | string | Rationale; shown in UI and audit trail |
| `created_by` | string | Set to your agent name |
| `expires_at` | ISO-8601 datetime | Filter auto-retires after this time |

**Constraints:**
- `source_host` and `source_subnet` are mutually exclusive on one rule.
- `destination` and `destination_subnet` are mutually exclusive on one rule.
- At least one matching criterion must be present (`sid`, `source_host`,
  `source_subnet`, `message_match`, etc.).
- SID-only filters (no host/subnet) are blocked unless the engine is configured
  with `ENGINE_ALLOW_SID_ONLY=true`.

### Matching order (classifier specificity)

Filters are evaluated most-specific-first.  First match wins.

1. `source_host` + `sid` + destination + port/protocol
2. `source_host` + `sid` + destination
3. `source_host` + `sid`
4. `sid` only (requires `ENGINE_ALLOW_SID_ONLY=true`)
5. `message_match` (exact / contains / regex)

### Lifecycle operations

| Call | Effect |
|---|---|
| `POST /filters/{id}/enable` | Make the filter active |
| `POST /filters/{id}/disable` | Pause without deleting |
| `POST /filters/{id}/retire` | Soft-delete (excluded from classification; audit preserved) |
| `POST /filters/{id}/unretire` | Restore to disabled for review |
| `PUT /filters/{id}` | Update any field (same body schema as POST) |

---

## Recommended Nightly Briefing Workflow

1. `GET /stats/filters` — get 24h hit totals and top SIDs.
2. `GET /filters` — load all active filters.  Cross-reference the top SIDs
   against existing filters to find SIDs with no coverage.
3. For each high-volume uncovered SID, grep the NDJSON archive
   (`eve-YYYYMMDD.ndjson`) for sample events to assess whether the traffic
   is benign noise or worth investigating.
4. For each high-volume covered SID, call `GET /filters/{id}/matches` to
   confirm the filter is catching what you expect.
5. Flag any `severity: 1` (critical) events that are *not* covered by a hide
   filter — these should be highlighted in the briefing regardless of volume.
6. Note filters with `hit_count > 0` but `last_seen_at` more than 7 days ago
   as potentially stale.
7. For any filter you want to propose: call `POST /filters/preview` first,
   then `POST /filters` with `enabled: false`.
8. Write the briefing.  Include: summary stats, items requiring attention,
   stale filter candidates, and a list of filters created (with their IDs).

---

## Filter Action Safety Guidelines

- Use `"tag"` by default.  `"hide"` permanently removes events from the
  Grafana/Loki stream — only use it for traffic you have verified is benign.
- When proposing a `"hide"` filter based on a single day's observation, set
  `expires_at` to 30 days from now so it auto-retires if the pattern changes.
- Add `notes` explaining what you observed, why you believe it is benign, and
  what evidence would cause you to reconsider.
- Never create a filter with `"allow"` action unless you understand that it
  bypasses all subsequent rules for matching traffic.
