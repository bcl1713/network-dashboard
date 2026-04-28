from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..classifier import _matches
from ..db import get_session
from ..deps import get_ring
from ..models import Filter, FilterAudit
from ..schemas import (
    FilterCreate,
    FilterOut,
    FilterPreviewRequest,
    FilterPreviewResponse,
    FilterPreviewSample,
    FilterUpdate,
    FromEventRequest,
)
from ..security import require_api_token

router = APIRouter(prefix="/filters", tags=["filters"], dependencies=[Depends(require_api_token)])


def _serialize(rule: Filter) -> dict[str, Any]:
    return FilterOut.model_validate(rule).model_dump()


def _apply(payload: FilterCreate | FilterUpdate, rule: Filter) -> None:
    data = payload.model_dump(exclude_unset=False)
    tags = data.pop("tags", None)
    for key, value in data.items():
        if key == "enabled":
            rule.enabled = 1 if value else 0
        else:
            setattr(rule, key, value)
    rule.tags = json.dumps(tags) if tags else None


def _rebuild_index(request: Request, session: Session) -> None:
    index = getattr(request.app.state, "rule_index", None)
    if index is not None:
        index.rebuild(session)


@router.get("")
def list_filters(
    request: Request,
    include_retired: bool = Query(default=False),
    q: str | None = Query(default=None),
    host: str | None = Query(default=None),
    sid: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    stmt = select(Filter)
    if not include_retired:
        stmt = stmt.where(Filter.retired == 0)
    if host:
        stmt = stmt.where(or_(Filter.source_host == host, Filter.source_subnet == host))
    if sid:
        stmt = stmt.where(Filter.sid == sid)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func_lower(Filter.name).like(like),
                func_lower(Filter.description).like(like),
                func_lower(Filter.notes).like(like),
            )
        )
    stmt = stmt.order_by(Filter.id.desc())
    rules = session.execute(stmt).scalars().all()
    return [_serialize(r) for r in rules]


def func_lower(col):
    from sqlalchemy import func

    return func.lower(func.coalesce(col, ""))


@router.post("", status_code=201)
def create_filter(
    request: Request,
    payload: FilterCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rule = Filter(action=payload.action)
    _apply(payload, rule)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    _rebuild_index(request, session)
    return _serialize(rule)


@router.get("/{filter_id}")
def get_filter(filter_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    rule = session.get(Filter, filter_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="filter not found")
    return _serialize(rule)


@router.put("/{filter_id}")
def update_filter(
    request: Request,
    filter_id: int,
    payload: FilterUpdate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rule = session.get(Filter, filter_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="filter not found")
    _apply(payload, rule)
    session.commit()
    session.refresh(rule)
    _rebuild_index(request, session)
    return _serialize(rule)


def _set_lifecycle(
    request: Request,
    filter_id: int,
    session: Session,
    *,
    enabled: int | None = None,
    retired: int | None = None,
) -> dict[str, Any]:
    rule = session.get(Filter, filter_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="filter not found")
    if enabled is not None:
        rule.enabled = enabled
    if retired is not None:
        rule.retired = retired
    session.commit()
    session.refresh(rule)
    _rebuild_index(request, session)
    return _serialize(rule)


@router.post("/{filter_id}/enable")
def enable(filter_id: int, request: Request, session: Session = Depends(get_session)):
    return _set_lifecycle(request, filter_id, session, enabled=1)


@router.post("/{filter_id}/disable")
def disable(filter_id: int, request: Request, session: Session = Depends(get_session)):
    return _set_lifecycle(request, filter_id, session, enabled=0)


@router.post("/{filter_id}/retire")
def retire(filter_id: int, request: Request, session: Session = Depends(get_session)):
    return _set_lifecycle(request, filter_id, session, retired=1, enabled=0)


@router.post("/{filter_id}/unretire")
def unretire(filter_id: int, request: Request, session: Session = Depends(get_session)):
    # Unretire returns to disabled so the operator must consciously re-enable.
    return _set_lifecycle(request, filter_id, session, retired=0, enabled=0)


@router.post("/{filter_id}/duplicate", status_code=201)
def duplicate(
    filter_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    src = session.get(Filter, filter_id)
    if src is None:
        raise HTTPException(status_code=404, detail="filter not found")

    cols = {c.name for c in Filter.__table__.columns}
    skip = {"id", "created_at", "updated_at", "hit_count", "last_seen_at", "last_matched_event_id"}
    data = {c: getattr(src, c) for c in cols if c not in skip}
    data["name"] = f"{src.name} (copy)"
    data["enabled"] = 0
    rule = Filter(**data)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    _rebuild_index(request, session)
    return _serialize(rule)


def _preview_against(rule: Filter, request: Request, limit: int) -> FilterPreviewResponse:
    ring = get_ring(request)
    events = ring.snapshot()
    samples: list[FilterPreviewSample] = []
    match_count = 0
    for ev in events:
        ok, _ = _matches(ev, rule)
        if not ok:
            continue
        match_count += 1
        if len(samples) < limit:
            samples.append(
                FilterPreviewSample(
                    event_id=ev.event_id,
                    timestamp=ev.timestamp,
                    src_ip=ev.src_ip,
                    dest_ip=ev.dest_ip,
                    sid=ev.sid,
                    signature=ev.signature,
                )
            )
    return FilterPreviewResponse(match_count=match_count, scanned=len(events), samples=samples)


@router.post("/{filter_id}/preview")
def preview_saved(
    filter_id: int,
    request: Request,
    body: FilterPreviewRequest | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rule = session.get(Filter, filter_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="filter not found")
    limit = body.limit if body else 20
    return _preview_against(rule, request, limit).model_dump()


@router.post("/preview")
def preview_draft(
    request: Request,
    payload: FilterCreate,
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    """Match a draft (unsaved) filter against the engine ring."""
    rule = Filter(action=payload.action)
    _apply(payload, rule)
    return _preview_against(rule, request, limit).model_dump()


@router.post("/from-event")
def from_event(
    request: Request,
    body: FromEventRequest,
    session: Session = Depends(get_session),  # noqa: ARG001  -- reserved for future use
) -> dict[str, Any]:
    """Suggest a filter draft prefilled from a known recent event."""
    ring = get_ring(request)
    event = ring.get(body.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found in ring buffer")

    draft: dict[str, Any] = {
        "name": body.name or f"Filter from event {body.event_id[:8]}",
        "action": body.action,
        "enabled": True,
        "match_mode": "exact",
    }
    if "source_host" in body.fields and event.src_ip:
        draft["source_host"] = event.src_ip
    if "sid" in body.fields and event.sid is not None:
        draft["sid"] = event.sid
    if "destination" in body.fields and event.dest_ip:
        draft["destination"] = event.dest_ip
    if "destination_port" in body.fields and event.dest_port is not None:
        draft["destination_port"] = event.dest_port
    if "protocol" in body.fields and event.proto:
        draft["protocol"] = event.proto

    if event.signature:
        draft["description"] = event.signature
    return draft


@router.get("/{filter_id}/matches")
def matches(
    filter_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rule = session.get(Filter, filter_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="filter not found")
    rows = session.execute(
        select(FilterAudit)
        .where(FilterAudit.filter_id == filter_id)
        .order_by(FilterAudit.matched_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "event_id": r.event_id,
            "matched_at": (
                r.matched_at.isoformat() if isinstance(r.matched_at, datetime) else str(r.matched_at)
            ),
            "decision": r.decision,
            "matched_fields": json.loads(r.matched_fields or "{}"),
        }
        for r in rows
    ]


_ = status, timezone  # keep imports used
