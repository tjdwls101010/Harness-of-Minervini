from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")
REGULAR_OPEN = dt.time(9, 30)
REGULAR_CLOSE = dt.time(16, 0)
EARLY_CLOSE = dt.time(13, 0)


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    last = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: dt.date) -> dt.date:
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def _new_year_holiday(year: int) -> dt.date:
    day = dt.date(year, 1, 1)
    return day + dt.timedelta(days=1) if day.weekday() == 6 else day


def _easter_sunday(year: int) -> dt.date:
    a, b, c = year % 19, year // 100, year % 100
    d, e, f = b // 4, b % 4, (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    leap = (32 + 2 * e + 2 * i - h - k) % 7
    correction = (a + 11 * h + 22 * leap) // 451
    month = (h + leap - 7 * correction + 114) // 31
    day = (h + leap - 7 * correction + 114) % 31 + 1
    return dt.date(year, month, day)


@lru_cache(maxsize=None)
def _nyse_holidays_for_year(year: int) -> frozenset[dt.date]:
    holidays = {
        _new_year_holiday(year),
        _nth_weekday(year, 2, 0, 3),
        _easter_sunday(year) - dt.timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed(dt.date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(dt.date(year, 12, 25)),
    }
    if year >= 1998:
        holidays.add(_nth_weekday(year, 1, 0, 3))
    if year >= 2022:
        holidays.add(_observed(dt.date(year, 6, 19)))
    return frozenset(holidays)


_SPECIAL_CLOSURES = frozenset(
    {
        dt.date(2001, 9, 11),
        dt.date(2001, 9, 12),
        dt.date(2001, 9, 13),
        dt.date(2001, 9, 14),
        dt.date(2004, 6, 11),
        dt.date(2007, 1, 2),
        dt.date(2012, 10, 29),
        dt.date(2012, 10, 30),
        dt.date(2018, 12, 5),
        dt.date(2025, 1, 9),
    }
)


def is_trading_day(day: dt.date) -> bool:
    if day.weekday() >= 5 or day in _SPECIAL_CLOSURES:
        return False
    return all(day not in _nyse_holidays_for_year(year) for year in (day.year - 1, day.year, day.year + 1))


def is_early_close(day: dt.date) -> bool:
    if not is_trading_day(day):
        return False
    thanksgiving = _nth_weekday(day.year, 11, 3, 4)
    return day == thanksgiving + dt.timedelta(days=1) or (day.month, day.day) in {(7, 3), (12, 24)}


def is_regular_session_open(now: dt.datetime | None = None) -> bool:
    """Report whether a US regular session is trading right now.

    Live provider snapshots describe the session in progress, so they may only
    stand in for a completed session while no session is open.
    """

    now_et = _as_et(now)
    day = now_et.date()
    if not is_trading_day(day):
        return False
    close = EARLY_CLOSE if is_early_close(day) else REGULAR_CLOSE
    return dt.datetime.combine(day, REGULAR_OPEN, tzinfo=ET) <= now_et < dt.datetime.combine(day, close, tzinfo=ET)


def _as_et(now: dt.datetime | None) -> dt.datetime:
    observed = now or dt.datetime.now(tz=ET)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return observed.astimezone(ET)


def last_completed_session(now: dt.datetime | None = None) -> dt.date:
    now_et = _as_et(now)
    day = now_et.date()
    if is_trading_day(day):
        close = dt.datetime.combine(day, EARLY_CLOSE if is_early_close(day) else REGULAR_CLOSE, tzinfo=ET)
        if now_et >= close:
            return day
    candidate = day - dt.timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= dt.timedelta(days=1)
    return candidate


@dataclass(frozen=True)
class AnalysisClock:
    """The completed-session boundary that every point-in-time provider receives."""

    date: dt.date
    mode: str
    timezone: str = "America/New_York"
    completed_session: bool = True


def _parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("as_of must use YYYY-MM-DD") from error


def resolve_as_of(value: str | dt.date | None = None, *, now: dt.datetime | None = None) -> AnalysisClock:
    """Resolve an explicit completed-session boundary or the latest completed session."""

    latest_completed = last_completed_session(now)
    if value is None:
        return AnalysisClock(date=latest_completed, mode="last_completed_session")

    explicit = _parse_date(value)
    if explicit > latest_completed:
        raise ValueError("as_of cannot be after the last completed US regular session")
    if not is_trading_day(explicit):
        raise ValueError("as_of must name a completed US trading session")
    return AnalysisClock(date=explicit, mode="explicit")
