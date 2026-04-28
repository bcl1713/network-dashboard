# Runbook

## Daily ops

- Check Grafana → IDS Overview for ingest rate and top SIDs.
- Review filter hit counts in the UI; retire stale or never-firing filters.
- Spot-check `infra/data/raw-eve/` rotation; current day file should be
  growing, prior days should be present.

## Restart a single service

```sh
docker compose -f infra/docker-compose.yml restart engine
docker compose -f infra/docker-compose.yml restart ui
docker compose -f infra/docker-compose.yml restart fluent-bit
```

The engine and UI can be restarted independently. The engine owns SQLite, so
restart it briefly; the UI will reconnect on its next request.

## Backups

`infra/backups/sqlite-backup.sh` uses `sqlite3 .backup` for a hot backup that
respects WAL. It rotates 7 daily and 4 weekly snapshots under
`infra/backups/snapshots/`.

Schedule it from cron or a Portainer scheduled task:

```cron
17 2 * * * /opt/network-dashboard/infra/backups/sqlite-backup.sh
```

## Restore from backup

```sh
make down
cp infra/backups/snapshots/filters-YYYYMMDD.sqlite infra/data/engine/filters.db
make up
```

## Raw NDJSON retention

Fluent Bit rotates the raw archive daily (`eve-YYYYMMDD.ndjson`). Prune
old files via cron or `find`:

```sh
find infra/data/raw-eve -name 'eve-*.ndjson' -mtime +30 -delete
```

## GeoIP enrichment (not yet configured)

`geoip_country` and `geoip_city` are null on all events. To populate them,
enrich in Fluent-Bit using its built-in `geoip2` filter against a MaxMind
GeoLite2 database — no OPNsense changes needed.

**Steps:**

1. Sign up for a free MaxMind account at <https://dev.maxmind.com/geoip/geolite2-free-geolocation-data>
   and download `GeoLite2-City.mmdb`.
2. Place the file on TrueNAS, e.g. `/mnt/data/network-dashboard/geoip/GeoLite2-City.mmdb`.
3. Mount it into the fluent-bit container in `infra/docker-compose.yml`:

   ```yaml
   volumes:
     - /mnt/data/network-dashboard/geoip/GeoLite2-City.mmdb:/etc/fluent-bit/GeoLite2-City.mmdb:ro
   ```

4. Add a filter to `infra/fluent-bit/fluent-bit.conf` before the OUTPUT blocks:

   ```ini
   [FILTER]
       Name        geoip2
       Match       opnsense.eve
       Database    /etc/fluent-bit/GeoLite2-City.mmdb
       Lookup_Key  src_ip
       Record      geoip_country country.names.en
       Record      geoip_city    city.names.en
   ```

5. The engine already reads `geoip_country` and `geoip_city` from the payload,
   so no engine changes are needed.
6. Recreate the container:
   `docker compose ... up -d --force-recreate fluent-bit`

Note: The MaxMind GeoLite2 database updates monthly. Consider a cron job to
re-download it and recreate the container.

## Common issues

- **Grafana dashboard empty** — confirm Loki tenant header. The provisioned
  datasource sends `X-Scope-OrgID: filtered`; if you query Loki directly, you
  must send the same header. If Grafana is accidentally pointed at the raw
  NDJSON path, treat it as a deployment error and fix the datasource.
- **Engine returning 401** — `ENGINE_API_TOKEN` mismatch. Check `.env` and
  Fluent Bit's `Header X-API-Token` value. The UI reads the token from
  `ENGINE_API_TOKEN` too.
- **Filter not matching** — open the event in the UI and use
  `GET /events/{id}/why-hidden` (linked from the event page) to see which
  rules were considered and which fields matched. If the rule should match,
  verify it's enabled, not retired, and not expired.
- **SQLite "database is locked"** — only the engine should write. Check that
  no manual `sqlite3` shell is open against the file. WAL +
  `busy_timeout=5000` handles brief contention.
