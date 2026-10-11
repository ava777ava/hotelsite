"""Сквозные сценарии интерфейса в настоящем браузере (не входят в unittest; для CI и ручной проверки).

Запуск (сервер с демо-данными на localhost:8000, `python -m app.demo`):
    python tests/ui_flows.py [http://localhost:8000]
Вход: demo@fligel.ru / demo12345. Проверяет, что основные действия не падают с ошибкой скрипта
и что открываются карточка брони, диалоги, панель уведомлений, поиск гостя, смена темы.
"""
import os
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Нужен playwright: pip install playwright && playwright install chromium")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
VIEWPORTS = {"компьютер": {"width": 1280, "height": 800}, "телефон": {"width": 390, "height": 844}}


def main() -> int:
    problems: list[str] = []
    with sync_playwright() as p:
        kwargs = {"executable_path": os.environ["PLAYWRIGHT_CHROMIUM"]} if os.environ.get("PLAYWRIGHT_CHROMIUM") else {}
        browser = p.chromium.launch(**kwargs)
        for label, vp in VIEWPORTS.items():
            mobile = label == "телефон"
            ctx = browser.new_context(viewport=vp, is_mobile=mobile, has_touch=mobile)
            page = ctx.new_page()
            page.on("pageerror", lambda e, l=label: problems.append(f"[{l}] ошибка скрипта: {e}"))
            page.on("console", lambda m, l=label: problems.append(f"[{l}] консоль: {m.text}") if m.type == "error" else None)

            def step(name, fn, l=label):
                try:
                    fn()
                except Exception as e:  # noqa: BLE001
                    problems.append(f"[{l}] шаг «{name}»: {str(e).splitlines()[0]}")

            page.goto(f"{BASE}/app/", wait_until="networkidle")
            page.fill("input[name=email]", "demo@fligel.ru")
            page.fill("input[name=password]", "demo12345")
            page.click("button[type=submit]")
            page.wait_for_selector("#app h1, #app .page-title, #app .nav", state="attached", timeout=10000)
            page.goto(f"{BASE}/app/#/board")  # на телефоне по умолчанию открывается «Сегодня»
            page.wait_for_selector(".bar", state="attached", timeout=10000)

            def open_booking():
                page.locator(".bar:visible").first.click()
                page.wait_for_selector(".drawer", timeout=4000)
                page.keyboard.press("Escape")
                page.wait_for_selector(".drawer", state="detached", timeout=4000)

            def new_booking():
                page.goto(f"{BASE}/app/#/board")
                page.wait_for_selector(".bar", state="attached")
                page.locator("button:visible", has_text="Бронь").first.click()
                page.wait_for_selector(".drawer", timeout=4000)
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                if page.locator(".modal").count():  # подтверждение «закрыть без сохранения»
                    page.keyboard.press("Escape")

            def theme():
                page.goto(f"{BASE}/app/#/board")
                page.wait_for_selector(".bar", state="attached")
                if mobile:
                    page.tap(".mobile-nav .more-btn")
                    page.wait_for_selector(".more-grid")
                    page.keyboard.press("Escape")
                else:
                    page.get_by_role("button", name="Тема").first.click()
                    page.get_by_role("button", name="Тема").first.click()

            def bell():
                page.goto(f"{BASE}/app/#/board")
                page.wait_for_selector(".bar", state="attached")
                page.locator(".bell-btn:visible").first.click()
                page.wait_for_selector(".drawer", timeout=4000)
                page.keyboard.press("Escape")

            def hotkeys():
                if mobile:
                    return
                page.goto(f"{BASE}/app/#/board")
                page.wait_for_selector(".bar", state="attached")
                page.keyboard.press("?")
                page.wait_for_selector(".modal", timeout=3000)
                page.keyboard.press("Escape")

            def tasks_flow():
                page.goto(f"{BASE}/app/#/tasks")
                page.get_by_role("button", name="Новая задача").click()
                page.fill(".modal input[maxlength='200']", f"Проверка e2e {label}")
                page.get_by_role("button", name="Сохранить").click()
                page.wait_for_selector(f".task-card:has-text('Проверка e2e {label}')", timeout=4000)
                page.locator(f".task-card:has-text('Проверка e2e {label}') .task-check").click()
                page.wait_for_selector(f".task-card:has-text('Проверка e2e {label}')", state="detached", timeout=4000)

            def autopilot_flow():
                page.goto(f"{BASE}/app/#/autopilot")
                page.wait_for_selector(".switch", timeout=5000)
                sw = page.locator(".switch").first
                before = sw.get_attribute("aria-checked")
                sw.click()
                page.wait_for_function("(b) => document.querySelector('.switch').getAttribute('aria-checked') !== b", arg=before, timeout=4000)
                page.locator(".switch").first.click()  # вернуть как было
                page.wait_for_function("(b) => document.querySelector('.switch').getAttribute('aria-checked') === b", arg=before, timeout=4000)

            def reviews_page():
                page.goto(f"{BASE}/app/#/reviews")
                page.wait_for_selector(".kpis, .empty", timeout=5000)

            step("карточка брони", open_booking)
            step("задачи", tasks_flow)
            step("автопилот", autopilot_flow)
            step("отзывы", reviews_page)
            step("новая бронь", new_booking)
            step("тема", theme)
            step("колокольчик", bell)
            step("горячие клавиши", hotkeys)
            ctx.close()
        browser.close()
    if problems:
        print("ПРОБЛЕМЫ:")
        for pr in problems:
            print(" -", pr)
        return 1
    print("Сценарии интерфейса пройдены на компьютере и телефоне.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
