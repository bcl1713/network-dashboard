# Agent Integration Guide

This document is written to be consumed directly by an AI agent tasked with
producing nightly network security briefings and managing Suricata alert
filters.

---

## Mental model

Events flow: **Suricata → engine classifier → Loki ("filtered" tenant) → Grafana**

The classifier runs every event through the active filter rules:

| Filter action | What happens |
|---|---|
| `hide` | Event is **dropped** — never reaches Loki or Grafana |
| `tag` | Event is forwarded to Loki, labeled `action=tag` |
| `allow` | Event is force-forwarded, labeled `action=allow` |
| *(no match)* | Event is forwarded to Loki, labeled `action=passthrough` |

**"Filtered logs" = what's in Loki = everything that was NOT hidden.**
This is what Grafana shows and what your nightly briefing should focus on.

The raw NDJSON archive on disk contains *everything* (including hidden events)
and is the ground truth for auditing what was suppressed — but for the
briefing, Loki is your primary source.

---

## Authentication

### Engine API

Every call (except `/healthz` and `/readyz`) requires:

```
X-API-Token: <ENGINE_API_TOKEN>
```

`ENGINE_API_TOKEN` is set in the project `.env` file.
The engine is reachable at `http://localhost:<ENGINE_HOST_PORT>` (default
port **8081**) from the host, or `http://engine:8000` from inside Docker.

### Loki

Loki is reachable at `http://localhost:3100` from the host, or
`http://loki:3100` from inside Docker.  Multi-tenant auth is enabled, so
every Loki request requires:

```
X-Scope-OrgID: filtered
```

No bearer token is needed — the org header is the only authentication.

---

## Querying last 24 hours of post-filter detections (Loki)

All events that passed through the filters live in Loki under the stream
label `{job="suricata"}`.  Each log line is a JSON object.

### Stream labels (for filtering queries)

| Label | Values | Notes |
|---|---|---|
| `job` | `"suricata"` | Always present |
| `host` | source hostname or IP | The alerting device |
| `sid` | Suricata signature ID (string) | `"0"` if unknown |
| `severity` | `"1"` (critical) / `"2"` (major) / `"3"` (minor) | |
| `action` | `"tag"` / `"allow"` / `"passthrough"` | Never `"hide"` — those events don't reach Loki |

### Log line fields (JSON)

Each log line contains: `event_id`, `event_type`, `src_ip`, `src_port`,
`dest_ip`, `dest_port`, `proto`, `sid`, `signature`, `severity`,
`geoip_country` (destination), `geoip_src_country`,
`geoip_latitude`, `geoip_longitude`, `geoip_src_latitude`, `geoip_src_longitude`.

### Fetching log lines — range query

```
GET http://localhost:3100/loki/api/v1/query_range
X-Scope-OrgID: filtered

Parameters:
  query     LogQL expression
  start     RFC3339 or Unix epoch in nanoseconds
  end       RFC3339 or Unix epoch in nanoseconds
  limit     max log lines to return (default 100, max 5000)
  direction forward | backward (default backward = newest first)
```

Example — all detections in the last 24 hours, newest first:

```bash
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
YESTERDAY=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)

curl -s \
  -H "X-Scope-OrgID: filtered" \
  "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="suricata"}' \
  --data-urlencode "start=$YESTERDAY" \
  --data-urlencode "end=$NOW" \
  --data-urlencode "limit=5000" \
  --data-urlencode "direction=forward"
```

Response shape:

```json
{
  "status": "success",
  "data": {
    "resultType": "streams",
    "result": [
      {
        "stream": { "job": "suricata", "host": "10.10.50.42", "sid": "2027865", "severity": "2", "action": "tag" },
        "values": [
          ["1746230400000000000", "{\"event_id\":\"a3f9...\",\"src_ip\":\"10.10.50.42\",\"signature\":\"ET POLICY Telegram...\"}"]
        ]
      }
    ]
  }
}
```

Each element of `values` is `[timestamp_nanoseconds, log_line_json_string]`.
Parse the second element as JSON to get the event fields.

### Useful LogQL query patterns

```
# All post-filter detections
{job="suricata"}

# Only unclassified events (no filter matched — highest interest)
{job="suricata", action="passthrough"}

# Only critical severity
{job="suricata", severity="1"}

# Specific SID
{job="suricata", sid="2027865"}

# Specific host
{job="suricata", host="10.10.50.42"}

# Keyword search within log lines (slow on large volumes)
{job="suricata"} |= "MALWARE"
```

### Counting/aggregating with metric queries

To get counts by label without fetching raw log lines:

```
GET http://localhost:3100/loki/api/v1/query
X-Scope-OrgID: filtered

Parameters:
  query   LogQL metric expression
  time    RFC3339 or Unix epoch (point-in-time for instant query)
```

Example — count of post-filter events per SID in the last 24 hours:

```bash
curl -s \
  -H "X-Scope-OrgID: filtered" \
  "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query=sum by (sid) (count_over_time({job="suricata"}[24h]))' \
  --data-urlencode "time=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Other useful aggregations:

```
# By host
sum by (host) (count_over_time({job="suricata"}[24h]))

# By severity
sum by (severity) (count_over_time({job="suricata"}[24h]))

# By action (tag vs passthrough vs allow)
sum by (action) (count_over_time({job="suricata"}[24h]))

# Passthrough events only (unclassified — no filter matched)
count_over_time({job="suricata", action="passthrough"}[24h])
```

The metric query response has `resultType: "vector"` and each element has
`{ metric: { sid: "..." }, value: [ timestamp, "count" ] }`.

---

## Engine API — supplementary context

The engine API provides filter metadata and match history.  Use it alongside
Loki data to understand *why* events look the way they do.

### Authentication reminder

```
X-API-Token: <ENGINE_API_TOKEN>
Base URL: http://localhost:8081
```

### Get 24-hour summary stats

```
GET /stats/filters
```

Returns: `total_filters`, `active_filters`, `retired_filters`,
`total_hits_24h` (filter match count), `top_sids` (top 10 SIDs by filter
match count in last 24h).

Note: `total_hits_24h` here counts events that **matched a filter** (any
action). It's complementary to the Loki count of events that survived.

### Get all active filters

```
GET /filters
```

Each filter object includes: `id`, `name`, `action`, `enabled`, `hit_count`
(cumulative), `last_seen_at`, `source_host`, `source_subnet`, `sid`, `notes`.

Use this to understand the current suppression ruleset — what's being hidden
vs. what's being tagged/allowed.

### Check what a specific filter has been catching

```
GET /filters/{id}/matches?limit=100
```

Returns recent audit rows: `event_id`, `matched_at`, `decision`,
`matched_fields` (which fields triggered the match).

### Explain the classification of a specific event

```
GET /events/{event_id}/why-hidden
```

Replays the full classifier chain for an event still in the ring buffer
(≈750 most-recent events).  Useful for understanding why a suspicious event
was tagged rather than hidden (or vice versa).

---

## Creating and managing filters

### Human approval required for all `hide` filters

**Never create a `hide` filter with `"enabled": true`.** All `hide` filters
must be created disabled and reviewed by the operator before activation.
A `hide` filter permanently removes matching events from the Loki stream —
an overly broad or incorrect rule will silently suppress real detections.

`tag` filters may be created enabled immediately — they keep events visible
and add no suppression risk.

### Tag-first workflow (observe before suppressing)

When you see a high-volume pattern that *might* be benign noise but you are
not certain, use a `tag` filter as a holding state rather than going straight
to `hide`:

1. **Create a `tag` filter, enabled.** Events matching the pattern continue
   to flow into Loki but are labeled `action=tag`, making them easy to query
   separately and track in Grafana.
2. **On subsequent nightly runs**, query Loki for that tagged pattern:
   ```
   {job="suricata", action="tag", sid="XXXX"}
   sum by (host) (count_over_time({job="suricata", action="tag", sid="XXXX"}[24h]))
   ```
   Note any changes in volume, source hosts, or destinations.
3. **Once confident the traffic is benign** (consistent pattern, known source,
   no escalation in severity), propose upgrading the filter to `hide`:
   ```
   PUT /filters/{id}
   Content-Type: application/json
   X-API-Token: <token>

   { "action": "hide", "enabled": false, "notes": "Observed for N days via tag filter — confirmed benign. Upgrading to hide pending review." }
   ```
   The `PUT` body uses the same schema as `POST /filters`. Setting
   `enabled: false` returns it to the approval queue even if it was previously
   enabled as a `tag` filter.

### Network-wide SID firing — suggest rule suppression instead

If a SID is generating events from **many different source hosts across
multiple subnets** (not just one device), do **not** create a `hide` filter
for each host or a broad subnet filter. Instead, flag it in the briefing as
a candidate for **Suricata rule suppression**:

> "SID XXXXX is firing from N distinct hosts across all observed subnets.
> This signature may not be relevant to this network. Consider disabling or
> suppressing the rule in OPNsense → Intrusion Detection → Rules rather than
> creating per-host filters in this system."

A filter in this engine only hides events after they are generated — it does
not reduce IDS load or prevent the raw NDJSON from filling up. Disabling the
rule in Suricata stops the alerts at the source.

The threshold for this recommendation: if the same SID is seen from 3 or more
distinct `/24` subnets, or from 5 or more distinct source IPs, prefer the
rule-suppression suggestion over a filter.

---

### Step 1 — check if a filter already exists

```
GET /filters?sid=2027865
GET /filters?host=10.10.50.42
```

### Step 2 — preview the proposed filter

Test against the engine's current ring buffer (≈750 most-recent events)
before creating:

```
POST /filters/preview?limit=20
Content-Type: application/json
X-API-Token: <token>

