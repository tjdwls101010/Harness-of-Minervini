#!/usr/bin/env python3
"""Corporate actions, earnings dates, calendar, and news.

Retrieve dividend payments, stock splits, capital gains distributions, earnings data,
earnings calendar, corporate event calendar, and company news via Yahoo Finance API.

Commands:
	get-dividends: Historical dividend payments with ex-dates
	get-splits: Stock split history and ratios
	get-capital-gains: Capital gains distributions (mutual funds/ETFs)
	get-actions: Combined dividends and splits
	get-earnings: Annual or quarterly earnings summary
	get-earnings-dates: Future and past earnings announcement dates
	get-calendar: Upcoming earnings, ex-dividend, and other corporate events
	get-news: Company news and press releases

Args:
	symbol (str): Ticker symbol (e.g., "AAPL", "MSFT", "SPY")
	--start (str): Start date for dividend filter (YYYY-MM-DD)
	--end (str): End date for dividend filter (YYYY-MM-DD)
	--freq (str): Earnings frequency (yearly/quarterly, default: yearly)
	--limit (int): Number of earnings dates to retrieve (default: 12)
	--days-until: Add the number of ET calendar days to the next earnings date
	--count (int): Number of news articles (default: 10)
	--tab (str): News tab filter (news/all/press_releases, default: news)

Returns:
	dict: {
		"Date": str,              # Action date or announcement date
		"Dividends": float,       # Dividend amount per share
		"Stock Splits": str,      # Split ratio (e.g., "2:1")
		"Capital Gains": float,   # Capital gains per share
		"Revenue": float,         # Earnings revenue (for get-earnings)
		"Earnings": float,        # Earnings per share
		"title": str,             # News headline (for get-news)
		"publisher": str,         # News source
		"link": str               # News article URL
	}

Example:
	>>> python actions.py get-dividends AAPL --start 2024-01-01 --end 2024-12-31
	{
		"2024-02-09": {"Dividends": 0.24},
		"2024-05-10": {"Dividends": 0.24},
		"2024-08-12": {"Dividends": 0.25},
		"2024-11-08": {"Dividends": 0.25}
	}

	>>> python actions.py get-splits AAPL
	{
		"2014-06-09": {"Stock Splits": "7:1"},
		"2020-08-31": {"Stock Splits": "4:1"}
	}

	>>> python actions.py get-earnings MSFT --freq quarterly
	{
		"2025Q4": {"Revenue": 62026000000, "Earnings": 3.13},
		"2025Q3": {"Revenue": 65585000000, "Earnings": 3.30},
		"2025Q2": {"Revenue": 64727000000, "Earnings": 2.99}
	}

	>>> python actions.py get-earnings-dates AAPL --limit 4
	{
		"2026-01-29": {"Earnings Date": "2026-01-29", "EPS Estimate": 2.35},
		"2025-10-31": {"Earnings Date": "2025-10-31", "EPS Estimate": 1.59}
	}

	>>> python actions.py get-calendar SPY
	{
		"Earnings Date": "N/A",
		"Ex-Dividend Date": "2026-03-21",
		"Dividend Date": "2026-04-30"
	}

	>>> python actions.py get-news AAPL --count 5
	[
		{
			"title": "Apple announces new product line",
			"publisher": "Reuters",
			"link": "https://...",
			"providerPublishTime": 1704153600
		}
	]

Use Cases:
	- Corporate-action and dividend-history evidence
	- Earnings-event proximity checks for the harness's entry policy
	- Company-event and news retrieval without an inferred verdict
	- Corporate action adjustments for backtesting
	- Stock split history for price normalization

Notes:
	- Yahoo Finance API rate limits: ~2000 requests/hour
	- Dividend dates are ex-dividend dates (not payment dates)
	- Earnings dates may be estimates subject to change
	- News articles limited to recent 30-60 days
	- get-calendar returns next upcoming events only
	- Capital gains primarily applicable to mutual funds and ETFs
	- Earnings estimates may be null if not available

See Also:
	- info.py get-history: Historical unadjusted OHLCV windows
	- earnings_acceleration.py: Earnings quality and acceleration diagnostics
	- info.py: Company metadata and business information
	- pipeline qualify: Stage-2 and Trend-Template eligibility gate
"""

import argparse
from datetime import datetime
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pandas as pd
import yfinance as yf
from utils import JsonArgumentParser, output_json, safe_run


_DATA_PROVENANCE = {
	"data_source": "Yahoo Finance via yfinance",
	"methodology": "[DATA] Retrieval only; no price, date, or event is inferred by this module.",
}
_ACTIONS_DOCTRINE = (
	"[DATA] Corporate-action records are evidence, not a trading verdict. "
	"Use them only with the harness's approved setup, risk, and event policies."
)
_EARNINGS_DATES_DOCTRINE = (
	"[TL] Avoid a new breakout entry immediately before earnings. Earnings proximity "
	"is an event-risk input, not a standalone buy or sell signal."
)


