"""Bounded thread-safe ring of recent normalized events.

Used by:
  * /events/{id} for recent event lookups
  * filter preview to test a draft rule against real recent traffic
"""
from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Iterable, Iterator

from .eve import NormalizedEvent


class RingBuffer:
    def __init__(self, maxlen: int = 750) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self._items: deque[NormalizedEvent] = deque(maxlen=maxlen)
        self._index: dict[str, NormalizedEvent] = {}
        self._lock = RLock()

    @property
    def maxlen(self) -> int:
        return self._items.maxlen or 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def append(self, event: NormalizedEvent) -> None:
        with self._lock:
            if len(self._items) == self._items.maxlen:
                evicted = self._items[0]
                self._index.pop(evicted.event_id, None)
            self._items.append(event)
            self._index[event.event_id] = event

    def get(self, event_id: str) -> NormalizedEvent | None:
        with self._lock:
            return self._index.get(event_id)

    def snapshot(self) -> list[NormalizedEvent]:
        with self._lock:
            return list(self._items)

    def __iter__(self) -> Iterator[NormalizedEvent]:
        return iter(self.snapshot())

    def extend(self, events: Iterable[NormalizedEvent]) -> None:
        for event in events:
            self.append(event)
