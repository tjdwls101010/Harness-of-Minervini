#!/usr/bin/env python3
"""Relative-strength ranking with an explicit source fallback chain.

``score`` first reads the authoritative IBD-style rating published by the
project's ``ibd-rs-rating`` Supabase backend. It must not be described as a
proprietary IBD feed. If that source is unavailable, the module computes a
clearly labelled local proxy from the stock/SPY RS line.

The proxy reports RS-day share and 1M/3M/6M/12M historical percentiles. Per
the binding implementation ruling, only its 12M percentile may provisionally
stand in for the Minervini RS >= 70 eligibility gate; shorter lookbacks are
timing evidence only. If neither source can produce the eligibility score, the
result is unavailable rather than a fabricated failure.
"""

import argparse
import math
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
import utils as _utils
from utils import JsonArgumentParser, output_json, safe_run


# [M] This is criterion 8 of the original Trend Template. It is a locked floor:
# lowering it would admit a stock that has not demonstrated leader-level demand.
MIN_RS_ELIGIBILITY = 70

# [TL] These windows separate short-term timing evidence from the 12-month SEPA
# eligibility horizon. They are trading-session approximations, not calendar days.
PROXY_LOOKBACKS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
DEFAULT_PROXY_PERIOD = "5y"
DEFAULT_RS_DAYS_LOOKBACK = 63

SOURCE_BACKEND = "ibd_rs_rating_backend"
SOURCE_PROXY = "local_rs_line_proxy"

DOCTRINE = (
	"[M] Relative strength is an eligibility test for leadership, not a reason to buy by itself: the original "
	"Trend Template requires an RS rank of at least 70 and prefers the 80s-90s. [TL] The stock/SPY RS line and "
	"RS-day share reveal whether the stock resists market pressure; short 1M/3M/6M percentiles are timing aids, "
	"while the adjudicated 12M measure alone may provisionally carry the eligibility gate when the backend is "
	"unavailable."
)

PROVENANCE = {
	"eligibility_floor": "[M] Minervini knowledge map, cluster C: RS >= 70; 80-90s preferred",
	"proxy_spec": "[TL] TraderLion knowledge map, clusters B/G and conflict ruling 4.14",
	"source_order": "Harness spec Implementation rulings: backend -> labelled local proxy -> unavailable",
	"backend_notice": "Authoritative project source: IBD-style data supplied by ibd-rs-rating; not described as a proprietary IBD feed",
}


def _configure_cache(no_cache=False):
	"""Use the shared cache API when present during the phased migration."""
	configure = getattr(_utils, "configure_cache", None)
	if configure is not None:
		already_disabled = getattr(_utils, "cache_disabled", lambda: False)()
		configure(bool(no_cache) or already_disabled)


def _cached_call(source, symbol, function, params, fetcher, *, no_cache=False):
	"""Small adapter for the shared cache API landed by the cache-clock pass."""
	cache = getattr(_utils, "cached_call", None)
	if cache is None:
		return fetcher()
	return cache(
		source,
		symbol,
		function,
		params,
		fetcher,
		price_endpoint=False,
		no_cache=no_cache,
	)


def _get_rs_client():
	"""Construct the package client lazily with normal certificate verification.

	The macOS/Python runtime used by this project does not always expose a usable
	system CA bundle to :mod:`urllib`, which is what ``ibd-rs-rating`` uses. Point
	urllib at certifi's pinned Mozilla bundle when the caller has not selected a
	bundle already. This repairs trust-chain discovery; it never disables or
	weakens TLS verification.
	"""
	import certifi

	os.environ.setdefault("SSL_CERT_FILE", certifi.where())
	from rs_rating import RS

	return RS()


def call_backend(function, *, symbol="MARKET", params=None, no_cache=False, client=None):
	"""Call one ``ibd-rs-rating`` method through the shared read-through cache.

	This is the public adapter used by both this CLI and the composite pipeline;
	direct ``RS`` calls elsewhere would silently bypass the approved cache.
	"""
	_configure_cache(no_cache)
	params = dict(params or {})
	client = client if client is not None else _get_rs_client()
	method = getattr(client, function)
	return _cached_call(
		"ibd-rs-rating",
		symbol.upper(),
		function,
		params,
		lambda: method(**params),
		no_cache=no_cache,
	)


def _extract_close(history):
	"""Return a numeric close series from a yfinance frame or test fixture."""
	if isinstance(history, pd.Series):
		series = history.copy()
	elif isinstance(history, pd.DataFrame):
		if "Close" not in history.columns:
			raise ValueError("history does not contain a Close column")
		series = history["Close"].copy()
	else:
		series = pd.Series(history, dtype="float64")

	if isinstance(series, pd.DataFrame):
		if series.shape[1] != 1:
			raise ValueError("history contains ambiguous Close columns")
		series = series.iloc[:, 0]
	return pd.to_numeric(series, errors="coerce").dropna().astype(float)