def _emit(command, data, doctrine=_ACTIONS_DOCTRINE, **extra):
	"""Emit a contract envelope without discarding dictionary root fields."""
	if isinstance(data, dict):
		result = dict(data)
	else:
		result = {"data": data}
	result.update(extra)
	result["doctrine"] = doctrine
	result["provenance"] = {**_DATA_PROVENANCE, "command": command}
	output_json(result)


def _earnings_date(value):
	"""Return the calendar date represented by a yfinance earnings index value."""
	stamp = pd.Timestamp(value)
	if stamp.tzinfo is not None:
		stamp = stamp.tz_convert("America/New_York")
	return stamp.date()


def _days_until_summary(data, today=None):
	"""Find the nearest non-past earnings date using the New York calendar date."""
	today = today or datetime.now(ZoneInfo("America/New_York")).date()
	if data is None or not hasattr(data, "index"):
		return {"as_of_date_et": today.isoformat(), "next_earnings_date": None, "days_until": None}

	future = []
	for value in data.index:
		date_value = _earnings_date(value)
		days = (date_value - today).days
		if days >= 0:
			future.append((days, date_value))
	if not future:
		return {"as_of_date_et": today.isoformat(), "next_earnings_date": None, "days_until": None}
	days, date_value = min(future)
	return {
		"as_of_date_et": today.isoformat(),
		"next_earnings_date": date_value.isoformat(),
		"days_until": days,
	}


@safe_run
def cmd_dividends(args):
	data = yf.Ticker(args.symbol).get_dividends()
	if args.start:
		start = pd.Timestamp(args.start)
		if data.index.tz is not None:
			start = start.tz_localize(data.index.tz)
		data = data[data.index >= start]
	if args.end:
		end = pd.Timestamp(args.end)
		if data.index.tz is not None:
			end = end.tz_localize(data.index.tz)
		data = data[data.index <= end]
	_emit("get-dividends", data)


@safe_run
def cmd_splits(args):
	_emit("get-splits", yf.Ticker(args.symbol).get_splits())


@safe_run
def cmd_capital_gains(args):
	_emit("get-capital-gains", yf.Ticker(args.symbol).get_capital_gains())


@safe_run
def cmd_actions(args):
	_emit("get-actions", yf.Ticker(args.symbol).get_actions())


@safe_run
def cmd_earnings(args):
	_emit("get-earnings", yf.Ticker(args.symbol).get_earnings(freq=args.freq))


@safe_run
def cmd_earnings_dates(args):
	data = yf.Ticker(args.symbol).get_earnings_dates(limit=args.limit)
	extra = _days_until_summary(data) if args.days_until else {}
	_emit("get-earnings-dates", data, doctrine=_EARNINGS_DATES_DOCTRINE, **extra)


@safe_run
def cmd_calendar(args):
	_emit("get-calendar", yf.Ticker(args.symbol).get_calendar())


@safe_run
def cmd_news(args):
	_emit("get-news", yf.Ticker(args.symbol).get_news(count=args.count, tab=args.tab))


def _add_no_cache(parser):
	parser.add_argument("--no-cache", action="store_true", help="Bypass cache reads and writes for this command")


def main():
	parser = JsonArgumentParser(description="Corporate actions, earnings, and news")
	sub = parser.add_subparsers(dest="command", required=True)

	# get-dividends
	sp = sub.add_parser("get-dividends", help="Historical dividend payments")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	sp.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
	sp.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_dividends)

	# get-splits
	sp = sub.add_parser("get-splits", help="Historical stock splits")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_splits)

	# get-capital-gains
	sp = sub.add_parser("get-capital-gains", help="Historical capital-gains distributions")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_capital_gains)

	# get-actions
	sp = sub.add_parser("get-actions", help="Combined dividend and split history")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_actions)

	# get-earnings
	sp = sub.add_parser("get-earnings", help="Annual or quarterly earnings summary")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	sp.add_argument("--freq", choices=["yearly", "quarterly"], default="yearly", help="Earnings frequency (default: yearly)")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_earnings)

	# get-earnings-dates
	sp = sub.add_parser("get-earnings-dates", help="Earnings dates with optional days-to-next report")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	sp.add_argument("--limit", type=int, default=12, help="Maximum earnings-date rows (default: 12)")
	sp.add_argument(
		"--days-until",
		action="store_true",
		help="Add New-York-date days until the next non-past earnings report",
	)
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_earnings_dates)

	# get-calendar
	sp = sub.add_parser("get-calendar", help="Upcoming corporate-event calendar")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_calendar)

	# get-news
	sp = sub.add_parser("get-news", help="Recent company news and press releases")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	sp.add_argument("--count", type=int, default=10, help="Maximum news rows (default: 10)")
	sp.add_argument("--tab", choices=["news", "all", "press_releases"], default="news", help="Yahoo news category (default: news)")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_news)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
