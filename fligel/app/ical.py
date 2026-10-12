"""Разбор и генерация календарей iCalendar (RFC 5545) — только то, что нужно для занятости.

Площадки (Авито, Яндекс Путешествия, Суточно.ру, Островок, Booking, Airbnb) отдают
занятость как набор VEVENT с датами начала/окончания. Мы читаем UID, DTSTART, DTEND,
SUMMARY и STATUS; всё остальное игнорируем.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass
class Event:
    uid: str
    start: date          # дата заезда
    end: date            # дата выезда (не включительно)
    summary: str = ""
    cancelled: bool = False


def _unfold(text: str) -> list[str]:
    """Склеивает перенесённые строки: строка, начинающаяся с пробела/таба — продолжение предыдущей."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n").replace("\\N", "\n")
        .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    )


def _parse_date(value: str, params: dict[str, str], default_tz: str) -> date:
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return datetime.strptime(value[:8], "%Y%m%d").date()
    # DATE-TIME: 20261001T140000Z или 20261001T140000 (+ TZID)
    utc = value.endswith("Z")
    dt = datetime.strptime(value.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    tz_name = params.get("TZID") or default_tz
    if utc:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        except Exception:
            dt = dt.replace(tzinfo=ZoneInfo(default_tz))
    # Переводим в часовой пояс объекта и берём календарную дату
    return dt.astimezone(ZoneInfo(default_tz)).date()


_DURATION = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$", re.I)


def _duration_days(value: str) -> int:
    """DURATION по RFC 5545 (P2D, P1W, PT24H…) → число суток, не меньше одних."""
    m = _DURATION.match(value.strip())
    if not m:
        raise ValueError(f"Непонятная длительность {value!r}")
    _, w, d, h, mi, sec = m.groups()
    total = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=int(sec or 0))
    return max(1, round(total / timedelta(days=1)))


def parse_report(text: str, default_tz: str = "Europe/Moscow") -> tuple[list[Event], int]:
    """Разбирает календарь; возвращает (события, сколько событий пропущено как неразбираемые).
    Одно «кривое» событие не должно ломать весь календарь площадки — оно пропускается и считается."""
    text = text.lstrip("\ufeff")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ValueError("По ссылке не календарь iCal (нет BEGIN:VCALENDAR)")
    events: list[Event] = []
    skipped = 0
    current: dict | None = None
    for line in _unfold(text):
        if ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *param_parts = head.split(";")
        name = name.strip().upper()
        params = {}
        for part in param_parts:
            if "=" in part:
                k, v = part.split("=", 1)
                params[k.strip().upper()] = v.strip('"')
        if name == "BEGIN" and value.strip().upper() == "VEVENT":
            current = {}
        elif name == "END" and value.strip().upper() == "VEVENT":
            if current is not None:
                try:
                    events.append(_build(current))
                except Exception:  # noqa: BLE001 — кривая дата/длительность в одном событии
                    skipped += 1
            current = None
        elif current is not None:
            try:
                if name == "UID":
                    current["uid"] = value.strip()
                elif name == "DTSTART":
                    current["start"] = _parse_date(value, params, default_tz)
                elif name == "DTEND":
                    current["end"] = _parse_date(value, params, default_tz)
                elif name == "DURATION":
                    current["duration"] = value
                elif name == "SUMMARY":
                    current["summary"] = _unescape(value.strip())
                elif name == "STATUS":
                    current["status"] = value.strip()
            except Exception:  # noqa: BLE001
                current["broken"] = True
    return events, skipped


def _build(cur: dict) -> Event:
    if cur.get("broken") or "start" not in cur:
        raise ValueError("нет даты начала")
    start = cur["start"]
    end = cur.get("end")
    if end is None and cur.get("duration"):
        end = start + timedelta(days=_duration_days(cur["duration"]))
    end = end or start + timedelta(days=1)
    if end <= start:
        end = start + timedelta(days=1)
    uid = cur.get("uid") or f"nouid-{start.isoformat()}-{end.isoformat()}"
    return Event(uid=uid, start=start, end=end, summary=cur.get("summary", ""), cancelled=cur.get("status", "").upper() == "CANCELLED")


def parse(text: str, default_tz: str = "Europe/Moscow") -> list[Event]:
    return parse_report(text, default_tz)[0]


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Строки длиннее 75 октетов переносятся по RFC 5545."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, current = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def generate(cal_name: str, events: list[Event], prodid: str = "-//Fligel//Booking//RU") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{prodid}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(cal_name)}",
    ]
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{ev.start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{ev.end.strftime('%Y%m%d')}",
            f"SUMMARY:{_escape(ev.summary or 'Занято')}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