def _midrank_percentile(values, current):
	"""Tie-neutral empirical percentile for a current rolling RS-line return.

	An inclusive ``<=`` ECDF would assign a perfectly flat RS line the 100th
	percentile because every observation ties. Midranks correctly place that
	uninformative all-tie case at 50 without inventing a second eligibility gate.
	"""
	clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
	if not clean or not math.isfinite(float(current)):
		return None
	equality = [math.isclose(value, current, rel_tol=1e-12, abs_tol=1e-12) for value in clean]
	less = sum(value < current and not tied for value, tied in zip(clean, equality))
	equal = sum(equality)
	return round((less + 0.5 * equal) / len(clean) * 100.0, 1)


def _compute_proxy_metrics(stock_close, spy_close, rs_days_lookback=DEFAULT_RS_DAYS_LOOKBACK):
	"""Compute deterministic local RS-line diagnostics from aligned closes.

	The historical percentiles are self-relative rolling distributions, not a
	cross-sectional IBD rank. The distinction is emitted in provenance because a
	local proxy must never masquerade as the unavailable backend measure.
	"""
	stock = _extract_close(stock_close).rename("stock")
	spy = _extract_close(spy_close).rename("spy")
	aligned = pd.concat([stock, spy], axis=1, join="inner").dropna()
	aligned = aligned[(aligned["stock"] > 0) & (aligned["spy"] > 0)]

	longest = PROXY_LOOKBACKS["12m"]
	# Twenty-one post-lookback observations are enough to define a distribution
	# while keeping recent IPO fallbacks honest about sparse evidence.
	minimum_points = longest + PROXY_LOOKBACKS["1m"]
	if len(aligned) < minimum_points:
		raise ValueError(
			f"local proxy needs at least {minimum_points} aligned sessions; received {len(aligned)}"
		)

	rs_line = aligned["stock"] / aligned["spy"]
	lookbacks = {}
	for label, sessions in PROXY_LOOKBACKS.items():
		rolling = rs_line.pct_change(periods=sessions, fill_method=None).dropna() * 100.0
		if rolling.empty:
			raise ValueError(f"local proxy cannot calculate the {label} RS-line measure")
		current = float(rolling.iloc[-1])
		lookbacks[label] = {
			"sessions": sessions,
			"rs_line_return_pct": round(current, 2),
			"historical_percentile": _midrank_percentile(rolling.tolist(), current),
			"sample_count": int(len(rolling)),
			"role": "eligibility" if label == "12m" else "timing_only",
		}

	stock_returns = aligned["stock"].pct_change(fill_method=None)
	spy_returns = aligned["spy"].pct_change(fill_method=None)
	paired_returns = pd.concat([stock_returns, spy_returns], axis=1).dropna().tail(rs_days_lookback)
	if paired_returns.empty:
		raise ValueError("local proxy cannot calculate RS-day share")
	rs_day_count = int((paired_returns["stock"] > paired_returns["spy"]).sum())
	rs_day_total = int(len(paired_returns))
	rs_day_share = round(rs_day_count / rs_day_total * 100.0, 1)

	eligibility_score = lookbacks["12m"]["historical_percentile"]
	return {
		"method": "stock close / SPY close RS line with self-historical rolling-return percentiles",
		"not_cross_sectional_rank": True,
		"aligned_sessions": int(len(aligned)),
		"rs_line": {
			"latest": round(float(rs_line.iloc[-1]), 6),
			"absolute_level_has_no_signal": True,
		},
		"rs_days": {
			"lookback_sessions": rs_day_total,
			"outperform_days": rs_day_count,
			"share_pct": rs_day_share,
			"threshold": "[TL] > 60% during a market correction",
			"passed_60pct": rs_day_share > 60.0,
			"role": "corroboration_only unless the selected window is a documented correction",
		},
		"lookbacks": lookbacks,
		"eligibility_score": eligibility_score,
		"eligibility_measure": "12m historical percentile only",
	}


def _fetch_proxy_history(symbol, period, no_cache=False):
	"""Fetch stock and SPY closes; the shared yfinance proxy owns caching."""
	# The cache-clock pass transparently wraps yfinance.Ticker.history. Keeping the
	# standard API here also leaves deterministic tests free to patch yf.Ticker.
	stock = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
	spy = yf.Ticker("SPY").history(period=period, interval="1d", auto_adjust=True)
	return _extract_close(stock), _extract_close(spy)


