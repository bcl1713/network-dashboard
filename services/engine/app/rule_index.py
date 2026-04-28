"""In-memory snapshot of active filters.

The classifier walks this on every event; we rebuild it from the database after
each filter mutation so reads on the hot path don't open SQLite connections.
"""
from __future__ import annotations

from threading import RLock
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Filter


class RuleIndex:
    def __init__(self) -> None:
        self._rules: list[Filter] = []
        self._lock = RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._rules)

    def snapshot(self) -> list[Filter]:
        with self._lock:
            return list(self._rules)

    def replace(self, rules: Iterable[Filter]) -> None:
        with self._lock:
            self._rules = list(rules)

    def rebuild(self, session: Session) -> None:
        rows = session.execute(
            select(Filter).where(Filter.retired == 0).where(Filter.enabled == 1)
        ).scalars().all()
        # Detach so callers can use these without a live session.
        for row in rows:
            session.expunge(row)
        self.replace(rows)
