"""Replay an NDJSON file of EVE events into the engine.

Useful for filling the ring buffer during development or for re-running
analysis against a saved capture from data/raw-eve.

Usage (inside the engine container):
    python -m scripts.replay_eve --file /raw/eve-20260427.ndjson \
        --url http://localhost:8000

Or from the host:
    python services/engine/scripts/replay_eve.py \
        --file infra/data/raw-eve/eve.ndjson \
        --url http://localhost:8081 \
        --token "$ENGINE_API_TOKEN"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--token", default=os.environ.get("ENGINE_API_TOKEN"))
    p.add_argument("--rate", type=float, default=0, help="events per second; 0 = unlimited")
    p.add_argument("--bulk-size", type=int, default=100)
    args = p.parse_args()

    if not args.token:
        print("missing --token or ENGINE_API_TOKEN", file=sys.stderr)
        return 2

    headers = {"X-API-Token": args.token, "Content-Type": "application/x-ndjson"}
    delay = (1.0 / args.rate) if args.rate > 0 else 0
    sent = 0
    with httpx.Client(timeout=30) as client, open(args.file, encoding="utf-8") as f:
        batch: list[str] = []
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                continue
            batch.append(line)
            if len(batch) >= args.bulk_size:
                _flush(client, args.url, headers, batch)
                sent += len(batch)
                batch.clear()
                if delay:
                    time.sleep(delay * args.bulk_size)
        if batch:
            _flush(client, args.url, headers, batch)
            sent += len(batch)
    print(json.dumps({"sent": sent}))
    return 0


def _flush(client: httpx.Client, url: str, headers: dict, batch: list[str]) -> None:
    payload = "\n".join(batch)
    r = client.post(f"{url}/ingest/bulk", content=payload, headers=headers)
    if r.status_code >= 400:
        print(f"bulk failed: {r.status_code} {r.text[:200]}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