def _proxy_result(symbol, *, period=DEFAULT_PROXY_PERIOD, rs_days_lookback=DEFAULT_RS_DAYS_LOOKBACK, no_cache=False):
	stock_close, spy_close = _fetch_proxy_history(symbol, period, no_cache=no_cache)
	metrics = _compute_proxy_metrics(stock_close, spy_close, rs_days_lookback=rs_days_lookback)
	score = metrics["eligibility_score"]
	if score is None:
		raise ValueError("12m proxy percentile is unavailable")
	return {
		"status": "available",
		"score": score,
		"source": SOURCE_PROXY,
		"provisional": True,
		"passed": score >= MIN_RS_ELIGIBILITY,
		"threshold": MIN_RS_ELIGIBILITY,
		"proxy": metrics,
	}


def _backend_rating(record, ticker):
	"""Validate, but never recalculate, a rating returned by the package."""
	if not isinstance(record, dict):
		raise LookupError(f"no backend record found for {ticker}")
	raw_rating = record.get("rs_rating")
	if raw_rating is None:
		raise LookupError(f"no backend rating found for {ticker}")
	if isinstance(raw_rating, bool):
		raise ValueError(f"backend rating has invalid boolean type: {raw_rating}")
	try:
		rating = int(raw_rating)
	except (TypeError, ValueError) as exc:
		raise ValueError(f"backend rating is not an integer: {raw_rating}") from exc
	if str(raw_rating).strip() not in {str(rating), f"{rating}.0"} and not (
		isinstance(raw_rating, float) and raw_rating.is_integer()
	):
		raise ValueError(f"backend rating is not an integer: {raw_rating}")
	if not 1 <= rating <= 99:
		raise ValueError(f"backend rating outside 1-99: {rating}")
	return rating


def resolve_rs_score(
	symbol,
	*,
	no_cache=False,
	proxy_period=DEFAULT_PROXY_PERIOD,
	rs_days_lookback=DEFAULT_RS_DAYS_LOOKBACK,
	client=None,
):
	"""Resolve eligibility in binding order: backend, local proxy, unavailable."""
	ticker = symbol.upper()
	_configure_cache(no_cache)
	backend_error = None

	try:
		backend = call_backend(
			"get",
			symbol=ticker,
			params={"ticker": ticker},
			no_cache=no_cache,
			client=client,
		)
		rating = _backend_rating(backend, ticker)
		rating_date = backend.get("date")
		return {
			"status": "available",
			"score": rating,
			"rating_date": rating_date,
			"source": SOURCE_BACKEND,
			"provisional": False,
			"passed": rating >= MIN_RS_ELIGIBILITY,
			"threshold": MIN_RS_ELIGIBILITY,
			"backend_record": backend,
			"backend": {
				"status": "available",
				"rating_date": rating_date,
			},
		}
	except Exception as exc:
		backend_error = f"{type(exc).__name__}: {exc}"

	try:
		proxy = _proxy_result(
			ticker,
			period=proxy_period,
			rs_days_lookback=rs_days_lookback,
			no_cache=no_cache,
		)
		proxy["backend"] = {"status": "unavailable", "reason": backend_error}
		return proxy
	except Exception as exc:
		return {
			"status": "unavailable",
			"score": None,
			"source": None,
			"provisional": None,
			"passed": None,
			"threshold": MIN_RS_ELIGIBILITY,
			"backend": {"status": "unavailable", "reason": backend_error},
			"proxy": {
				"status": "unavailable",
				"reason": f"{type(exc).__name__}: {exc}",
			},
		}


def compute_rs_score(symbol, *, no_cache=False, details=False):
	"""Compatibility API used by Trend Template and external callers."""
	result = resolve_rs_score(symbol, no_cache=no_cache)
	return result if details else result.get("score")


def _backend_context(ticker, no_cache=False, client=None):
	"""Fetch optional history/reference context without changing eligibility."""
	history = None
	spy_rs = None
	try:
		history_rows = call_backend(
			"history",
			symbol=ticker,
			params={"ticker": ticker, "days": 253},
			no_cache=no_cache,
			client=client,
		) or []
		if history_rows:
			history = {}
			for label, offset in (("1w_ago", 5), ("1m_ago", 21), ("3m_ago", 63), ("6m_ago", 126)):
				if len(history_rows) > offset:
					history[label] = history_rows[offset].get("rs_rating")
	except Exception:
		history = None

	try:
		reference = call_backend("reference", params={}, no_cache=no_cache, client=client) or []
		spy_rs = next((row.get("rs_rating") for row in reference if row.get("ticker") == "SPY"), None)
	except Exception:
		spy_rs = None
	return history, spy_rs


