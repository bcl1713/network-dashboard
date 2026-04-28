from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Filter, FilterAudit
from .schemas import StatsResponse, StatsRow


def collect_stats(session: Session, *, top_n: int = 10) -> StatsResponse:
    total = session.scalar(select(func.count(Filter.id))) or 0
    active = session.scalar(
        select(func.count(Filter.id)).where(Filter.retired == 0).where(Filter.enabled == 1)
    ) or 0
    retired = session.scalar(select(func.count(Filter.id)).where(Filter.retired == 1)) or 0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    hits_24h = session.scalar(
        select(func.count(FilterAudit.id)).where(FilterAudit.matched_at >= cutoff_str)
    ) or 0

    rows = session.execute(
        select(Filter.sid, func.count(FilterAudit.id), func.max(FilterAudit.matched_at))
        .join(FilterAudit, FilterAudit.filter_id == Filter.id)
        .where(FilterAudit.matched_at >= cutoff_str)
        .group_by(Filter.sid)
        .order_by(func.count(FilterAudit.id).desc())
        .limit(top_n)
    ).all()

    top = [
        StatsRow(
            sid=sid,
            hits_24h=hits,
            last_seen_at=_parse_dt(last_seen),
        )
        for sid, hits, last_seen in rows
    ]

    return StatsResponse(
        total_filters=total,
        active_filters=active,
        retired_filters=retired,
        total_hits_24h=hits_24h,
        top_sids=top,
    )


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
