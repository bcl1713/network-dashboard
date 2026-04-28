"""Engine entrypoint.

Builds the FastAPI app, wires shared singletons (ring buffer, Loki client,
SQLite engine, rule index) onto app.state in the lifespan, and registers
route modules.

Phase 2 wires `app.state.classify` / `app.state.explain` / `app.state.on_match`
so the ingest hot path picks up the classifier without route changes.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from sqlalchemy import update

from .classifier import Decision, classify, explain
from .config import get_settings
from .db import init_engine, session_scope
from .eve import NormalizedEvent
from .loki_client import LokiClient
from .logging import configure_logging, get_logger
from .models import Filter, FilterAudit
from .retention import retention_loop
from .ring_buffer import RingBuffer
from .routes import events, filters, health, ingest, stats
from .rule_index import RuleIndex

log = get_logger(__name__)


def _run_migrations(db_path: str) -> None:
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def _build_classify(rule_index: RuleIndex, allow_sid_only: bool):
    def _classify(event: NormalizedEvent) -> Decision:
        return classify(event, rule_index.snapshot(), allow_sid_only=allow_sid_only)

    return _classify


def _build_explain(rule_index: RuleIndex, allow_sid_only: bool):
    def _explain(event: NormalizedEvent) -> dict:
        decision, chain = explain(event, rule_index.snapshot(), allow_sid_only=allow_sid_only)
        return {
            "decision": {
                "action": decision.action,
                "filter_id": decision.filter_id,
                "matched_fields": decision.matched_fields,
            },
            "chain": [
                {
                    "filter_id": s.filter_id,
                    "name": s.name,
                    "action": s.action,
                    "matched": s.matched,
                    "matched_fields": s.matched_fields,
                }
                for s in chain
            ],
        }

    return _explain


def _build_on_match():
    """Persist a hit: bump counters on the filter and append an audit row."""

    def _on_match(event: NormalizedEvent, decision: Decision) -> None:
        if decision.filter_id is None:
            return
        now = datetime.now(tz=timezone.utc)
        with session_scope() as session:
            session.execute(
                update(Filter)
                .where(Filter.id == decision.filter_id)
                .values(
                    hit_count=Filter.hit_count + 1,
                    last_seen_at=now,
                    last_matched_event_id=event.event_id,
                )
            )
            session.add(
                FilterAudit(
                    filter_id=decision.filter_id,
                    event_id=event.event_id,
                    decision=decision.action,
                    matched_fields=json.dumps(decision.matched_fields),
                )
            )
            session.commit()

    return _on_match


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info(
        "engine.startup",
        ring_size=settings.ring_size,
        loki_url=settings.loki_url,
        db_path=str(settings.db_path),
    )

    init_engine(settings.db_path)
    try:
        _run_migrations(str(settings.db_path))
    except Exception as exc:  # noqa: BLE001
        log.error("engine.migrations_failed", error=str(exc))
        raise

    rule_index = RuleIndex()
    with session_scope() as session:
        rule_index.rebuild(session)

    app.state.settings = settings
    app.state.ring = RingBuffer(maxlen=settings.ring_size)
    app.state.loki = LokiClient(
        base_url=settings.loki_url,
        tenant=settings.loki_tenant,
        timeout_s=settings.loki_push_timeout_s,
        retry_max=settings.loki_retry_max,
    )
    app.state.rule_index = rule_index
    app.state.classify = _build_classify(rule_index, settings.allow_sid_only)
    app.state.explain = _build_explain(rule_index, settings.allow_sid_only)
    app.state.on_match = _build_on_match()

    stop_event = asyncio.Event()
    retention_task = asyncio.create_task(retention_loop(settings, stop_event))

    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(retention_task, timeout=5)
        except asyncio.TimeoutError:
            retention_task.cancel()
        await app.state.loki.aclose()
        log.info("engine.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Suricata Filter Engine",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(events.router)
    app.include_router(filters.router)
    app.include_router(stats.router)
    return app


app = create_app()