@safe_run
def cmd_score(args):
	"""Resolve one ticker's RS eligibility with source and cache provenance."""
	_configure_cache(args.no_cache)
	ticker = args.symbol.upper()
	eligibility = resolve_rs_score(
		ticker,
		no_cache=args.no_cache,
		proxy_period=args.proxy_period,
		rs_days_lookback=args.rs_days_lookback,
	)
	history = None
	spy_rs = None
	if eligibility.get("source") == SOURCE_BACKEND:
		history, spy_rs = _backend_context(ticker, no_cache=args.no_cache)

	payload = {
		"symbol": ticker,
		"status": eligibility["status"],
		"rs_rating": eligibility.get("score"),
		"rating_date": eligibility.get("rating_date"),
		"eligibility": eligibility,
		"spy_rs": spy_rs,
		"history": history,
		"threshold": f"[M] RS >= {MIN_RS_ELIGIBILITY} for Trend Template criterion 8",
		"doctrine": DOCTRINE,
		"provenance": PROVENANCE,
	}
	if eligibility["status"] == "unavailable":
		payload["error"] = f"RS eligibility is unavailable for {ticker} from both configured sources"
	output_json(payload)
	if eligibility["status"] == "unavailable":
		raise SystemExit(1)


@safe_run
def cmd_screen(args):
	"""Screen the backend universe by its IBD-style rating."""
	_configure_cache(args.no_cache)
	try:
		stocks = call_backend(
			"filter",
			params={"min_rating": args.min_rating},
			no_cache=args.no_cache,
		) or []
	except Exception as exc:
		output_json({
			"error": f"RS screen backend unavailable: {exc}",
			"status": "unavailable",
			"doctrine": DOCTRINE,
			"provenance": PROVENANCE,
		})
		raise SystemExit(1)

	stocks = sorted(stocks, key=lambda row: row.get("rs_rating", 0), reverse=True)
	if args.limit:
		stocks = stocks[: args.limit]
	output_json({
		"status": "available",
		"data": stocks,
		"metadata": {"count": len(stocks), "min_rating": args.min_rating},
		"doctrine": DOCTRINE,
		"provenance": PROVENANCE,
	})


@safe_run
def cmd_compare(args):
	"""Compare backend ratings without substituting incomparable proxy ranks."""
	_configure_cache(args.no_cache)
	tickers = [symbol.upper() for symbol in args.symbols]
	try:
		results = call_backend(
			"compare",
			params={"tickers": tickers},
			no_cache=args.no_cache,
		) or []
	except Exception as exc:
		output_json({
			"error": f"RS compare backend unavailable: {exc}",
			"status": "unavailable",
			"doctrine": DOCTRINE,
			"provenance": PROVENANCE,
		})
		raise SystemExit(1)

	output_json({
		"status": "available",
		"rankings": results,
		"count": len(results),
		"doctrine": DOCTRINE,
		"provenance": PROVENANCE,
	})


def _add_cache_flag(parser):
	parser.add_argument(
		"--no-cache",
		action="store_true",
		help="Bypass shared cache reads and writes for this invocation",
	)


def main():
	parser = JsonArgumentParser(
		description="Relative-strength ranking: cached IBD-style backend, then labelled local proxy"
	)
	sub = parser.add_subparsers(dest="command", required=True)

	sp = sub.add_parser("score", help="Resolve RS eligibility for one ticker")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument(
		"--proxy-period",
		default=DEFAULT_PROXY_PERIOD,
		help=f"yfinance history used only by the local fallback (default: {DEFAULT_PROXY_PERIOD})",
	)
	sp.add_argument(
		"--rs-days-lookback",
		type=int,
		default=DEFAULT_RS_DAYS_LOOKBACK,
		help=f"Recent paired sessions for the [TL] RS-day diagnostic (default: {DEFAULT_RS_DAYS_LOOKBACK})",
	)
	_add_cache_flag(sp)
	sp.set_defaults(func=cmd_score)

	sp = sub.add_parser("screen", help="Screen the backend universe for high-RS stocks")
	sp.add_argument("--min-rating", type=int, default=80, help="Minimum backend RS rating (default: 80)")
	sp.add_argument("--limit", type=int, default=50, help="Maximum results (default: 50)")
	_add_cache_flag(sp)
	sp.set_defaults(func=cmd_screen)

	sp = sub.add_parser("compare", help="Compare backend RS ratings for multiple tickers")
	sp.add_argument("symbols", nargs="+", help="Ticker symbols to compare")
	_add_cache_flag(sp)
	sp.set_defaults(func=cmd_compare)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
