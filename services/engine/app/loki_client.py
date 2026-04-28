"""Async Loki push client.

Pushes one event at a time (small per-event JSON) with stream labels derived
from the normalized event. Uses the multi-tenant header so we can keep the
filtered stream isolated from any future raw stream.

Failures are retried with exponential backoff. Persistent failure is logged
but does not raise to the caller -- ingest must keep accepting events even if
Loki is down. The raw NDJSON archive remains the source of truth.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from .eve import NormalizedEvent
from .logging import get_logger

log = get_logger(__name__)


class LokiClient:
    def __init__(
        self,
        base_url: str,
        tenant: str,
        *,
        timeout_s: float = 5.0,
        retry_max: int = 5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._tenant = tenant
        self._timeout_s = timeout_s
        self._retry_max = retry_max
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def push(self, event: NormalizedEvent, action: str) -> bool:
        """Push a single event. Returns True on success, False on giving up."""
        labels = event.to_loki_labels(action)
        ts_ns = str(int(event.timestamp.timestamp() * 1_000_000_000))
        line = json.dumps(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "src_ip": event.src_ip,
                "src_port": event.src_port,
                "dest_ip": event.dest_ip,
                "dest_port": event.dest_port,
                "proto": event.proto,
                "sid": event.sid,
                "signature": event.signature,
                "severity": event.severity,
                "geoip_country": event.geoip_country,
                "geoip_city": event.geoip_city,
            },
            separators=(",", ":"),
        )
        body: dict[str, Any] = {
            "streams": [
                {
                    "stream": labels,
                    "values": [[ts_ns, line]],
                }
            ]
        }
        return await self._post_with_retry(body)

    async def ping(self) -> bool:
        try:
            r = await self._client.get(f"{self._base_url}/ready")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def _post_with_retry(self, body: dict[str, Any]) -> bool:
        url = f"{self._base_url}/loki/api/v1/push"
        headers = {
            "Content-Type": "application/json",
            "X-Scope-OrgID": self._tenant,
        }
        delay = 0.5
        for attempt in range(1, self._retry_max + 1):
            try:
                r = await self._client.post(url, json=body, headers=headers)
                if r.status_code in (200, 204):
                    return True
                if 500 <= r.status_code < 600 or r.status_code == 429:
                    log.warning(
                        "loki.push.retry",
                        attempt=attempt,
                        status=r.status_code,
                        body=r.text[:200],
                    )
                else:
                    log.error(
                        "loki.push.client_error",
                        status=r.status_code,
                        body=r.text[:200],
                    )
                    return False
            except httpx.HTTPError as exc:
                log.warning("loki.push.exception", attempt=attempt, error=str(exc))

            await asyncio.sleep(delay)
            delay = min(delay * 2, 8.0)

        log.error("loki.push.gave_up", attempts=self._retry_max)
        return False
