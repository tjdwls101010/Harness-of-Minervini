#!/usr/bin/env python3
"""Ticker information retrieval.

Retrieve comprehensive company metadata, fast quotes, ISIN codes, shares outstanding,
history metadata, and SEC filings for stocks and ETFs via Yahoo Finance API.

Commands:
	get-info: Full company information (industry, sector, employees, description, etc.)
	get-fast-info: Quick quote with essential metrics (price, volume, market cap)
	get-info-fields: Specific fields from company info
	get-isin: International Securities Identification Number
	get-shares: Current shares outstanding
	get-shares-full: Historical shares outstanding with date range
	get-history-metadata: Trading metadata (currency, exchange, timezone)
	get-history: Raw unadjusted daily or weekly OHLCV for an explicit date range
	get-sec-filings: SEC filing documents and links

Args:
	symbol (str): Ticker symbol (e.g., "AAPL", "MSFT", "SPY")
	fields (list): Specific fields to retrieve (for get-info-fields)
	--start (str): Start date for shares history (YYYY-MM-DD)
	--end (str): End date for shares history (YYYY-MM-DD)
	--since (str): Filter SEC filings on or after this date (YYYY-MM-DD)
	--form (str): Filter SEC filings by form type (e.g., "10-K", "10-Q", "8-K")

Returns:
	dict: {
		"symbol": str,                    # Ticker symbol
		"shortName": str,                 # Company short name
		"longName": str,                  # Full company name
		"sector": str,                    # Business sector
		"industry": str,                  # Industry classification
		"marketCap": int,                 # Market capitalization
		"enterpriseValue": int,           # Enterprise value
		"fullTimeEmployees": int,         # Number of employees
		"website": str,                   # Company website
		"businessSummary": str,           # Business description
		"financialCurrency": str,         # Reporting currency
		"exchange": str,                  # Listing exchange
		"quoteType": str                  # Security type (EQUITY, ETF, etc.)
	}

Example:
	>>> python info.py get-info AAPL
	{
		"symbol": "AAPL",
		"shortName": "Apple Inc.",
		"sector": "Technology",
		"industry": "Consumer Electronics",
		"marketCap": 2800000000000,
		"fullTimeEmployees": 164000,
		"website": "https://www.apple.com",
		"businessSummary": "Apple Inc. designs, manufactures..."
	}

	>>> python info.py get-fast-info SPY
	{
		"last_price": 475.50,
		"last_volume": 78234000,
		"market_cap": 445000000000,
		"shares": 935000000,
		"year_high": 480.50,
		"year_low": 410.30
	}

	>>> python info.py get-info-fields MSFT sector industry marketCap
	{
		"sector": "Technology",
		"industry": "Software—Infrastructure",
		"marketCap": 2950000000000
	}

	>>> python info.py get-isin AAPL
	{
		"isin": "US0378331005"
	}

	>>> python info.py get-shares-full AAPL --start 2023-01-01 --end 2024-01-01
	{
		"2023-01-31": 15634232000,
		"2023-04-30": 15647304000,
		"2023-07-31": 15550061000
	}

	>>> python info.py get-sec-filings AAPL --form 10-K --since 2024-01-01
	[
		{
			"type": "10-K",
			"date": "2024-11-01",
			"title": "Annual Report",
			"edgarUrl": "https://www.sec.gov/..."
		}
	]

Use Cases:
	- Company research and fundamental analysis screening
	- Ticker metadata enrichment and category classification
	- Sector and industry context for leadership analysis
	- ISIN lookup for international trading systems
	- Shares outstanding tracking for dilution analysis
	- SEC filing retrieval for compliance and research

Notes:
	- Yahoo Finance API rate limits: ~2000 requests/hour
	- get-info returns 100+ fields (extensive company data)
	- get-fast-info is faster but returns fewer fields
	- get-info-fields uses 3-tier fallback for key fields:
	  1. ticker.get_info() (primary)
	  2. ticker.fast_info (marketCap, currentPrice, 52w range)
	  3. ticker.history(period="5d") last Close (currentPrice only)
	  This eliminates null values for ADRs and some large-caps (e.g., AVGO, TSM)
	- ISIN codes may not be available for all securities
	- Shares outstanding data updated quarterly
	- SEC filings only available for US-listed companies
	- Some fields may be null for non-US securities

See Also:
	- info.py get-history: Historical unadjusted OHLCV windows
	- earnings_acceleration.py: Earnings and estimate diagnostics
	- actions.py: Earnings calendar and corporate events
	- pipeline qualify: Stage-2 and Trend-Template eligibility gate
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pandas as pd
import yfinance as yf
from utils import JsonArgumentParser, error_json, output_json, safe_run


_DATA_DOCTRINE = (
	"[DATA] Module-sourced values are evidence only. This retrieval command does not "
	"infer missing market or company facts and does not issue a trading verdict."
)
_HISTORY_DOCTRINE = (
	"[DATA] Historical OHLCV is the doctrine-compliant source for as-of and post-exit "
	"review; no missing bar is filled from memory or narrative sources."
)
_DATA_PROVENANCE = {
	"data_source": "Yahoo Finance via yfinance",
	"methodology": "[DATA] Retrieval only; methodology thresholds are not applied here.",
}


def _emit(command, data, doctrine=_DATA_DOCTRINE, **extra):
	"""Emit metadata while preserving dictionary root fields for existing consumers."""
	if isinstance(data, dict):
		result = dict(data)
	else:
		result = {"data": data}
	result.update(extra)
	result["doctrine"] = doctrine
	result["provenance"] = {**_DATA_PROVENANCE, "command": command}
	output_json(result)


def _history_records(data):
	"""Convert OHLCV rows to date-keyed records without changing source values."""
	records = []
	for index, row in data.iterrows():
		record = {"date": index.isoformat() if hasattr(index, "isoformat") else str(index)}
		for column, value in row.items():
			record[str(column)] = value
		records.append(record)
	return records


@safe_run
def cmd_get_info(args):
	ticker = yf.Ticker(args.symbol)
	_emit("get-info", ticker.get_info())


@safe_run
def cmd_get_fast_info(args):
	ticker = yf.Ticker(args.symbol)
	fi = ticker.get_fast_info()
	result = {}
	for attr in dir(fi):
		if attr.startswith("_"):
			continue
		try:
			val = getattr(fi, attr)
			if not callable(val):
				result[attr] = val
		except Exception:
			pass
	_emit("get-fast-info", result)


@safe_run
def cmd_get_info_fields(args):
	ticker = yf.Ticker(args.symbol)
	info = ticker.get_info()
	filtered = {k: info[k] for k in args.fields if k in info}

	# Fallback: supplement null/missing key fields via fast_info
	fast_info_map = {
		"marketCap": "market_cap",
		"currentPrice": "last_price",
		"fiftyTwoWeekLow": "year_low",
		"fiftyTwoWeekHigh": "year_high",
	}
	missing = [f for f in args.fields if f in fast_info_map and (f not in filtered or filtered[f] is None)]
	if missing:
		try:
			fi = ticker.get_fast_info()
			for field in missing:
				attr = fast_info_map[field]
				val = getattr(fi, attr, None)
				if val is not None:
					filtered[field] = val
		except Exception:
			pass

	# Fallback: if currentPrice still missing, use last close from history
	if "currentPrice" in args.fields and (filtered.get("currentPrice") is None):
		try:
			hist = ticker.history(period="5d")
			# Drop the partial current-session bar yfinance appends mid-day: its
			# Close can be NaN, which would set currentPrice to NaN instead of the
			# last real close.
			hist = hist.dropna(subset=["Close"])
			if not hist.empty:
				filtered["currentPrice"] = float(hist["Close"].iloc[-1])
		except Exception:
			pass

	# Compressed view: remove MA/52w fields that duplicate trend_template data
	_remove_fields = {
		"fiftyDayAverage", "twoHundredDayAverage",
		"fiftyTwoWeekLow", "fiftyTwoWeekHigh",
	}
	filtered["compressed"] = {k: v for k, v in filtered.items() if k not in _remove_fields}

	_emit("get-info-fields", filtered)


@safe_run
def cmd_get_isin(args):
	ticker = yf.Ticker(args.symbol)
	_emit("get-isin", {"isin": ticker.get_isin()})


@safe_run
def cmd_get_shares(args):
	ticker = yf.Ticker(args.symbol)
	_emit("get-shares", ticker.get_shares())


@safe_run
def cmd_get_shares_full(args):
	ticker = yf.Ticker(args.symbol)
	kwargs = {}
	if args.start:
		kwargs["start"] = args.start
	if args.end:
		kwargs["end"] = args.end
	_emit("get-shares-full", ticker.get_shares_full(**kwargs))


@safe_run
def cmd_get_history_metadata(args):
	ticker = yf.Ticker(args.symbol)
	_emit("get-history-metadata", ticker.get_history_metadata())


@safe_run
def cmd_get_history(args):
	"""Get unadjusted source OHLCV for an explicit date range."""
	start = pd.Timestamp(args.start)
	end = pd.Timestamp(args.end)
	if end <= start:
		error_json("--end must be later than --start")

	symbol = args.symbol.upper()
	data = yf.Ticker(symbol).history(
		start=args.start,
		end=args.end,
		interval=args.interval,
		auto_adjust=False,
		actions=False,
	)
	data = data.dropna(how="all")
	if data.empty:
		error_json(f"No OHLCV history returned for {symbol} in the requested range")

	_emit(
		"get-history",
		{
			"symbol": symbol,
			"start": args.start,
			"end": args.end,
			"end_exclusive": True,
			"interval": args.interval,
			"row_count": len(data),
			"history": _history_records(data),
		},
		doctrine=_HISTORY_DOCTRINE,
	)


@safe_run
def cmd_get_sec_filings(args):
	from datetime import datetime

	ticker = yf.Ticker(args.symbol)
	data = ticker.get_sec_filings()

	since = getattr(args, "since", None)
	form_filter = getattr(args, "form", None)

	# yfinance returns list of dicts for sec_filings
	if isinstance(data, list) and data and (since or form_filter):
		filtered = data
		if since:
			since_dt = datetime.strptime(since, "%Y-%m-%d").date()

			def _parse_date(val):
				if isinstance(val, datetime):
					return val.date()
				if hasattr(val, "date") and callable(val.date):
					return val.date()
				if hasattr(val, "year"):  # datetime.date
					return val
				if isinstance(val, str):
					return datetime.strptime(val[:10], "%Y-%m-%d").date()
				return None

			filtered = [f for f in filtered if f.get("date") and (_d := _parse_date(f["date"])) and _d >= since_dt]
		if form_filter:
			filtered = [f for f in filtered if form_filter.upper() in (f.get("type", "") or "").upper()]
		data = filtered

	_emit("get-sec-filings", data)


def _add_no_cache(parser):
	parser.add_argument("--no-cache", action="store_true", help="Bypass cache reads and writes for this command")


def main():
	parser = JsonArgumentParser(description="Ticker information retrieval")
	sub = parser.add_subparsers(dest="command", required=True)

	# get-info
	sp = sub.add_parser("get-info", help="Get full ticker info")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_info)

	# get-fast-info
	sp = sub.add_parser("get-fast-info", help="Get fast ticker info")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_fast_info)

	# get-info-fields
	sp = sub.add_parser("get-info-fields", help="Get specific info fields")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	sp.add_argument("fields", nargs="+", help="One or more yfinance info-field names")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_info_fields)

	# get-isin
	sp = sub.add_parser("get-isin", help="Get ISIN")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_isin)

	# get-shares
	sp = sub.add_parser("get-shares", help="Get shares outstanding")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_shares)

	# get-shares-full
	sp = sub.add_parser("get-shares-full", help="Get full shares history")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	sp.add_argument("--start", default=None, help="Optional inclusive start date (YYYY-MM-DD; default: provider range)")
	sp.add_argument("--end", default=None, help="Optional exclusive end date (YYYY-MM-DD; default: provider range)")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_shares_full)

	# get-history-metadata
	sp = sub.add_parser("get-history-metadata", help="Get history metadata")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_history_metadata)

	# get-history
	sp = sub.add_parser("get-history", help="Get raw OHLCV for an explicit date range")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	sp.add_argument("--start", required=True, help="Inclusive start date (YYYY-MM-DD)")
	sp.add_argument("--end", required=True, help="Exclusive end date (YYYY-MM-DD)")
	sp.add_argument("--interval", choices=["1d", "1wk"], default="1d", help="OHLCV interval (default: 1d)")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_history)

	# get-sec-filings
	sp = sub.add_parser("get-sec-filings", help="Get SEC filings")
	sp.add_argument("symbol", help="US-listed ticker symbol")
	sp.add_argument("--since", type=str, default=None, help="Filter filings on or after date (YYYY-MM-DD)")
	sp.add_argument("--form", type=str, default=None, help="Filter by form type (e.g., 10-K, 10-Q, 8-K)")
	_add_no_cache(sp)
	sp.set_defaults(func=cmd_get_sec_filings)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
