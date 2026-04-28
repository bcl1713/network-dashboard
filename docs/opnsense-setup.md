# OPNsense Setup

This guide covers configuring OPNsense to forward Suricata EVE JSON to the
network-dashboard stack via syslog.

## Prerequisites

- OPNsense with Intrusion Detection (Suricata) installed and at least one
  interface rule enabled
- The dashboard host is reachable from OPNsense on TCP port 5140
- The stack is running (`make up` completed, `make smoke` passes)

## 1. Enable EVE JSON logging in Suricata

**Services → Intrusion Detection → Administration → Settings tab**

| Setting | Value |
|---|---|
| Enabled | checked |
| EVE JSON log | checked |
| EVE JSON log output types | `alert` at minimum; add `http`, `dns`, `tls` as wanted |

Apply and restart Suricata if prompted. EVE JSON output will appear in
`/var/log/suricata/eve.json` on the OPNsense host — confirm it is growing
before continuing.

## 2. Add a remote syslog target

**System → Settings → Logging → Targets → + (add)**

| Field | Value |
|---|---|
| Transport | TCP(4) |
| Hostname / IP | IP or hostname of the machine running this stack |
| Port | `5140` |
| Facility | `local0` (any unused facility works) |
| Level | `Informational` |
| Application | `suricata` |
| Format | `RFC 5424` |
| Description | `network-dashboard` (optional) |

Save and apply. OPNsense will open a persistent TCP connection to Fluent Bit
and stream Suricata syslog records. Fluent Bit expects RFC 5424 framing with
the raw EVE JSON as the message body — do not add any extra OPNsense template
customisation.

## 3. Verify end-to-end

**Fluent Bit metrics** — check records are arriving:

```sh
curl -s http://localhost:2020/api/v1/metrics | python3 -m json.tool | grep -A3 opnsense
```

Look for `records_total` incrementing on the `opnsense.eve` input.

**Raw archive** — the daily NDJSON file should be present and growing:

```sh
ls -lh infra/data/raw-eve/
tail -1 infra/data/raw-eve/eve-$(date +%Y%m%d).ndjson | python3 -m json.tool
```

**Engine stats** — confirm events are being ingested:

```sh
curl -s http://localhost:8081/stats -H "X-API-Token: $(grep ENGINE_API_TOKEN .env | cut -d= -f2)"
```

**Grafana** — open the *IDS Overview* dashboard at `http://localhost:3000`.
Events may take up to a minute to appear after the first record arrives.

## 4. Firewall

If the dashboard host runs a local firewall (ufw, nftables, firewalld), allow
inbound TCP 5140 from the OPNsense management/LAN interface:

```sh
# ufw example
ufw allow from <opnsense-ip> to any port 5140 proto tcp
```

OPNsense itself does not need a firewall rule for outbound traffic on port 5140
unless you have an explicit block-all egress policy on the LAN interface.

## Troubleshooting

**No records in Fluent Bit metrics**
- Confirm OPNsense can reach the dashboard host: `telnet <host> 5140` from an
  OPNsense shell.
- Check the syslog target is active in OPNsense: the target row should show no
  error icon.
- Confirm TCP 5140 is not blocked by a host firewall on the dashboard machine.

**Records arrive but Grafana is empty**
- The engine only pushes events to Loki after classification. If every incoming
  event matches a hide rule the Loki stream will be empty by design. Check the
  filter list in the UI (`http://localhost:8082`).
- Confirm the Loki datasource header is `X-Scope-OrgID: filtered` (provisioned
  by default).

**Syslog records arrive but parse as raw strings, not JSON**
- OPNsense must forward with **RFC 5424** format and the **suricata**
  application filter. Other formats (BSD syslog, plain text) will not match
  Fluent Bit's RFC5424 parser and the inner EVE JSON will not be extracted.
- Check Fluent Bit logs: `docker compose -f infra/docker-compose.yml logs fluent-bit`
  and look for parser errors on the `opnsense.eve` tag.

**Only old events appear after a restart**
- Fluent Bit does not maintain a read position across restarts for the syslog
  TCP input; it will only process records received after it starts. Historical
  events remain in the raw NDJSON archive.
