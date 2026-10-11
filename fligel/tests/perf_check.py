"""Замеры скорости на большом объёме данных (не входит в unittest).

1) Создайте нагрузочные данные:  python -m app.demo_load --rooms 500 --years 3   (в отдельной базе)
2) Запустите сервер на этой базе и выполните:  python tests/perf_check.py http://localhost:8000 [--budget 3.0]
Входит как loadtest@fligel.ru / loadtest12345. Для каждого запроса — медиана из трёх замеров; при --budget код возврата 1,
если что-то медленнее бюджета (секунд)."""
import statistics
import sys
import time

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "http://localhost:8000").rstrip("/")
BUDGET = float(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else None


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=60)
    tok = c.post("/api/auth/login", json={"email": "loadtest@fligel.ru", "password": "loadtest12345"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    me = c.get("/api/me", headers=h).json()
    prop = me["properties"][0]["id"]
    from datetime import date, timedelta
    today = date.today()
    first = today.replace(day=1)
    checks = [
        ("Шахматка, 2 недели", f"/api/board?property_id={prop}&from={today - timedelta(days=2)}&days=14"),
        ("Шахматка, месяц", f"/api/board?property_id={prop}&from={today - timedelta(days=2)}&days=31"),
        ("Шахматка, 3 месяца", f"/api/board?property_id={prop}&from={today - timedelta(days=2)}&days=92"),
        ("Сегодня + сводка владельца", f"/api/today?property_id={prop}&summary=1"),
        ("Список броней (месяц)", f"/api/bookings?from={first}&to={today + timedelta(days=31)}"),
        ("Отчёт за месяц", f"/api/reports?from={first}&to={today + timedelta(days=1)}"),
        ("Отчёт за 12 месяцев", f"/api/reports?from={today - timedelta(days=365)}&to={today + timedelta(days=1)}"),
        ("Аналитика: прогноз 30/60/90", "/api/analytics/forecast"),
        ("Аналитика: темп", "/api/analytics/pace"),
        ("Аналитика: окно брони (90 дн.)", "/api/analytics/lead-time"),
        ("Аналитика: каналы", "/api/analytics/channels"),
        ("Бухгалтеру за месяц", f"/api/analytics/accountant?from={first}&to={today + timedelta(days=1)}"),
        ("Уборка (500 номеров)", f"/api/housekeeping?property_id={prop}"),
        ("Поиск гостя по телефону", "/api/guests/list?q=900"),
        ("Автоцены (расчёт на 60 дней)", "/api/autoprice/preview"),
        ("Кол-во в меню (badges)", "/api/badges"),
    ]
    rows, slow = [], []
    for name, path in checks:
        times, size, status = [], 0, 0
        for _ in range(3):
            t0 = time.monotonic()
            r = c.get(path, headers=h)
            times.append(time.monotonic() - t0)
            size, status = len(r.content), r.status_code
        med = statistics.median(times)
        rows.append((name, status, med, size))
        if status >= 400 or (BUDGET and med > BUDGET):
            slow.append(name)
    w = max(len(r[0]) for r in rows)
    print(f"{'Запрос':{w}}  код  медиана, с  размер ответа")
    for name, status, med, size in rows:
        print(f"{name:{w}}  {status}  {med:9.3f}  {size / 1024:8.0f} КБ{'   <-- медленно' if name in slow else ''}")
    if slow:
        print("\nПроблемные:", ", ".join(slow))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
