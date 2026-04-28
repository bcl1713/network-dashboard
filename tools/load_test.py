#!/usr/bin/env python3
"""Burst synthetic events into the engine.

Usage:
    python tools/load_test.py --rate 200 --duration 30 \
        --url http://localhost:8081 --token $ENGINE_API_TOKEN
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth_eve import make_event  # noqa: E402


async def _worker(client: httpx.AsyncClient, url: str, token: str, queue: asyncio.Queue) -> dict:
    stats = {"ok": 0, "err": 0}
    while True:
        ev = await queue.get()
        if ev is None:
            queue.task_done()
            return stats
        try:
            r = await client.post(
                f"{url}/ingest/event",
                json=ev,
                headers={"X-API-Token": token, "Content-Type": "application/json"},
            )
            if r.status_code == 200:
                stats["ok"] += 1
            else:
                stats["err"] += 1
        except httpx.HTTPError:
            stats["err"] += 1
        finally:
            queue.task_done()


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rate", type=int, default=100, help="events per second")
    p.add_argument("--duration", type=float, default=10, help="seconds")
    p.add_argument("--url", default="http://localhost:8081")
    p.add_argument("--token", default=os.environ.get("ENGINE_API_TOKEN"))
    p.add_argument("--workers", type=int, default=20)
    args = p.parse_args()

    if not args.token:
        print("missing --token or ENGINE_API_TOKEN", file=sys.stderr)
        return 2

    rng = random.Random()
    queue: asyncio.Queue = asyncio.Queue(maxsize=args.workers * 4)

    async with httpx.AsyncClient(timeout=10) as client:
        workers = [
            asyncio.create_task(_worker(client, args.url, args.token, queue))
            for _ in range(args.workers)
        ]

        start = time.monotonic()
        sent = 0
        next_tick = start
        interval = 1.0 / args.rate
        while time.monotonic() - start < args.duration:
            await queue.put(make_event(rng))
            sent += 1
            next_tick += interval
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

        for _ in workers:
            await queue.put(None)

        results = await asyncio.gather(*workers)

    elapsed = time.monotonic() - start
    ok = sum(r["ok"] for r in results)
    err = sum(r["err"] for r in results)
    print(json.dumps({"sent": sent, "ok": ok, "err": err, "elapsed_s": round(elapsed, 2)}))
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
