"""Recent-event lookup and (Phase 4) why-hidden replay.

Phase 1 supplies the read endpoint backed by the in-memory ring.
why-hidden is wired in Phase 4 once the classifier exists; until then it
returns a 503 explaining the feature is unavailable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..deps import get_ring
from ..security import require_api_token

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(require_api_token)])


def _serialize(event) -> dict:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp.isoformat(),
        "event_type": event.event_type,
        "src_ip": event.src_ip,
        "src_port": event.src_port,
        "dest_ip": event.dest_ip,
        "dest_port": event.dest_port,
        "proto": event.proto,
        "sid": event.sid,
        "generator_id": event.generator_id,
        "signature": event.signature,
        "severity": event.severity,
        "host": event.host,
        "geoip_country": event.geoip_country,
        "geoip_city": event.geoip_city,
        "raw": event.raw,
    }


@router.get("/{event_id}")
async def get_event(event_id: str, request: Request) -> dict:
    ring = get_ring(request)
    event = ring.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found in ring buffer")
    return _serialize(event)


@router.get("/{event_id}/why-hidden")
async def why_hidden(event_id: str, request: Request) -> dict:
    ring = get_ring(request)
    event = ring.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found in ring buffer")

    explain = getattr(request.app.state, "explain", None)
    if explain is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="classifier not loaded; why-hidden requires Phase 2+",
        )
    result = explain(event)
    return {"event_id": event_id, **result}
