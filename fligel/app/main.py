"""Точка входа: uvicorn app.main:app"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import config, db, sync
from .api import account, bookings, channels, expenses, public, reports
from .migrate import migrate
from .sync import Scheduler
from .util import Json

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC = Path(__file__).resolve().parent / "static"


def admin_page(request: Request):
    return FileResponse(STATIC / "admin" / "index.html")


def booking_page(request: Request):
    return FileResponse(STATIC / "book" / "index.html")


def health(request: Request):
    """Для мониторинга и docker-compose healthcheck: проверяет БД и живость планировщика
    синхронизации площадок (не завис ли фоновый поток). Отдаёт 503, если что-то не так —
    monitoring и Docker понимают только код ответа, поэтому он должен быть верным."""
    try:
        with db.tx() as conn:
            db.one(conn, "SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    scheduler_ok = sync.scheduler_alive()
    body = {"ok": db_ok and scheduler_ok, "db": db_ok,
            "scheduler": scheduler_ok if config.SYNC_ENABLED else None}
    return Json(body, status_code=200 if body["ok"] else 503)


@asynccontextmanager
async def lifespan(app: Starlette):
    if config.SECRET_KEY == "dev-secret-change-me" and not config.PUBLIC_BASE_URL.startswith("http://localhost"):
        raise RuntimeError("Задайте SECRET_KEY в .env перед запуском на сервере")
    if os.environ.get("AUTO_MIGRATE", "1") == "1":
        migrate()
    db.init_pool()
    scheduler = Scheduler() if config.SYNC_ENABLED else None
    if scheduler:
        scheduler.start()
    yield
    if scheduler:
        scheduler.stop()
    db.close_pool()


routes = [
    Route("/", lambda r: RedirectResponse("/app/")),
    Route("/app", lambda r: RedirectResponse("/app/")),
    Route("/app/", admin_page),
    Route("/book/{slug}", booking_page),
    Route("/health", health),
    *account.routes,
    *bookings.routes,
    *channels.routes,
    *expenses.routes,
    *reports.routes,
    *public.routes,
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
]

app = Starlette(routes=routes, lifespan=lifespan, middleware=[Middleware(GZipMiddleware, minimum_size=1000)])
