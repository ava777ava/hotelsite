"""Применяет SQL-миграции из app/migrations по порядку. Запуск: python -m app.migrate"""
from pathlib import Path

import psycopg

from . import config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def migrate(url: str | None = None) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(url or config.DATABASE_URL, autocommit=False) as conn:
        with conn.cursor() as cur:
            # Не даём двум экземплярам приложения мигрировать одновременно.
            # Лок берём до CREATE TABLE: иначе параллельные `CREATE TABLE IF NOT EXISTS`
            # от нескольких воркеров uvicorn падают гонкой в системном каталоге Postgres.
            cur.execute("SELECT pg_advisory_xact_lock(724501)")
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            cur.execute("SELECT name FROM schema_migrations")
            done = {r[0] for r in cur.fetchall()}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in done:
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
                applied.append(path.name)
        conn.commit()
    return applied


if __name__ == "__main__":
    names = migrate()
    print("Применены миграции: " + ", ".join(names) if names else "База уже в актуальном состоянии")
