"""Форматы iCal, которые встречаются у площадок.

ВАЖНО: открытых образцов календарей Авито, Яндекс Путешествий, Суточно.ру и Островка в документации найти не удалось (проверено
поиском 12.10.2026), поэтому образцы ниже собраны по стандарту RFC 5545 с вариациями, типичными для таких выгрузок: даты без времени
(VALUE=DATE), время в UTC (…Z), локальное время с TZID и блоком VTIMEZONE, длительность вместо DTEND, свёрнутые строки,
перевод строки LF/CRLF, BOM, имена свойств в разном регистре, «кривое» событие среди нормальных. Когда придут реальные календари
(раздел «Площадки → Отладка» сохраняет сырые .ics), их нужно добавить сюда как образцы."""
import unittest
from datetime import date

from test_app import Base, d  # noqa: F401

from app import db, ical, sync

MSK = "Europe/Moscow"


def cal(*events: str, head: str = "", crlf: bool = True) -> str:
    text = "\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Test//Platform//RU", head, *events, "END:VCALENDAR", ""]).replace("\n\n", "\n")
    return text.replace("\n", "\r\n") if crlf else text


def ev(*lines: str) -> str:
    return "\n".join(["BEGIN:VEVENT", *lines, "END:VEVENT"])


class IcalFormatTests(unittest.TestCase):
    def one(self, text, tz=MSK):
        events = ical.parse(text, tz)
        self.assertEqual(len(events), 1, events)
        return events[0]

    def test_avito_style_all_day_dates(self):
        e = self.one(cal(ev("UID:avito-20350710-1", "DTSTAMP:20350601T100000Z", "DTSTART;VALUE=DATE:20350710", "DTEND;VALUE=DATE:20350715", "SUMMARY:Занято"),
                         head="X-WR-CALNAME:Квартира у парка"))
        self.assertEqual((e.start, e.end, e.summary, e.cancelled), (date(2035, 7, 10), date(2035, 7, 15), "Занято", False))

    def test_yandex_style_utc_datetimes_converted_to_property_timezone(self):
        # заезд 14:00 и выезд 12:00 по Москве, переданные в UTC
        e = self.one(cal(ev("UID:7f1c2b3a-1111-4a5b-8c9d-0e1f2a3b4c5d@travel.yandex.ru", "DTSTAMP:20350601T100000Z",
                            "DTSTART:20350710T110000Z", "DTEND:20350712T090000Z", "SUMMARY:Бронь 12345", "STATUS:CONFIRMED")))
        self.assertEqual((e.start, e.end), (date(2035, 7, 10), date(2035, 7, 12)))
        # полночь по Москве, переданная как 21:00Z предыдущего дня, — это уже следующая календарная дата
        e = self.one(cal(ev("UID:y2", "DTSTART:20350709T210000Z", "DTEND:20350711T210000Z")))
        self.assertEqual((e.start, e.end), (date(2035, 7, 10), date(2035, 7, 12)))

    def test_sutochno_style_local_time_with_tzid_and_vtimezone(self):
        vtz = "\n".join(["BEGIN:VTIMEZONE", "TZID:Europe/Moscow", "BEGIN:STANDARD", "DTSTART:19700101T000000", "TZOFFSETFROM:+0300",
                         "TZOFFSETTO:+0300", "TZNAME:MSK", "END:STANDARD", "END:VTIMEZONE"])
        e = self.one(cal(ev("UID:st-77@sutochno.ru", "DTSTART;TZID=Europe/Moscow:20350710T140000", "DTEND;TZID=Europe/Moscow:20350713T120000",
                            "SUMMARY:Бронирование №77\\, Иван"), head=vtz))
        self.assertEqual((e.start, e.end, e.summary), (date(2035, 7, 10), date(2035, 7, 13), "Бронирование №77, Иван"))

    def test_ostrovok_style_folded_description_and_extra_properties(self):
        long_desc = "DESCRIPTION:" + "Гость и подробности брони, " * 8
        folded = "\r\n ".join([long_desc[i:i + 60] for i in range(0, len(long_desc), 60)])
        text = cal(ev("UID:ostrovok-998877", "DTSTART;VALUE=DATE:20350710", "DTEND;VALUE=DATE:20350712", "SUMMARY:Reserved", folded,
                      "CATEGORIES:BOOKING", "TRANSP:OPAQUE", "X-OSTROVOK-ID:998877", "SEQUENCE:2"))
        e = self.one(text)
        self.assertEqual((e.uid, e.start, e.end, e.summary), ("ostrovok-998877", date(2035, 7, 10), date(2035, 7, 12), "Reserved"))

    def test_duration_instead_of_dtend(self):
        for dur, nights in (("P2D", 2), ("P1W", 7), ("PT48H", 2), ("PT24H", 1), ("P1DT12H", 2)):
            e = self.one(cal(ev(f"UID:dur-{dur}", "DTSTART;VALUE=DATE:20350710", f"DURATION:{dur}")))
            self.assertEqual((e.end - e.start).days, nights, dur)

    def test_missing_dtend_means_one_night_and_end_before_start_is_fixed(self):
        e = self.one(cal(ev("UID:a", "DTSTART;VALUE=DATE:20350710")))
        self.assertEqual(e.end, date(2035, 7, 11))
        e = self.one(cal(ev("UID:b", "DTSTART;VALUE=DATE:20350710", "DTEND;VALUE=DATE:20350710")))
        self.assertEqual(e.end, date(2035, 7, 11))

    def test_line_endings_bom_and_lowercase_names(self):
        base = cal(ev("UID:lf", "DTSTART;VALUE=DATE:20350710", "DTEND;VALUE=DATE:20350712"), crlf=False)
        self.assertEqual(self.one(base).start, date(2035, 7, 10))                      # LF
        self.assertEqual(self.one(base.replace("\n", "\r")).start, date(2035, 7, 10))  # старый Mac: CR
        self.assertEqual(self.one("﻿" + base).start, date(2035, 7, 10))           # BOM
        low = base.replace("DTSTART", "dtstart").replace("DTEND", "dtend").replace("UID", "uid").replace("SUMMARY", "summary")
        self.assertEqual(self.one(low).end, date(2035, 7, 12))

    def test_cancelled_and_unknown_tzid(self):
        e = self.one(cal(ev("UID:c", "DTSTART;VALUE=DATE:20350710", "DTEND;VALUE=DATE:20350712", "STATUS:CANCELLED")))
        self.assertTrue(e.cancelled)
        # Windows-имя пояса (Outlook-стиль): неизвестный TZID не должен ронять разбор — берём пояс объекта
        e = self.one(cal(ev("UID:w", "DTSTART;TZID=Russian Standard Time:20350710T140000", "DTEND;TZID=Russian Standard Time:20350712T120000")))
        self.assertEqual((e.start, e.end), (date(2035, 7, 10), date(2035, 7, 12)))

    def test_broken_event_is_skipped_not_fatal(self):
        text = cal(ev("UID:good1", "DTSTART;VALUE=DATE:20350710", "DTEND;VALUE=DATE:20350712"),
                   ev("UID:bad1", "DTSTART;VALUE=DATE:не-дата", "DTEND;VALUE=DATE:20350712"),
                   ev("UID:bad2", "SUMMARY:Нет даты вообще"),
                   ev("UID:bad3", "DTSTART;VALUE=DATE:20350710", "DURATION:ерунда"),
                   ev("UID:good2", "DTSTART;VALUE=DATE:20350720", "DTEND;VALUE=DATE:20350722"))
        events, skipped = ical.parse_report(text, MSK)
        self.assertEqual([e.uid for e in events], ["good1", "good2"])
        self.assertEqual(skipped, 3)

    def test_not_a_calendar_and_empty_calendar(self):
        with self.assertRaises(ValueError):
            ical.parse("<html>Вход в личный кабинет</html>")
        self.assertEqual(ical.parse(cal()), [])

    def test_our_own_export_round_trips(self):
        events = [ical.Event("x1@fligel", date(2035, 7, 10), date(2035, 7, 12), "Занято")]
        back = ical.parse(ical.generate("Тест — 101", events))
        self.assertEqual([(e.uid, e.start, e.end) for e in back], [("x1@fligel", date(2035, 7, 10), date(2035, 7, 12))])