{
  "name": "draft check",
  "action": "hide",
  "source_host": "10.10.50.42",
  "sid": 2027865
}
```

Response: `{ "match_count": N, "scanned": M, "samples": [...] }`.
If `match_count` is a large fraction of `scanned`, the filter may be too
broad — consider scoping more tightly.

### Step 3 — create the filter (disabled by default)

```
POST /filters
Content-Type: application/json
X-API-Token: <token>

{
  "name": "Telegram noise from media-server",
  "description": "Outbound HTTPS to Telegram bot API",
  "action": "hide",
  "enabled": false,
  "source_host": "10.10.50.42",
  "sid": 2027865,
  "notes": "Verified safe: media-server runs a Telegram notification bot. Observed 600+ hits/day in Loki.",
  "tags": ["ai-suggested"],
  "created_by": "daily-briefing-agent",
  "expires_at": "2026-06-03T00:00:00Z"
}
```

**Always create with `"enabled": false`** so a human can review before it
starts suppressing events.  Use `POST /filters/{id}/enable` to activate.

### Full filter field reference

| Field | Type | Notes |
|---|---|---|
| `name` | string, required | Short label |
| `description` | string | Longer explanation |
| `action` | `"tag"` \| `"hide"` \| `"allow"` | |
| `enabled` | bool | Start `false`; human enables after review |
| `source_host` | string | Exact source IP. Mutually exclusive with `source_subnet` |
| `source_subnet` | string | CIDR, e.g. `"10.10.60.0/24"`. Mutually exclusive with `source_host` |
| `sid` | integer | Suricata signature ID |
| `destination` | string | Exact dest IP. Mutually exclusive with `destination_subnet` |
| `destination_subnet` | string | Dest CIDR |
| `destination_port` | integer 0–65535 | |
| `protocol` | string | `"TCP"`, `"UDP"`, etc. |
| `message_match` | string | Text matched against the alert signature string |
| `match_mode` | `"exact"` \| `"contains"` \| `"regex"` | How `message_match` is applied |
| `tags` | array of strings | e.g. `["ai-suggested", "needs-review"]` |
| `notes` | string | Rationale for creating the filter |
| `created_by` | string | Set to your agent name |
| `expires_at` | ISO-8601 datetime | Filter auto-retires after this time |

**Constraints:**
- `source_host` and `source_subnet` are mutually exclusive.
- `destination` and `destination_subnet` are mutually exclusive.
- SID-only filters (no host/subnet) require `ENGINE_ALLOW_SID_ONLY=true`.

### Matching order (most specific wins)

1. `source_host` + `sid` + destination + port/protocol
2. `source_host` + `sid` + destination
3. `source_host` + `sid`
4. `sid` only (requires `ENGINE_ALLOW_SID_ONLY=true`)
5. `message_match` (exact / contains / regex)

### Filter lifecycle endpoints

| Call | Effect |
|---|---|
| `POST /filters/{id}/enable` | Activate the filter |
| `POST /filters/{id}/disable` | Pause without deleting |
| `POST /filters/{id}/retire` | Soft-delete (audit rows preserved) |
| `PUT /filters/{id}` | Update any field (same body schema as POST) |

---

## Recommended nightly briefing workflow

1. **Volume overview** — run `sum by (sid) (count_over_time({job="suricata"}[24h]))` and `sum by (action) (...)` against Loki to get total event counts and the tag/passthrough split.

2. **Passthrough deep-dive** — query `{job="suricata", action="passthrough"}` for the last 24h. These events matched *no* filter at all and are your highest-interest items. Cluster by SID and source host.

3. **Critical severity** — query `{job="suricata", severity="1"}`. Any severity-1 events should be explicitly addressed in the briefing regardless of volume.

4. **Review existing tagged patterns** — query `{job="suricata", action="tag"}` grouped by SID and host. For any tag filter that has now been observed for several days with a consistent, benign pattern, propose upgrading it to `hide` (disabled, pending operator approval) using `PUT /filters/{id}`.

5. **New/novel signatures** — cross-reference SIDs seen in Loki against `GET /filters` to find SIDs with no existing filter coverage. These are candidates for new `tag` filters to begin observation.

6. **Network-wide SID check** — for any high-volume SID, check how many distinct source hosts and subnets it is firing from. If it spans 3+ distinct `/24` subnets or 5+ source IPs, recommend Suricata rule suppression in OPNsense rather than a filter in this system.

7. **Filter suggestions** — for each proposed new filter: check with `GET /filters?sid=X`, preview with `POST /filters/preview`, then create. Use `action=tag, enabled=true` to begin observation, or `action=hide, enabled=false` if the pattern is already well-understood and operator approval is expected.

8. **Write the briefing** — include: event counts, passthrough anomalies, severity-1 findings, tag-filter upgrade candidates (with filter IDs for the operator to enable), new tag filters created, any rule-suppression recommendations, and any proposed `hide` filters awaiting approval.
