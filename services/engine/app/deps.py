"""FastAPI dependency providers.

The actual instances live on `app.state` (set up in main.lifespan); these
helpers expose them via Depends() so route modules don't import the FastAPI
app object directly.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from .config import Settings, get_settings as _get_settings

if TYPE_CHECKING:
    from .loki_client import LokiClient
    from .ring_buffer import RingBuffer


def get_settings() -> Settings:
    return _get_settings()


def get_ring(request: Request) -> "RingBuffer":
    return request.app.state.ring


def get_loki(request: Request) -> "LokiClient":
    return request.app.state.loki
