from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    TASI_TZ = ZoneInfo("Asia/Riyadh")
except Exception:  # pragma: no cover - Windows without tzdata
    TASI_TZ = timezone(timedelta(hours=3), name="AST")

PREOPEN = time(9, 30)
SESSION_OPEN = time(10, 0)
SESSION_CLOSE = time(15, 0)
POST_CLOSE = time(15, 30)
FRIDAY = 4
SATURDAY = 5


def now_riyadh(moment: datetime | None = None) -> datetime:
    if moment is None:
        return datetime.now(TASI_TZ)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=TASI_TZ)
    return moment.astimezone(TASI_TZ)


def is_tasi_weekday(moment: datetime | None = None) -> bool:
    return now_riyadh(moment).weekday() not in {FRIDAY, SATURDAY}


def is_tasi_session_date(day: date) -> bool:
    return day.weekday() not in {FRIDAY, SATURDAY}


def next_tasi_session_date(day: date | None = None) -> date:
    """Snap a calendar date onto the next Sunday–Thursday TASI session."""

    current = day or now_riyadh().date()
    while current.weekday() in {FRIDAY, SATURDAY}:
        current += timedelta(days=1)
    return current


def add_tasi_calendar_days(start: date, days: int) -> date:
    """Shift by calendar days, then land on a TASI weekday (Sun–Thu)."""

    target = start + timedelta(days=days)
    if days < 0:
        while target.weekday() in {FRIDAY, SATURDAY}:
            target -= timedelta(days=1)
        return target
    return next_tasi_session_date(target)


def session_phase(moment: datetime | None = None) -> str:
    """weekend | closed | preopen | open | auction"""

    current = now_riyadh(moment)
    if not is_tasi_weekday(current):
        return "weekend"
    clock = current.time().replace(microsecond=0)
    if clock < PREOPEN:
        return "closed"
    if clock < SESSION_OPEN:
        return "preopen"
    if clock <= SESSION_CLOSE:
        return "open"
    if clock < POST_CLOSE:
        return "auction"
    return "closed"


def is_intraday_window(moment: datetime | None = None) -> bool:
    return session_phase(moment) == "open"


def phase_label(phase: str) -> str:
    return {
        "weekend": "عطلة تاسي",
        "closed": "السوق مغلق",
        "preopen": "تجهيز الافتتاح",
        "open": "جلسة تداول",
        "auction": "مزاد الإغلاق",
    }.get(phase, phase)
