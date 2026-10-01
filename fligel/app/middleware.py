"""Заголовки безопасности для всех ответов.

CSP разрешает загрузку ресурсов только с нашего же сервера: даже если когда-нибудь в интерфейс
попадёт чужой скрипт или картинка, браузер не отправит данные на сторонний сайт (и это же
соблюдает правило 152-ФЗ «никаких внешних CDN и аналитики»). Страница бронирования для гостей
(/book/...) должна встраиваться на сайты клиентов через iframe, поэтому для неё запрет
встраивания не ставится — для всего остального (админка, лендинг, юридические страницы) он включён.
"""
from starlette.datastructures import MutableHeaders

from . import config

CSP_BASE = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'; "
            "object-src 'none'")
HSTS = "max-age=31536000"


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        embeddable = path.startswith("/book/") or path.startswith("/api/public/")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
                if not embeddable:
                    headers.setdefault("X-Frame-Options", "DENY")
                    headers.setdefault("Content-Security-Policy", CSP_BASE + "; frame-ancestors 'none'")
                else:
                    headers.setdefault("Content-Security-Policy", CSP_BASE)
                if config.PUBLIC_BASE_URL.startswith("https://"):
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
