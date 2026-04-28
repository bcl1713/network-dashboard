#!/usr/bin/env python3
"""Generate synthetic Suricata EVE alerts for development.

Usage:
    python tools/synth_eve.py --count 100 [--out events.ndjson]
    python tools/synth_eve.py --count 1 --pretty
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone

HOSTS = [
    ("10.10.50.42", "media-server.local"),
    ("10.10.50.50", "homelab-runner.local"),
    ("10.10.60.17", "iot-bridge.local"),
    ("10.10.40.5", "admin-laptop.local"),
]
DESTS = [
    ("149.154.167.41", 443, "TCP", "GB", "London"),
    ("8.8.8.8", 53, "UDP", "US", "Mountain View"),
    ("1.1.1.1", 53, "UDP", "AU", "Sydney"),
    ("104.16.0.1", 443, "TCP", "US", "San Francisco"),
    ("142.250.190.78", 443, "TCP", "US", "Mountain View"),
]
SIGNATURES = [
    (2027865, 2, "ET POLICY Telegram Outbound Bot API"),
    (2010935, 3, "ET POLICY Public DNS Query"),
    (2013504, 2, "ET POLICY GNU/Linux APT User-Agent"),
    (2024897, 1, "ET MALWARE Possible Suspicious Domain Lookup"),
    (2100498, 3, "GPL ATTACK_RESPONSE id check returned root"),
]


def make_event(rng: random.Random) -> dict:
    src_ip, host = rng.choice(HOSTS)
    dest_ip, dest_port, proto, country, city = rng.choice(DESTS)
    sid, severity, sig = rng.choice(SIGNATURES)
    ts = datetime.now(tz=timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "+0000")
    return {
        "timestamp": ts,
        "flow_id": rng.getrandbits(56),
        "in_iface": "igb1",
        "event_type": "alert",
        "src_ip": src_ip,
        "src_port": rng.randint(1024, 65535),
        "dest_ip": dest_ip,
        "dest_port": dest_port,
        "proto": proto,
        "host": host,
        "alert": {
            "action": "allowed",
            "gid": 1,
            "signature_id": sid,
            "rev": 1,
            "signature": sig,
            "severity": severity,
        },
        "geoip": {"country_name": _country_name(country), "city_name": city},
    }


def _country_name(code: str) -> str:
    return {
        "GB": "United Kingdom",
        "US": "United States",
        "AU": "Australia",
    }.get(code, code)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--out", default="-", help="output file (- for stdout)")
    p.add_argument("--pretty", action="store_true", help="pretty-print single event")
    args = p.parse_args()

    rng = random.Random(args.seed)
    out = sys.stdout if args.out == "-" else open(args.out, "w", encoding="utf-8")
    try:
        for i in range(args.count):
            ev = make_event(rng)
            if args.pretty and args.count == 1:
                json.dump(ev, out, indent=2)
                out.write("\n")
            else:
                out.write(json.dumps(ev) + "\n")
    finally:
        if out is not sys.stdout:
            out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
