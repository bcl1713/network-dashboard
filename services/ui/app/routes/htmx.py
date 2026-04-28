"""HTMX fragment routes.

These return small HTML snippets that swap into existing pages without a
full reload. Keep them tiny -- the page route renders the surrounding
chrome on first load.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/htmx", include_in_schema=False)


def _engine(request: Request):
    return request.app.state.engine


def _templates(request: Request):
    return request.app.state.templates


@router.post("/filters/{filter_id}/lifecycle", response_class=HTMLResponse)
async def lifecycle(request: Request, filter_id: int) -> HTMLResponse:
    form = await request.form()
    action = form.get("action", "disable")
    if action not in {"enable", "disable", "retire", "unretire"}:
        return HTMLResponse("invalid action", status_code=400)
    engine = _engine(request)
    rule = await engine.lifecycle(filter_id, action)
    return _templates(request).TemplateResponse(
        request, "filters/_row.html", {"rule": rule}
    )


@router.post("/filters/{filter_id}/duplicate", response_class=HTMLResponse)
async def duplicate(request: Request, filter_id: int) -> HTMLResponse:
    engine = _engine(request)
    rule = await engine.duplicate(filter_id)
    return _templates(request).TemplateResponse(
        request, "filters/_row.html", {"rule": rule}
    )


@router.post("/filters/preview", response_class=HTMLResponse)
async def preview_draft(request: Request) -> HTMLResponse:
    """Run a draft preview from the create/edit form. Body is form-encoded."""
    form = await request.form()
    payload: dict = {}
    for key in (
        "name",
        "action",
        "match_mode",
        "source_host",
        "source_subnet",
        "destination",
        "destination_subnet",
        "protocol",
        "message_match",
    ):
        v = form.get(key)
        if v:
            payload[key] = v
    for key in ("sid", "generator_id", "destination_port"):
        v = form.get(key)
        if v:
            try:
                payload[key] = int(v)
            except ValueError:
                continue
    payload.setdefault("name", "draft")
    payload.setdefault("action", "tag")
    payload.setdefault("match_mode", "exact")
    payload["enabled"] = True

    engine = _engine(request)
    try:
        result = await engine.preview_draft(payload, limit=20)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(f"<div class='error'>preview failed: {exc}</div>", status_code=400)
    return _templates(request).TemplateResponse(
        request, "filters/_preview_results.html", {"preview": result, "rule": payload}
    )