class FormatsThroughSyncTests(Base):
    """Те же форматы — через весь путь: ссылка → разбор → брони в нужных датах и журнал синхронизации."""

    def setUp(self):
        self.ctx = self.register(f"fmt{id(self)}@example.ru")
        self.room = self.ctx["rooms"][0]
        self._orig = sync.fetch
        self.body = ""
        sync.fetch = lambda url: self.body

    def tearDown(self):
        sync.fetch = self._orig

    def feed(self, channel):
        r = self.client.post("/api/feeds", headers=self.ctx["h"], json={"room_id": self.room["id"], "channel": channel, "url": "https://example.com/c.ics"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def nights(self):
        bs = self.client.get("/api/board", headers=self.ctx["h"], params={"from": d(-2), "days": 60}).json()["bookings"]
        return sorted((b["check_in"], b["check_out"], b["source"]) for b in bs)

    def test_each_platform_style_creates_the_right_booking(self):
        a, b = date.fromisoformat(d(5)), date.fromisoformat(d(8))
        fmt = lambda x: x.strftime("%Y%m%d")  # noqa: E731
        samples = {
            "avito": cal(ev("UID:av1", f"DTSTART;VALUE=DATE:{fmt(a)}", f"DTEND;VALUE=DATE:{fmt(b)}", "SUMMARY:Занято")),
            "yandex": cal(ev("UID:ya1@yandex", f"DTSTART:{fmt(a)}T110000Z", f"DTEND:{fmt(b)}T090000Z", "STATUS:CONFIRMED")),
            "sutochno": cal(ev("UID:su1", f"DTSTART;TZID=Europe/Moscow:{fmt(a)}T140000", f"DTEND;TZID=Europe/Moscow:{fmt(b)}T120000")),
            "ostrovok": cal(ev("UID:os1", f"DTSTART;VALUE=DATE:{fmt(a)}", "DURATION:P3D", "SUMMARY:Reserved")),
        }
        for channel, text in samples.items():
            with self.subTest(channel=channel):
                with db.tx() as conn:   # чистое состояние для каждой площадки
                    db.run(conn, "DELETE FROM ical_feeds WHERE account_id = (SELECT account_id FROM rooms WHERE id = %s)", (self.room["id"],))
                    db.run(conn, "DELETE FROM bookings WHERE room_id = %s", (self.room["id"],))
                self.body = text
                res = self.feed(channel)
                self.assertEqual((res["status"], res["added"]), ("ok", 1), res)
                self.assertEqual(self.nights(), [(a.isoformat(), b.isoformat(), channel)])

    def test_one_broken_event_does_not_block_the_rest(self):
        a, b = date.fromisoformat(d(5)), date.fromisoformat(d(7))
        self.body = cal(ev("UID:ok1", f"DTSTART;VALUE=DATE:{a:%Y%m%d}", f"DTEND;VALUE=DATE:{b:%Y%m%d}"), ev("UID:bad", "DTSTART;VALUE=DATE:мусор"))
        res = self.feed("avito")
        self.assertEqual((res["status"], res["added"]), ("ok", 1))
        log = self.client.get("/api/sync-log", headers=self.ctx["h"]).json()
        self.assertIn("Не удалось разобрать событий: 1", log[0]["message"])


if __name__ == "__main__":
    unittest.main()
