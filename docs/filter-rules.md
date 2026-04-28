# Filter rules

## Matching order

The classifier evaluates active filters from most specific to least specific
and short-circuits on the first match.

1. host + SID
2. host + SID + destination
3. host + SID + destination + port/proto
4. SID-only fallback (only when `ENGINE_ALLOW_SID_ONLY=true`)
5. message text match (`exact`, `contains`, or `regex`)

`source_host` and `source_subnet` are mutually exclusive on a single rule;
likewise `destination` and `destination_subnet`. Subnet matching uses Python's
stdlib `ipaddress` module.

Retired or expired filters (`expires_at < now`) are skipped during
classification but remain in the database for audit and explainability.

## Actions

| Action | Effect                                                    |
|--------|-----------------------------------------------------------|
| `tag`  | Event still pushed to Loki, but labeled `action=tag`.     |
| `hide` | Event dropped from the Loki push. Raw NDJSON keeps it.    |
| `allow`| Force-allow even if a later rule would tag/hide it.       |

New filters default to `tag` in the UI. The UI requires a preview run before
allowing the user to switch a filter to `hide`.

## Examples

### Telegram bot noise (host + SID)

```json
{
  "name": "Telegram bot noise from media-server",
  "source_host": "10.10.50.42",
  "sid": 2027865,
  "action": "hide",
  "notes": "Outbound HTTPS to telegram.org from media bot; verified safe"
}
```

### Whole-subnet SID tag

```json
{
  "name": "Tag NTP queries from IoT subnet",
  "source_subnet": "10.10.60.0/24",
  "sid": 2010935,
  "action": "tag",
  "notes": "IoT devices doing NTP; keep visible but mark"
}
```

### Regex on message

```json
{
  "name": "Hide self-signed cert warnings on management VLAN",
  "source_subnet": "10.10.40.0/24",
  "message_match": "self-signed.*(splunk|grafana|loki)",
  "match_mode": "regex",
  "action": "hide"
}
```

## Lifecycle

- `enable` / `disable` — temporary toggle.
- `retire` — soft delete; excluded from classification, hidden from default
  list. Audit rows are preserved until normal TTL cleanup removes them.
- `unretire` — restores a retired filter to **disabled** so it can be reviewed
  before being re-enabled.
- `duplicate` — clone an existing filter as a starting point.
- `preview` — match a draft (or saved) filter against the engine's in-memory
  ring buffer (~750 most recent events) before committing.
