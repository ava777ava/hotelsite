"""Команды администратора сервиса (для вас как владельца платформы, не для клиентов).

Запуск (Docker):  docker compose exec app python -m app.admin <команда>
Без Docker:       python -m app.admin <команда>

  list                              все аккаунты: тариф, статус, оплата, активность
  show <email|id>                   подробности по аккаунту
  suspend <email|id>                приостановить доступ (клиент увидит «Аккаунт приостановлен»)
  activate <email|id>               вернуть доступ
  set-plan <email|id> <тариф> [--paid-until ГГГГ-ММ-ДД]
                                    тарифы: trial, start (до 4 объектов), business (до 15),
                                    pro (до 40), custom (без ограничения)
  reset-password <email>            выдать пользователю новый временный пароль (если не работает почта)
  stats                             общие цифры по сервису

Аккаунт можно указывать email владельца (или любого сотрудника) либо началом id.
"""
import argparse
import secrets
import sys
from datetime import date

from .auth import hash_password
from .db import all_, one, run, tx

PLANS = {"trial": 4, "start": 4, "business": 15, "pro": 40, "custom": 10 ** 6}
PLAN_LABELS = {"trial": "Пробный период", "start": "Старт", "business": "Бизнес", "pro": "Профи", "custom": "Индивидуальный"}


def find_account(conn, key: str) -> dict:
    key = key.strip()
    row = one(conn, "SELECT a.* FROM accounts a JOIN users u ON u.account_id = a.id WHERE lower(u.email) = lower(%s) LIMIT 1",
              (key,))
    if not row and len(key) >= 6:
        rows = all_(conn, "SELECT * FROM accounts WHERE id::text LIKE %s", (key + "%",))
        row = rows[0] if len(rows) == 1 else None
    if not row:
        raise SystemExit(f"Аккаунт «{key}» не найден (укажите email сотрудника или начало id)")
    return row


def list_accounts(conn) -> list[dict]:
    return all_(conn, """
        SELECT a.id, a.name, a.plan, a.status, a.paid_until, a.created_at,
               (SELECT count(*) FROM users u WHERE u.account_id = a.id) AS users,
               (SELECT count(*) FROM properties p WHERE p.account_id = a.id) AS properties,
               (SELECT count(*) FROM rooms r WHERE r.account_id = a.id) AS rooms,
               (SELECT count(*) FROM bookings b WHERE b.account_id = a.id AND b.created_at > now() - interval '30 days') AS bookings_30d,
               (SELECT max(u.last_login_at) FROM users u WHERE u.account_id = a.id) AS last_login,
               (SELECT u.email FROM users u WHERE u.account_id = a.id AND u.role = 'owner' ORDER BY u.created_at LIMIT 1) AS owner_email
        FROM accounts a ORDER BY a.created_at DESC""")


def set_status(conn, key: str, status: str) -> dict:
    acc = find_account(conn, key)
    run(conn, "UPDATE accounts SET status = %s WHERE id = %s", (status, acc["id"]))
    return acc


def set_plan(conn, key: str, plan: str, paid_until: date | None = None) -> dict:
    if plan not in PLANS:
        raise SystemExit(f"Неизвестный тариф «{plan}». Доступны: {', '.join(PLANS)}")
    acc = find_account(conn, key)
    run(conn, "UPDATE accounts SET plan = %s, paid_until = %s WHERE id = %s", (plan, paid_until, acc["id"]))
    return acc


def reset_password(conn, email: str) -> str:
    user = one(conn, "SELECT id FROM users WHERE lower(email) = lower(%s)", (email.strip(),))
    if not user:
        raise SystemExit(f"Пользователь {email} не найден")
    password = secrets.token_urlsafe(9)
    run(conn, "UPDATE users SET password_hash = %s, failed_attempts = 0, locked_until = NULL WHERE id = %s",
        (hash_password(password), user["id"]))
    return password


def stats(conn) -> dict:
    return one(conn, """
        SELECT (SELECT count(*) FROM accounts) AS accounts,
               (SELECT count(*) FROM accounts WHERE status = 'active') AS active,
               (SELECT count(*) FROM accounts WHERE plan = 'trial') AS trial,
               (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM rooms) AS rooms,
               (SELECT count(*) FROM bookings WHERE created_at > now() - interval '30 days') AS bookings_30d""")


def _fmt_dt(v) -> str:
    return v.strftime("%d.%m.%Y %H:%M") if v else "—"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.admin", description="Команды администратора Флигеля")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("stats")
    for name in ("show", "suspend", "activate"):
        sub.add_parser(name).add_argument("account")
    sp = sub.add_parser("set-plan")
    sp.add_argument("account"); sp.add_argument("plan"); sp.add_argument("--paid-until")
    sub.add_parser("reset-password").add_argument("email")
    args = ap.parse_args(argv)
    with tx() as conn:
        if args.cmd == "list":
            rows = list_accounts(conn)
            print(f"{'ID':9} {'Название':26} {'Тариф':10} {'Статус':10} {'Оплачен до':11} {'Польз.':6} {'Номеров':7} {'Брони/30д':9} Последний вход")
            for r in rows:
                print(f"{str(r['id'])[:8]:9} {r['name'][:25]:26} {r['plan']:10} {r['status']:10} "
                      f"{(r['paid_until'].strftime('%d.%m.%Y') if r['paid_until'] else '—'):11} {r['users']:<6} {r['rooms']:<7} "
                      f"{r['bookings_30d']:<9} {_fmt_dt(r['last_login'])}")
            print(f"Всего аккаунтов: {len(rows)}")
        elif args.cmd == "show":
            acc = find_account(conn, args.account)
            info = next(r for r in list_accounts(conn) if r["id"] == acc["id"])
            for k, v in info.items():
                print(f"{k:14}: {_fmt_dt(v) if hasattr(v, 'hour') else v}")
            for u in all_(conn, "SELECT name, email, role, last_login_at FROM users WHERE account_id = %s ORDER BY created_at", (acc["id"],)):
                print(f"  - {u['role']:11} {u['name']} <{u['email']}>, вход: {_fmt_dt(u['last_login_at'])}")
        elif args.cmd in ("suspend", "activate"):
            acc = set_status(conn, args.account, "suspended" if args.cmd == "suspend" else "active")
            print(f"Аккаунт «{acc['name']}»: {'приостановлен' if args.cmd == 'suspend' else 'снова активен'}")
        elif args.cmd == "set-plan":
            paid = date.fromisoformat(args.paid_until) if args.paid_until else None
            acc = set_plan(conn, args.account, args.plan, paid)
            print(f"Аккаунт «{acc['name']}»: тариф {args.plan}" + (f", оплачен до {paid.strftime('%d.%m.%Y')}" if paid else ""))
        elif args.cmd == "reset-password":
            print(f"Новый временный пароль для {args.email}: {reset_password(conn, args.email)}")
            print("Передайте его пользователю и попросите сменить в «Профиле».")
        elif args.cmd == "stats":
            for k, v in stats(conn).items():
                print(f"{k:14}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
