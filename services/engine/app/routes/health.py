from fastapi import APIRouter, Depends

from ..deps import get_loki

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(loki=Depends(get_loki)) -> dict[str, object]:
    loki_ok = await loki.ping()
    return {"status": "ok" if loki_ok else "degraded", "loki": loki_ok}
