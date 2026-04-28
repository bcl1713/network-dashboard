"""Ingest endpoints.

The hot path is intentionally short:

    raw payload  →  eve.normalize  →  ring.append  →  classify  →  loki.push

Phase 1 keeps `classify` as a no-op (action="passthrough"). Phase 2 swaps in
the real classifier from app.classifier without changing this module's shape.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..deps import get_loki, get_ring
from ..eve import NormalizedEvent, normalize
from ..logging import get_logger
from ..security import require_api_token

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(require_api_token)])
log = get_logger(__name__)


async def _process_event(payload: dict[str, Any], request: Request) -> NormalizedEvent:
    event = normalize(payload)
    ring = get_ring(request)
    ring.append(event)

    classify = getattr(request.app.state, "classify", None)
    if classify is not None:
        decision = classify(event)
        action = decision.action
        on_match = getattr(request.app.state, "on_match", None)
        if on_match is not None and decision.filter_id is not None:
            on_match(event, decision)
    else:
        action = "passthrough"

    if action == "hide":
        log.debug("event.hidden", event_id=event.event_id, sid=event.sid)
        return event

    loki = get_loki(request)
    pushed = await loki.push(event, action=action)
    if not pushed:
        log.warning("event.loki_push_failed", event_id=event.event_id)
    return event


@router.post("/event", status_code=status.HTTP_200_OK)
async def ingest_event(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="event payload must be a JSON object")

    event = await _process_event(payload, request)
    return {"event_id": event.event_id, "accepted": True}


@router.post("/bulk", status_code=status.HTTP_200_OK)
async def ingest_bulk(request: Request) -> dict[str, Any]:
    """Accept either a JSON array or NDJSON body."""
    body = await request.body()
    if not body:
        return {"accepted": 0, "event_ids": []}

    payloads: list[dict[str, Any]] = []
    text = body.decode("utf-8", errors="replace").strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"invalid JSON array: {exc}") from exc
        if not isinstance(parsed, list):
            raise HTTPException(status_code=400, detail="bulk array must be a JSON list")
        payloads = [p for p in parsed if isinstance(p, dict)]
    else:
        for lineno, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=400, detail=f"invalid NDJSON on line {lineno}: {exc}"
                ) from exc
            if isinstance(obj, dict):
                payloads.append(obj)

    event_ids: list[str] = []
    for payload in payloads:
        event = await _process_event(payload, request)
        event_ids.append(event.event_id)
    return {"accepted": len(event_ids), "event_ids": event_ids}
