from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def start_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def current_week_start() -> date:
    return start_of_week(today())


def next_week_start() -> date:
    return current_week_start() + timedelta(days=7)


def fmt_day(d: date) -> str:
    """Monday 16 November"""
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def fmt_weekday(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def fmt_short(d: date) -> str:
    """16 Nov"""
    return f"{d.day} {MONTHS[d.month - 1][:3]}"


def fmt_week(start: date) -> str:
    """16 – 22 November 2026 (month and year only repeated when they change)."""
    end = start + timedelta(days=6)
    if start.year != end.year:
        return f"{start.day} {MONTHS[start.month - 1]} {start.year} – {end.day} {MONTHS[end.month - 1]} {end.year}"
    if start.month != end.month:
        return f"{start.day} {MONTHS[start.month - 1][:3]} – {end.day} {MONTHS[end.month - 1][:3]} {end.year}"
    return f"{start.day} – {end.day} {MONTHS[end.month - 1]} {end.year}"


def week_label(start: date) -> str | None:
    current = current_week_start()
    return {
        current: "This week",
        current + timedelta(days=7): "Next week",
        current - timedelta(days=7): "Last week",
    }.get(start)


def greeting() -> str:
    hour = datetime.now(ZoneInfo(settings.timezone)).hour
    if hour < 5 or hour >= 18:
        return "Good evening"
    return "Good morning" if hour < 12 else "Good afternoon"
