"""Сквозные сценарии «как человек» в настоящем браузере (для CI и ручной проверки).

Запуск (чистая база, сервер на localhost:8000):  python tests/e2e.py [http://localhost:8000]

1) Владелец: регистрация → создание объекта → бронь с оплатой → отчёт показывает выручку → шахматка не даёт занять тот же номер.
2) Гость: страница бронирования → заявка → администратор видит заявку и подтверждает → бронь в шахматке подтверждена.
Каждый сценарий — на компьютере (1280 px) и на телефоне (390 px)."""
import os
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Нужен playwright: pip install playwright && playwright install chromium")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
VIEWPORTS = {"компьютер": {"width": 1280, "height": 800}, "телефон": {"width": 390, "height": 844}}


def scenario(browser, label, vp, problems):
    mobile = label == "телефон"
    stamp = f"{int(time.time())}{'m' if mobile else 'd'}"
    email, password = f"e2e{stamp}@example.ru", "e2e-password-1"
    ctx = browser.new_context(viewport=vp, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    page.on("pageerror", lambda e: problems.append(f"[{label}] ошибка скрипта: {e}"))
    page.on("console", lambda m: problems.append(f"[{label}] консоль: {m.text}") if m.type == "error" else None)

    def step(name):
        print(f"  [{label}] {name}")

    # ---- 1. владелец ----
    step("регистрация")
    page.goto(f"{BASE}/app/#register", wait_until="networkidle")
    page.fill("input[name=account_name]", f"Отель E2E {stamp}")
    page.fill("input[name=name]", "Ирина Тестова")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_selector("text=Добавим ваш объект", timeout=10000)

    step("создание объекта")
    page.get_by_role("button", name="Создать шахматку").click()
    page.wait_for_selector(".bar, .b-cell, .board", state="attached", timeout=10000)
    # приветственные экраны (один раз) — пропускаем
    try:
        page.get_by_role("button", name="Пропустить").click(timeout=3000)
    except Exception:  # noqa: BLE001
        pass

    step("бронь с оплатой")
    page.goto(f"{BASE}/app/#/board")
    page.wait_for_selector(".b-cell", state="attached", timeout=10000)
    page.locator("button:visible", has_text="Бронь").first.click()
    page.wait_for_selector(".drawer", timeout=5000)
    drawer = page.locator(".drawer")
    drawer.locator("label:has-text('Гость') input").first.fill("Анна Гостева")
    drawer.locator("input[type=tel]").fill("9001112233")
    drawer.get_by_role("button", name="Оплачено полностью").click()
    drawer.get_by_role("button", name="Создать").click()
    page.wait_for_selector(".drawer", state="detached", timeout=8000)
    page.wait_for_selector(".bar:has-text('Анна')", state="attached", timeout=8000)

    step("отчёт показывает выручку")
    page.goto(f"{BASE}/app/#/stats")
    page.wait_for_selector(".kpis", timeout=10000)
    body = page.inner_text("#app").replace("\xa0", " ").replace("\u202f", " ")
    if "Выручка" not in body:
        problems.append(f"[{label}] в отчёте нет блока «Выручка»")
    if "3 500" not in body and "3500" not in body:
        problems.append(f"[{label}] в отчёте не видна сумма брони 3 500 ₽")

    step("тот же номер занять нельзя")
    r = page.request.get(f"{BASE}/api/me", headers={"Authorization": "Bearer " + page.evaluate("localStorage.getItem('token')")})
    if r.status != 200:
        problems.append(f"[{label}] /api/me вернул {r.status}")
    token = page.evaluate("localStorage.getItem('token')")
    hdr = {"Authorization": f"Bearer {token}"}
    board = page.request.get(f"{BASE}/api/board", headers=hdr).json()
    booking = board["bookings"][0]
    again = page.request.post(f"{BASE}/api/bookings", headers=hdr, data={"room_id": booking["room_id"], "check_in": booking["check_in"], "check_out": booking["check_out"], "guest_name": "Дубль"})
    if again.status != 409:
        problems.append(f"[{label}] двойная бронь не отклонена: {again.status}")

    # ---- 2. гость ----
    step("гость: заявка на странице бронирования")
    slug = page.request.get(f"{BASE}/api/me", headers=hdr).json()["properties"][0]["public_slug"]
    guest = browser.new_context(viewport=vp, is_mobile=mobile, has_touch=mobile).new_page()
    guest.on("pageerror", lambda e: problems.append(f"[{label}/гость] ошибка скрипта: {e}"))
    guest.goto(f"{BASE}/book/{slug}?lang=ru", wait_until="networkidle")
    guest.wait_for_selector(".opt .btn", timeout=10000)
    guest.locator(".opt .btn").first.click()
    guest.fill("input[name=guest_name]", "Пётр Приезжий")
    guest.fill("input[name=guest_phone]", "9003334455")
    guest.check("input[name=consent]")
    guest.click("#bf button[type=submit]")
    guest.wait_for_selector("text=Заявка отправлена", timeout=8000)

    step("администратор подтверждает заявку")
    page.goto(f"{BASE}/app/#/bookings")
    page.wait_for_selector("text=Приезжий", timeout=10000)
    page.get_by_role("button", name="Подтвердить").first.click()
    page.wait_for_timeout(1200)
    from datetime import date, timedelta
    span = f"from={date.today() - timedelta(days=30)}&to={date.today() + timedelta(days=60)}"
    after = page.request.get(f"{BASE}/api/bookings?{span}", headers=hdr).json()
    mine = [b for b in after if b["guest_name"] == "Пётр Приезжий"]
    if not mine or mine[0]["status"] != "confirmed":
        problems.append(f"[{label}] заявка гостя не подтвердилась: {[b['status'] for b in mine]}")
    ctx.close()


def main() -> int:
    problems: list[str] = []
    with sync_playwright() as p:
        kwargs = {"executable_path": os.environ["PLAYWRIGHT_CHROMIUM"]} if os.environ.get("PLAYWRIGHT_CHROMIUM") else {}
        browser = p.chromium.launch(**kwargs)
        for label, vp in VIEWPORTS.items():
            try:
                scenario(browser, label, vp, problems)
            except Exception as e:  # noqa: BLE001
                problems.append(f"[{label}] сценарий прерван: {str(e).splitlines()[0]}")
        browser.close()
    if problems:
        print("ПРОБЛЕМЫ:")
        for pr in problems:
            print(" -", pr)
        return 1
    print("Сквозные сценарии пройдены на компьютере и телефоне.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
