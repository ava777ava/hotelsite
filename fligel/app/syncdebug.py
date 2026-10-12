"""Отладка и состояние синхронизации площадок.

* Сырые календари: последние SNAPSHOTS_KEEP штук для каждой площадки/номера — и то, что мы забрали у площадки (received),
  и то, что отдали ей мы (served). Одинаковый календарь второй раз не копируется — растёт счётчик. Нужно, чтобы разбирать
  реальные форматы Авито, Яндекса и других. Включено по умолчанию (accounts.sync_debug), хранится не дольше SNAPSHOTS_DAYS дней
  и показывается только владельцу: в календаре могут быть имена гостей.
* Состояние: когда забрали календарь площадки, когда площадка забирала наш, сколько событий, сколько «эхо» отброшено, ошибки.
* Предупреждение, если площадка не забирала наш календарь дольше STALE_EXPORT_HOURS часов."""
import hashlib
import logging

from . import notify
from .db import all_, one, run, tx

log = logging.getLogger("fligel.syncdebug")

SNAPSHOTS_KEEP = 10
SNAPSHOTS_DAYS = 14
MAX_BODY = 2 * 1024 * 1024
STALE_EXPORT_HOURS = 6


def debug_enabled(conn, account_id) -> bool:
    row = one(conn, "SELECT sync_debug FROM accounts WHERE id = %s", (account_id,))
    return bool(row and row["sync_debug"])


