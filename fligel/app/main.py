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
from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import blog, config, db, sync
from .api import account, analytics, integrations, v1 as v1_api, demo as demo_api, billing as billing_api, operator as operator_api, autopilot, autoprice as autoprice_api, bookings, channels, expenses, guestpages, guests, household as household_api, housekeeping, incomes, money, notify as notify_api, owners, photos, public, reports, tariffs, tasks
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


def guest_page(request: Request):
    """Анкета (/f/<токен>) и отзыв (/r/<токен>) — одна страница, тип определяет скрипт по адресу."""
    return FileResponse(STATIC / "guest" / "index.html", headers={"Referrer-Policy": "no-referrer"})


def api_docs(request: Request):
    return FileResponse(STATIC / "docs" / "api.html")


def blog_index(request: Request):
    return HTMLResponse(blog.index_html())


def blog_article(request: Request):
    html = blog.article_html(request.path_params["slug"])
    if html is None:
        raise StarletteHTTPException(404)
    return HTMLResponse(html)


def operator_page(request: Request):
    return FileResponse(STATIC / "operator" / "index.html", headers={"Cache-Control": "no-store"})


def legal_page(name: str):
    def handler(request: Request):
        return FileResponse(STATIC / "legal" / f"{name}.html")
    return handler


def service_worker(request: Request):
    """Скрипт офлайн-режима. Лежит в корне сайта, чтобы управлять всем приложением; кэшировать его самого нельзя."""
    return FileResponse(STATIC / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


def favicon(request: Request):
    return FileResponse(STATIC / "icons" / "icon.svg", media_type="image/svg+xml")


def robots(request: Request):
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /app/\nDisallow: /api/\nDisallow: /ical/\nDisallow: /f/\nDisallow: /r/\nDisallow: /operator/\n"
        f"Sitemap: {config.PUBLIC_BASE_URL}/sitemap.xml\n")


def sitemap(request: Request):
    urls = ["/", "/api/docs", *blog.sitemap_urls(), "/legal/privacy", "/legal/pdn-consent", "/legal/terms"]
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


def _backup_check() -> dict | None:
    """Результат еженедельной проверки восстановления бэкапа (deploy/verify_backup.sh). Информационное поле: на статус «здоров» не влияет —
    но если проверка не проходила дольше 10 дней или упала, `stale`/`ok` покажут это при просмотре /health."""
    import json
    from datetime import datetime, timezone
    try:
        with db.tx() as conn:
            row = db.one(conn, "SELECT value FROM service_state WHERE key = 'backup_check'")
        if not row:
            return {"ok": None, "stale": True, "message": "проверка бэкапа ещё не выполнялась"}
        data = json.loads(row["value"])
        at = datetime.fromisoformat(data["at"].replace("Z", "+00:00"))
        data["age_days"] = (datetime.now(timezone.utc) - at).days
        data["stale"] = data["age_days"] > 10
        return data
    except Exception:
        return None


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
            "scheduler": scheduler_ok if config.SYNC_ENABLED else None, "backup_check": _backup_check() if db_ok else None}
    return Json(body, status_code=200 if body["ok"] else 503)


@asynccontextmanager
async def lifespan(app: Starlette):
    if not config.PUBLIC_BASE_URL.startswith(("http://localhost", "http://127.0.0.1")) and (
            config.SECRET_KEY == "dev-secret-change-me" or len(config.SECRET_KEY) < 24):
        raise RuntimeError("Задайте SECRET_KEY в .env (длинная случайная строка, не короче 24 символов) перед запуском на сервере")
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
    Route("/api/docs", api_docs),
    Route("/blog/", blog_index),
    Route("/blog", lambda r: RedirectResponse("/blog/")),
    Route("/blog/{slug}", blog_article),
    Route("/operator/", operator_page),
    Route("/operator", lambda r: RedirectResponse("/operator/")),
    Route("/f/{token}", guest_page),
    Route("/r/{token}", guest_page),
    Route("/legal/privacy", legal_page("privacy")),
    Route("/legal/pdn-consent", legal_page("pdn-consent")),
    Route("/legal/terms", legal_page("terms")),
    Route("/health", health),
    Route("/favicon.ico", favicon),
    Route("/sw.js", service_worker),
    Route("/robots.txt", robots),
    Route("/sitemap.xml", sitemap),
    Route("/manifest.webmanifest", manifest),
    *account.routes,
    *integrations.routes,
    *v1_api.routes,
    *demo_api.routes,
    *billing_api.routes,
    *operator_api.routes,
    *analytics.routes,
    *autopilot.routes,
    *autoprice_api.routes,
    *bookings.routes,
    *channels.routes,
    *expenses.routes,
    *guestpages.routes,
    *guests.routes,
    *household_api.routes,
    *housekeeping.routes,
    *incomes.routes,
    *money.routes,
    *notify_api.routes,
    *owners.routes,
    *photos.routes,
    *reports.routes,
    *tariffs.routes,
    *tasks.routes,
    *public.routes,
    *telegram_api.routes,
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
]

app = Starlette(routes=routes, lifespan=lifespan, exception_handlers={StarletteHTTPException: not_found}, middleware=[Middleware(SecurityHeaders), Middleware(GZipMiddleware, minimum_size=1000)])
