from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC_HTMX = ROOT / "static" / "js" / "htmx.min.js"


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UI_ENGINE_BASE_URL", "http://engine.invalid:8000")
    monkeypatch.setenv("UI_ENGINE_API_TOKEN", "test-token")
    monkeypatch.setenv("UI_LOG_LEVEL", "WARNING")
    from app import config

    config.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _ensure_htmx_stub():
    """The Dockerfile vendors htmx at build time. Tests run from source, so
    drop a tiny stub in place if the file is missing."""
    if not STATIC_HTMX.exists():
        STATIC_HTMX.parent.mkdir(parents=True, exist_ok=True)
        STATIC_HTMX.write_text("// test stub\n")


class FakeEngine:
    """Minimal in-memory engine stub for UI tests."""

    def __init__(self) -> None:
        self.filters: dict[int, dict[str, Any]] = {}
        self.next_id = 1
        self.matches: dict[int, list[dict[str, Any]]] = {}
        self.events: dict[str, dict[str, Any]] = {}
        self._stats = {
            "total_filters": 0,
            "active_filters": 0,
            "retired_filters": 0,
            "total_hits_24h": 0,
            "top_sids": [],
        }

    async def aclose(self) -> None:
        return None

    async def list_filters(self, *, include_retired: bool = False, q: str | None = None):
        rules = list(self.filters.values())
        if not include_retired:
            rules = [r for r in rules if not r.get("retired")]
        return rules

    async def get_filter(self, filter_id: int) -> dict:
        if filter_id not in self.filters:
            from app.engine_client import EngineError

            raise EngineError(404, "not found")
        return self.filters[filter_id]

    async def create_filter(self, payload: dict) -> dict:
        rule = {
            "id": self.next_id,
            "name": payload.get("name", "x"),
            "description": payload.get("description"),
            "enabled": bool(payload.get("enabled", True)),
            "retired": False,
            "action": payload.get("action", "tag"),
            "source_host": payload.get("source_host"),
            "source_subnet": payload.get("source_subnet"),
            "sid": payload.get("sid"),
            "destination": payload.get("destination"),
            "destination_subnet": payload.get("destination_subnet"),
            "destination_port": payload.get("destination_port"),
            "protocol": payload.get("protocol"),
            "message_match": payload.get("message_match"),
            "match_mode": payload.get("match_mode", "exact"),
            "tags": payload.get("tags"),
            "notes": payload.get("notes"),
            "created_at": "2026-04-27T00:00:00",
            "updated_at": "2026-04-27T00:00:00",
            "hit_count": 0,
            "last_seen_at": None,
            "last_matched_event_id": None,
        }
        self.filters[self.next_id] = rule
        self.next_id += 1
        return rule

    async def update_filter(self, filter_id: int, payload: dict) -> dict:
        rule = await self.get_filter(filter_id)
        rule.update(payload)
        return rule

    async def lifecycle(self, filter_id: int, action: str) -> dict:
        rule = await self.get_filter(filter_id)
        if action == "enable":
            rule["enabled"] = True
        elif action == "disable":
            rule["enabled"] = False
        elif action == "retire":
            rule["retired"] = True
            rule["enabled"] = False
        elif action == "unretire":
            rule["retired"] = False
            rule["enabled"] = False
        return rule

    async def duplicate(self, filter_id: int) -> dict:
        rule = await self.get_filter(filter_id)
        copy = dict(rule)
        copy["id"] = self.next_id
        copy["name"] = rule["name"] + " (copy)"
        copy["enabled"] = False
        self.filters[self.next_id] = copy
        self.next_id += 1
        return copy

    async def preview_saved(self, filter_id: int, limit: int = 20):
        return {"match_count": 0, "scanned": 0, "samples": []}

    async def preview_draft(self, payload: dict, limit: int = 20):
        return {"match_count": 0, "scanned": 0, "samples": []}

    async def from_event(self, event_id: str, fields, action: str = "tag"):
        return {"name": "draft", "action": action, "source_host": "10.10.50.42", "sid": 1}

    async def filter_matches(self, filter_id: int, limit: int = 100):
        return self.matches.get(filter_id, [])

    async def get_event(self, event_id: str):
        if event_id not in self.events:
            from app.engine_client import EngineError

            raise EngineError(404, "not found")
        return self.events[event_id]

    async def why_hidden(self, event_id: str):
        return {"event_id": event_id, "decision": {"action": "passthrough", "filter_id": None, "matched_fields": {}}, "chain": []}

    async def stats(self):
        self._stats["total_filters"] = len(self.filters)
        self._stats["active_filters"] = sum(
            1 for r in self.filters.values() if r.get("enabled") and not r.get("retired")
        )
        self._stats["retired_filters"] = sum(1 for r in self.filters.values() if r.get("retired"))
        return self._stats

    async def healthz(self):
        return {"status": "ok"}


@pytest.fixture
def fake_engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def client(fake_engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    def _factory(*args, **kwargs):
        return fake_engine

    monkeypatch.setattr(main, "EngineClient", _factory)
    app = main.create_app()
    with TestClient(app) as c:
        yield c
