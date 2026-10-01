"""Точка входа: uvicorn app.main:app"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import config, db, sync
from .api import account, bookings, channels, expenses, incomes, public, reports
from .api import telegram as telegram_api
from .middleware import SecurityHeaders
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


def landing_page(request: Request):
    return FileResponse(STATIC / "landing" / "index.html")


def legal_page(name: str):
    def handler(request: Request):
        return FileResponse(STATIC / "legal" / f"{name}.html")
    return handler


def favicon(request: Request):
    return FileResponse(STATIC / "icons" / "icon.svg", media_type="image/svg+xml")


def robots(request: Request):
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /app/\nDisallow: /api/\nDisallow: /ical/\n"
        f"Sitemap: {config.PUBLIC_BASE_URL}/sitemap.xml\n")


def sitemap(request: Request):
    urls = ["/", "/legal/privacy", "/legal/pdn-consent", "/legal/terms"]
    body = "".join(f"<url><loc>{config.PUBLIC_BASE_URL}{u}</loc></url>" for u in urls)
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"{body}</urlset>", media_type="application/xml")


def manifest(request: Request):
    return Json({
        "name": "Флигель — управление бронированиями", "short_name": "Флигель", "lang": "ru",
        "start_url": "/app/", "scope": "/", "display": "standalone", "background_color": "#1C2420",
        "theme_color": "#1C2420",
        "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    }, media_type="application/manifest+json")


async def not_found(request: Request, exc: StarletteHTTPException):
    """Понятная страница 404 для людей и JSON для программ (API, календари)."""
    if exc.status_code == 404 and not request.url.path.startswith(("/api/", "/ical/", "/static/")):
        return FileResponse(STATIC / "404.html", status_code=404)
    return Json({"error": "Не найдено" if exc.status_code == 404 else (exc.detail or "Ошибка")},
                status_code=exc.status_code)


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
    Route("/", landing_page),
    Route("/app", lambda r: RedirectResponse("/app/")),
    Route("/app/", admin_page),
    Route("/book/{slug}", booking_page),
    Route("/legal/privacy", legal_page("privacy")),
    Route("/legal/pdn-consent", legal_page("pdn-consent")),
    Route("/legal/terms", legal_page("terms")),
    Route("/health", health),
    Route("/favicon.ico", favicon),
    Route("/robots.txt", robots),
    Route("/sitemap.xml", sitemap),
    Route("/manifest.webmanifest", manifest),
    *account.routes,
    *bookings.routes,
    *channels.routes,
    *expenses.routes,
    *incomes.routes,
    *reports.routes,
    *public.routes,
    *telegram_api.routes,
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
]

app = Starlette(routes=routes, lifespan=lifespan, exception_handlers={StarletteHTTPException: not_found}, middleware=[Middleware(SecurityHeaders), Middleware(GZipMiddleware, minimum_size=1000)])
