from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .engine_client import EngineClient
from .logging import configure_logging, get_logger
from .routes import htmx, pages

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("ui.startup", engine=settings.engine_base_url)
    app.state.settings = settings
    app.state.engine = EngineClient(
        base_url=settings.engine_base_url,
        api_token=settings.engine_api_token,
        timeout_s=settings.request_timeout_s,
    )
    app.state.templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    try:
        yield
    finally:
        await app.state.engine.aclose()
        log.info("ui.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="Suricata Filter UI", version="0.1.0", lifespan=lifespan)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(pages.router)
    app.include_router(htmx.router)
    return app


app = create_app()
