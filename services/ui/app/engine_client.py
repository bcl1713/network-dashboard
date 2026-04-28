"""Thin async wrapper around the engine REST API.

All errors propagate as `EngineError` so the UI can show a flash without
crashing. The token is attached on construction.
"""
from __future__ import annotations

from typing import Any

import httpx


class EngineError(RuntimeError):
    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(f"engine error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class EngineClient:
    def __init__(self, base_url: str, api_token: str, timeout_s: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            headers={"X-API-Token": api_token},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kw) -> Any:
        r = await self._client.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except ValueError:
                detail = r.text
            raise EngineError(r.status_code, detail)
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    # ---------- filters ----------

    async def list_filters(self, *, include_retired: bool = False, q: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"include_retired": str(include_retired).lower()}
        if q:
            params["q"] = q
        return await self._request("GET", "/filters", params=params)

    async def get_filter(self, filter_id: int) -> dict:
        return await self._request("GET", f"/filters/{filter_id}")

    async def create_filter(self, payload: dict) -> dict:
        return await self._request("POST", "/filters", json=payload)

    async def update_filter(self, filter_id: int, payload: dict) -> dict:
        return await self._request("PUT", f"/filters/{filter_id}", json=payload)

    async def lifecycle(self, filter_id: int, action: str) -> dict:
        return await self._request("POST", f"/filters/{filter_id}/{action}")

    async def duplicate(self, filter_id: int) -> dict:
        return await self._request("POST", f"/filters/{filter_id}/duplicate")

    async def preview_saved(self, filter_id: int, limit: int = 20) -> dict:
        return await self._request("POST", f"/filters/{filter_id}/preview", json={"limit": limit})

    async def preview_draft(self, payload: dict, limit: int = 20) -> dict:
        return await self._request(
            "POST", "/filters/preview", json=payload, params={"limit": limit}
        )

    async def from_event(self, event_id: str, fields: list[str], action: str = "tag") -> dict:
        return await self._request(
            "POST",
            "/filters/from-event",
            json={"event_id": event_id, "fields": fields, "action": action},
        )

    async def filter_matches(self, filter_id: int, limit: int = 100) -> list[dict]:
        return await self._request(
            "GET", f"/filters/{filter_id}/matches", params={"limit": limit}
        )

    # ---------- events ----------

    async def get_event(self, event_id: str) -> dict:
        return await self._request("GET", f"/events/{event_id}")

    async def why_hidden(self, event_id: str) -> dict:
        return await self._request("GET", f"/events/{event_id}/why-hidden")

    # ---------- stats / health ----------

    async def stats(self) -> dict:
        return await self._request("GET", "/stats/filters")

    async def healthz(self) -> dict:
        return await self._request("GET", "/healthz")
