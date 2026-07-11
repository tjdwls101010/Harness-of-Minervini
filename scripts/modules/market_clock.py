"""NYSE-aware market clock shared by cache policy and skill preprocessing."""

import argparse
import datetime as dt
import os
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")
REGULAR_OPEN = dt.time(9, 30)
REGULAR_CLOSE = dt.time(16, 0)
EARLY_CLOSE = dt.time(13, 0)
PREMARKET_START = dt.time(4, 0)
AFTER_HOURS_END = dt.time(20, 0)


def _nth_weekday(year, month, weekday, occurrence):
	first = dt.date(year, month, 1)
	delta = (weekday - first.weekday()) % 7
	return first + dt.timedelta(days=delta + 7 * (occurrence - 1))


def _last_weekday(year, month, weekday):
	if month == 12:
		last = dt.date(year, 12, 31)
	else:
		last = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
	return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day):
	if day.weekday() == 5:
		return day - dt.timedelta(days=1)
	if day.weekday() == 6:
		return day + dt.timedelta(days=1)
	return day


def _new_year_holiday(year):
	"""Return the NYSE New Year's closure for ``year``.

	Unlike the other fixed-date exchange holidays, a New Year's Day that falls
	on Saturday is not observed on the preceding Friday.  Treating it like the
	federal-holiday rule incorrectly marks 2021-12-31 (and analogous dates) as a
	market closure.
	"""
	day = dt.date(year, 1, 1)
	return day + dt.timedelta(days=1) if day.weekday() == 6 else day


def _easter_sunday(year):
	"""Return Gregorian Easter using the Anonymous Gregorian algorithm."""
	a = year % 19
	b = year // 100
	c = year % 100
	d = b // 4
	e = b % 4
	f = (b + 8) // 25
	g = (b - f + 1) // 3
	h = (19 * a + b - d - g + 15) % 30
	i = c // 4
	k = c % 4
	l = (32 + 2 * e + 2 * i - h - k) % 7
	m = (a + 11 * h + 22 * l) // 451
	month = (h + l - 7 * m + 114) // 31
	day = ((h + l - 7 * m + 114) % 31) + 1
	return dt.date(year, month, day)


@lru_cache(maxsize=None)
def _nyse_holidays_for_year(year):
	"""Return regular NYSE full-day closures whose observed date touches ``year``."""
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
	return frozenset(day for day in holidays if day.year in {year - 1, year, year + 1})


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


def is_trading_day(day):
	"""Return whether ``day`` has an NYSE regular session."""
	if isinstance(day, dt.datetime):
		day = day.date()
	if day.weekday() >= 5 or day in _SPECIAL_CLOSURES:
		return False
	holidays = set()
	for year in (day.year - 1, day.year, day.year + 1):
		holidays.update(_nyse_holidays_for_year(year))
	return day not in holidays


def is_early_close(day):
	"""Return whether ``day`` uses the NYSE's 13:00 ET close."""
	if isinstance(day, dt.datetime):
		day = day.date()
	if not is_trading_day(day):
		return False
	thanksgiving = _nth_weekday(day.year, 11, 3, 4)
	return day == thanksgiving + dt.timedelta(days=1) or (day.month, day.day) in {(7, 3), (12, 24)}


def _coerce_now(now=None):
	if now is None:
		local_now = dt.datetime.now().astimezone()
	elif now.tzinfo is None:
		local_now = now.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
	else:
		local_now = now
	return local_now, local_now.astimezone(ET)


def session_window(now=None):
	"""Return today's timezone-aware regular-session open and close, or ``(None, None)``."""
	_, now_et = _coerce_now(now)
	day = now_et.date()
	if not is_trading_day(day):
		return None, None
	open_at = dt.datetime.combine(day, REGULAR_OPEN, tzinfo=ET)
	close_at = dt.datetime.combine(day, EARLY_CLOSE if is_early_close(day) else REGULAR_CLOSE, tzinfo=ET)
	return open_at, close_at


def last_completed_session(now=None):
	"""Return the latest fully completed NYSE regular-session date in ET."""
	_, now_et = _coerce_now(now)
	day = now_et.date()
	_, close_at = session_window(now_et)
	if close_at is not None and now_et >= close_at:
		return day
	candidate = day - dt.timedelta(days=1)
	while not is_trading_day(candidate):
		candidate -= dt.timedelta(days=1)
	return candidate


def session_progress(now=None):
	"""Return today's regular-session elapsed fraction, clamped to 0..1, or None on a closure."""
	_, now_et = _coerce_now(now)
	open_at, close_at = session_window(now_et)
	if open_at is None:
		return None
	duration = (close_at - open_at).total_seconds()
	return max(0.0, min(1.0, (now_et - open_at).total_seconds() / duration))


def _session_name(now_et, open_at, close_at):
	if open_at is None:
		return "closed"
	current = now_et.timetz().replace(tzinfo=None)
	if PREMARKET_START <= current < REGULAR_OPEN:
		return "pre"
	if open_at <= now_et < close_at:
		return "regular"
	if close_at <= now_et and current < AFTER_HOURS_END:
		return "after"
	return "closed"


def cache_entry_count():
	"""Count complete JSON cache entries without creating the cache directory."""
	root = Path(os.environ.get("MINERVINI_CACHE_DIR", "~/.cache/minervini-harness")).expanduser()
	try:
		return sum(1 for path in root.iterdir() if path.is_file() and path.suffix == ".json")
	except (FileNotFoundError, NotADirectoryError, PermissionError):
		return 0


def get_market_state(now=None):
	"""Return the stable JSON contract consumed by caching and skill preprocessing."""
	local_now, now_et = _coerce_now(now)
	open_at, close_at = session_window(now_et)
	session = _session_name(now_et, open_at, close_at)
	return {
		"now_local": local_now.isoformat(timespec="seconds"),
		"now_et": now_et.isoformat(timespec="seconds"),
		"market_open": session == "regular",
		"session": session,
		"last_completed_session": last_completed_session(now_et).isoformat(),
		"cache_entries": cache_entry_count(),
	}


def main():
	from utils import JsonArgumentParser, configure_cache, output_json

	parser = JsonArgumentParser(description="NYSE session clock and Minervini cache state")
	parser.add_argument("--no-cache", action="store_true", help="Accepted for the global module contract; this command performs no cached fetches")
	args = parser.parse_args()

	configure_cache(args.no_cache)
	output_json(get_market_state())


if __name__ == "__main__":
	main()