def save(conn, account_id, kind: str, channel: str, body: str, *, feed_id=None, target_id=None, events: int = 0,
         status: str = "ok", note: str = "", user_agent: str = "", hash_source: str | None = None) -> None:
    """Запоминает сырой календарь (если включён режим отладки). Вызывать внутри транзакции."""
    if not debug_enabled(conn, account_id):
        return
    if len(body) > MAX_BODY:
        body, note = body[:MAX_BODY], (note + " Календарь обрезан до 2 МБ.").strip()
    digest = hashlib.sha256((hash_source if hash_source is not None else body).encode("utf-8", "replace")).hexdigest()
    key, key_params = ("feed_id = %s", (feed_id,)) if kind == "received" else ("target_id = %s AND channel = %s", (target_id, channel))
    last = one(conn, f"SELECT id, body_hash, status FROM ical_snapshots WHERE kind = %s AND {key} ORDER BY created_at DESC, id DESC LIMIT 1",
               (kind, *key_params))
    if last and last["body_hash"] == digest and last["status"] == status:
        run(conn, "UPDATE ical_snapshots SET last_seen_at = now(), seen_count = seen_count + 1, user_agent = %s WHERE id = %s",
            (user_agent[:300] or "", last["id"]))
        return
    run(conn, "INSERT INTO ical_snapshots (account_id, kind, feed_id, target_id, channel, body, body_hash, size, events, status, note, user_agent)"
              " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (account_id, kind, feed_id, target_id, channel, body, digest, len(body.encode("utf-8", "replace")), events, status, note[:500], user_agent[:300]))
    run(conn, f"DELETE FROM ical_snapshots WHERE kind = %s AND {key} AND id NOT IN ("
              f"SELECT id FROM ical_snapshots WHERE kind = %s AND {key} ORDER BY created_at DESC, id DESC LIMIT %s)",
        (kind, *key_params, kind, *key_params, SNAPSHOTS_KEEP))


def purge_old() -> int:
    with tx() as conn:
        return run(conn, "DELETE FROM ical_snapshots WHERE created_at < now() - make_interval(days => %s)", (SNAPSHOTS_DAYS,)) or 0


def state(conn, account_id) -> list[dict]:
    """Одна строка на каждый подключённый календарь площадки: что мы у неё забрали и когда она забирала наш."""
    rows = all_(conn,
        "SELECT f.id AS feed_id, f.channel, f.enabled, f.created_at AS connected_at, f.last_synced_at, f.last_status, f.last_error,"
        " coalesce(f.room_id, f.room_type_id) AS target_id, f.room_type_id IS NOT NULL AS by_type,"
        " coalesce('Номер ' || r.name, 'Категория ' || rt.name) AS target_name,"
        " e.last_fetched_at AS exported_at, e.fetch_count AS export_count, e.last_user_agent,"
        " (SELECT row_to_json(l) FROM (SELECT started_at, status, events, added, updated, removed, conflicts, echoes, skipped, message"
        "   FROM sync_log WHERE feed_id = f.id ORDER BY started_at DESC, id DESC LIMIT 1) l) AS last_run,"
        " (SELECT count(*) FROM sync_log WHERE feed_id = f.id AND status = 'error' AND started_at > now() - interval '24 hours') AS errors_24h,"
        " (SELECT coalesce(sum(echoes), 0) FROM sync_log WHERE feed_id = f.id AND started_at > now() - interval '7 days') AS echoes_7d,"
        " (SELECT count(*) FROM ical_snapshots s WHERE s.feed_id = f.id) AS received_snapshots,"
        " (SELECT count(*) FROM ical_snapshots s WHERE s.target_id = coalesce(f.room_id, f.room_type_id) AND s.channel = f.channel AND s.kind = 'served') AS served_snapshots,"
        " EXISTS (SELECT 1 FROM sync_alerts a WHERE a.target_id = coalesce(f.room_id, f.room_type_id) AND a.channel = f.channel) AS export_stale"
        " FROM ical_feeds f LEFT JOIN rooms r ON r.id = f.room_id LEFT JOIN room_types rt ON rt.id = f.room_type_id"
        " LEFT JOIN ical_exports e ON e.target_id = coalesce(f.room_id, f.room_type_id) AND e.channel = f.channel"
        " WHERE f.account_id = %s ORDER BY f.channel, coalesce(r.sort_order, 0), coalesce(r.name, rt.name)", (account_id,))
    return rows


def check_stale() -> int:
    """Раз в проход планировщика: открывает/закрывает предупреждения «площадка не забирала наш календарь > N часов»
    и один раз на аккаунт и площадку шлёт уведомление о новых."""
    opened = 0
    with tx() as conn:
        stale = all_(conn,
            "SELECT f.account_id, f.channel, coalesce(f.room_id, f.room_type_id) AS target_id,"
            " coalesce(r.name, rt.name) AS target_name FROM ical_feeds f JOIN accounts a ON a.id = f.account_id"
            " LEFT JOIN rooms r ON r.id = f.room_id LEFT JOIN room_types rt ON rt.id = f.room_type_id"
            " LEFT JOIN ical_exports e ON e.target_id = coalesce(f.room_id, f.room_type_id) AND e.channel = f.channel"
            " WHERE f.enabled AND a.status = 'active' AND NOT a.is_demo"
            " AND coalesce(e.last_fetched_at, f.created_at) < now() - make_interval(hours => %s)", (STALE_EXPORT_HOURS,))
        keep = [(str(x["target_id"]), x["channel"]) for x in stale]
        current = all_(conn, "SELECT target_id, channel FROM sync_alerts WHERE kind = 'export_stale'")
        for c in current:
            if (str(c["target_id"]), c["channel"]) not in keep:
                run(conn, "DELETE FROM sync_alerts WHERE target_id = %s AND channel = %s AND kind = 'export_stale'", (c["target_id"], c["channel"]))
        fresh: dict[tuple, list[str]] = {}
        for x in stale:
            added = one(conn, "INSERT INTO sync_alerts (account_id, target_id, channel) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING 1 AS ok",
                        (x["account_id"], x["target_id"], x["channel"]))
            if added:
                fresh.setdefault((x["account_id"], x["channel"]), []).append(x["target_name"])
        from .sync import CHANNEL_LABELS
        for (account_id, channel), names in fresh.items():
            opened += 1
            notify.send(conn, account_id, "sync_error",
                        f"Площадка {CHANNEL_LABELS.get(channel, channel)} не забирала наш календарь больше {STALE_EXPORT_HOURS} ч ({', '.join(names[:5])}"
                        f"{'…' if len(names) > 5 else ''}). Проверьте, что ссылка нашего календаря вставлена на площадке.", link="#/channels", bell=True)
    return opened


def stale_count(conn, account_id) -> int:
    return one(conn, "SELECT count(*) AS n FROM sync_alerts WHERE account_id = %s", (account_id,))["n"]
