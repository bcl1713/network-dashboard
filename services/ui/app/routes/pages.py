from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..engine_client import EngineError

router = APIRouter()


def _engine(request: Request):
    return request.app.state.engine


def _templates(request: Request):
    return request.app.state.templates


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    engine = _engine(request)
    try:
        stats = await engine.stats()
    except EngineError as exc:
        stats = {"error": str(exc)}
    return _templates(request).TemplateResponse(
        request, "index.html", {"stats": stats}
    )


@router.get("/filters", response_class=HTMLResponse)
async def filters_list(
    request: Request,
    include_retired: bool = Query(default=False),
    q: str | None = Query(default=None),
):
    engine = _engine(request)
    rules = await engine.list_filters(include_retired=include_retired, q=q)
    return _templates(request).TemplateResponse(
        request,
        "filters/list.html",
        {"rules": rules, "include_retired": include_retired, "q": q or ""},
    )


@router.get("/filters/new", response_class=HTMLResponse)
async def filters_new(request: Request, from_event: str | None = Query(default=None)):
    engine = _engine(request)
    draft: dict[str, Any] = {"action": "tag", "match_mode": "exact", "enabled": True}
    if from_event:
        try:
            event = await engine.get_event(from_event)
        except EngineError:
            event = None
        if event:
            try:
                prefill = await engine.from_event(
                    from_event,
                    fields=["source_host", "sid", "destination", "destination_port", "protocol"],
                )
                draft.update(prefill)
                draft["from_event_id"] = from_event
            except EngineError:
                pass
    return _templates(request).TemplateResponse(
        request, "filters/form.html", {"rule": draft, "is_new": True, "errors": None}
    )


@router.post("/filters/new", response_class=HTMLResponse)
async def filters_create(request: Request):
    engine = _engine(request)
    payload = await _read_form(request)
    try:
        created = await engine.create_filter(payload)
    except EngineError as exc:
        return _templates(request).TemplateResponse(
            request,
            "filters/form.html",
            {"rule": payload, "is_new": True, "errors": exc.detail},
            status_code=400,
        )
    return RedirectResponse(url=f"/filters/{created['id']}", status_code=303)


@router.get("/filters/{filter_id}", response_class=HTMLResponse)
async def filters_detail(request: Request, filter_id: int):
    engine = _engine(request)
    try:
        rule = await engine.get_filter(filter_id)
    except EngineError as exc:
        if exc.status_code == 404:
            raise HTTPException(404) from exc
        raise
    matches = await engine.filter_matches(filter_id, limit=50)
    return _templates(request).TemplateResponse(
        request,
        "filters/form.html",
        {"rule": rule, "is_new": False, "errors": None, "matches": matches},
    )


@router.post("/filters/{filter_id}", response_class=HTMLResponse)
async def filters_update(request: Request, filter_id: int):
    engine = _engine(request)
    payload = await _read_form(request)
    try:
        await engine.update_filter(filter_id, payload)
    except EngineError as exc:
        return _templates(request).TemplateResponse(
            request,
            "filters/form.html",
            {"rule": {**payload, "id": filter_id}, "is_new": False, "errors": exc.detail},
            status_code=400,
        )
    return RedirectResponse(url=f"/filters/{filter_id}", status_code=303)


@router.get("/filters/{filter_id}/preview", response_class=HTMLResponse)
async def filters_preview(request: Request, filter_id: int):
    engine = _engine(request)
    rule = await engine.get_filter(filter_id)
    preview = await engine.preview_saved(filter_id, limit=50)
    return _templates(request).TemplateResponse(
        request, "filters/preview.html", {"rule": rule, "preview": preview}
    )


@router.get("/events/{event_id}", response_class=HTMLResponse)
async def events_detail(request: Request, event_id: str):
    engine = _engine(request)
    try:
        event = await engine.get_event(event_id)
    except EngineError as exc:
        if exc.status_code == 404:
            raise HTTPException(404) from exc
        raise
    try:
        why = await engine.why_hidden(event_id)
    except EngineError:
        why = None
    return _templates(request).TemplateResponse(
        request, "events/detail.html", {"event": event, "why": why}
    )


async def _read_form(request: Request) -> dict[str, Any]:
    form = await request.form()
    payload: dict[str, Any] = {}
    for k, v in form.multi_items():
        if v == "":
            continue
        payload[k] = v
    # Booleans
    payload["enabled"] = "enabled" in form
    # Numerics
    for key in ("sid", "generator_id", "destination_port"):
        if key in payload:
            try:
                payload[key] = int(payload[key])
            except (TypeError, ValueError):
                payload.pop(key)
    # Tags as comma-separated text
    tags_raw = payload.pop("tags", None)
    if isinstance(tags_raw, str) and tags_raw.strip():
        payload["tags"] = [t.strip() for t in tags_raw.split(",") if t.strip()]
    # Drop helper-only fields the engine doesn't accept.
    payload.pop("from_event_id", None)
    return payload
