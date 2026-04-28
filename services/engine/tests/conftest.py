from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test SQLite file so filters don't leak between tests."""
    db_path = tmp_path / "filters.db"
    monkeypatch.setenv("ENGINE_API_TOKEN", "test-token")
    monkeypatch.setenv("ENGINE_DB_PATH", str(db_path))
    monkeypatch.setenv("ENGINE_LOKI_URL", "http://loki.invalid:3100")
    monkeypatch.setenv("ENGINE_LOG_LEVEL", "WARNING")

    from app import config, db

    config.get_settings.cache_clear()
    # Force the SQLAlchemy engine to be re-initialized for the new DB path.
    db._engine = None
    db._SessionLocal = None


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def basic_event() -> dict[str, Any]:
    return json.loads((FIXTURES / "eve_alert_basic.json").read_text())


@pytest.fixture
def dns_event() -> dict[str, Any]:
    return json.loads((FIXTURES / "eve_alert_with_dest.json").read_text())


@pytest.fixture
def stub_loki(monkeypatch: pytest.MonkeyPatch):
    """Patch LokiClient so tests don't touch the network."""
    from app import loki_client

    sent: list[tuple[str, str]] = []

    async def fake_push(self, event, action: str) -> bool:
        sent.append((event.event_id, action))
        return True

    async def fake_ping(self) -> bool:
        return True

    async def fake_aclose(self) -> None:
        return None

    monkeypatch.setattr(loki_client.LokiClient, "push", fake_push)
    monkeypatch.setattr(loki_client.LokiClient, "ping", fake_ping)
    monkeypatch.setattr(loki_client.LokiClient, "aclose", fake_aclose)
    return sent


@pytest.fixture
def client(stub_loki):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        c._sent_to_loki = stub_loki  # type: ignore[attr-defined]
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Token": "test-token"}
