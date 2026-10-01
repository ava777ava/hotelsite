"""Дымовая проверка интерфейса в настоящем браузере (необязательная, отдельно от unittest).

Открывает все разделы админки на компьютере и на «телефоне», проверяет, что в консоли нет
ошибок (в том числе нарушений CSP) и что страницы не пустые.

Запуск (сервер с демо-данными уже работает на localhost:8000):
    pip install playwright && playwright install chromium     # один раз, не входит в requirements
    python tests/ui_smoke.py [http://localhost:8000]

Вход: demo@fligel.ru / demo12345 (создаётся командой `python -m app.demo`).
"""
import os
import re
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Нужен playwright: pip install playwright && playwright install chromium")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
ROUTES = ["board", "today", "bookings", "rates", "channels", "expenses", "stats", "notifications", "settings", "help", "profile"]
VIEWPORTS = {"компьютер": {"width": 1366, "height": 850}, "телефон": {"width": 390, "height": 844}}


def check(page, name, problems):
    page.goto(f"{BASE}/app/#/{name}")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(700)
    text = page.inner_text("#app").strip()
    if len(text) < 30:
        problems.append(f"раздел «{name}» пустой")
    # «null», «undefined» или «[object ...]» в тексте страницы — признак забытой проверки в вёрстке
    bad = re.search(r"(^|\s)(null|undefined|NaN)(\s|$)|\[object ", text)
    if bad:
        problems.append(f"раздел «{name}»: в тексте страницы видно «{bad.group(0).strip()}»")


def main() -> int:
    problems: list[str] = []
    with sync_playwright() as p:
        kwargs = {"executable_path": os.environ["PLAYWRIGHT_CHROMIUM"]} if os.environ.get("PLAYWRIGHT_CHROMIUM") else {}
        browser = p.chromium.launch(**kwargs)
        for label, vp in VIEWPORTS.items():
            ctx = browser.new_context(viewport=vp, is_mobile=label == "телефон", has_touch=label == "телефон")
            page = ctx.new_page()
            page.on("pageerror", lambda e, l=label: problems.append(f"[{l}] ошибка скрипта: {e}"))
            page.on("console", lambda m, l=label: problems.append(f"[{l}] консоль: {m.text}") if m.type == "error" else None)
            page.goto(f"{BASE}/app/", wait_until="networkidle")
            page.fill("input[name=email]", "demo@fligel.ru")
            page.fill("input[name=password]", "demo12345")
            page.click("button[type=submit]")
            page.wait_for_timeout(1200)
            for name in ROUTES:
                check(page, name, problems)
            if label == "телефон":
                page.goto(f"{BASE}/app/#/board")
                page.wait_for_timeout(500)
                page.tap(".mobile-nav .more-btn")
                page.wait_for_selector(".more-grid")
            for url in ("/", "/book/demo", "/legal/privacy", "/legal/terms", "/legal/pdn-consent"):
                page.goto(BASE + url, wait_until="networkidle")
            ctx.close()
        browser.close()
    if problems:
        print("ПРОБЛЕМЫ:")
        for pr in problems:
            print(" -", pr)
        return 1
    print("Всё в порядке: разделы открываются на компьютере и телефоне, ошибок в консоли нет.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
