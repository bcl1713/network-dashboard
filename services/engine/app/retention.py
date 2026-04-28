"""Periodic pruner for filter_audit.

Runs as a background asyncio task started by the FastAPI lifespan. Deletes
audit rows older than `audit_ttl_days`. Runs once at startup, then every
`audit_prune_interval_s` seconds.

Retired filters keep their audit history until normal TTL cleanup removes it.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from .config import Settings
from .db import session_scope
from .logging import get_logger
from .models import FilterAudit

log = get_logger(__name__)


def prune_once(ttl_days: int) -> int:
    """Synchronous prune. Returns number of rows deleted."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=ttl_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    with session_scope() as session:
        result = session.execute(
            delete(FilterAudit).where(FilterAudit.matched_at < cutoff_str)
        )
        session.commit()
        return result.rowcount or 0


async def retention_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    """Run prune_once on an interval until stop_event is set."""
    interval = max(60, settings.audit_prune_interval_s)
    while not stop_event.is_set():
        try:
            deleted = await asyncio.to_thread(prune_once, settings.audit_ttl_days)
            if deleted:
                log.info("retention.pruned", deleted=deleted)
        except Exception as exc:  # noqa: BLE001
            log.error("retention.error", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
