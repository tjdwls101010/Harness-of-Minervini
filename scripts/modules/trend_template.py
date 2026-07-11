#!/usr/bin/env python3
"""Minervini Trend Template: 8-criteria checklist for Stage 2 qualification.

Evaluates a stock against Mark Minervini's 8 Trend Template criteria to determine
whether it qualifies as a Stage 2 uptrend candidate. Each criterion is individually
scored with pass/fail, and an overall verdict is produced.

Commands:
	check: Run full 8-criteria Trend Template check for a single ticker

Args:
	symbol (str): Ticker symbol (e.g., "AAPL", "NVDA", "MSFT")
	--period (str): Historical data period for MA calculation (default: "2y")

Returns:
	dict: {
		"symbol": str,
		"date": str,
		"current_price": float,
		"criteria": [
			{
				"id": int,
				"description": str,
				"passed": bool,
				"value": float or str,
				"threshold": str
			}
		],
		"passed_count": int,
		"total_count": 8,
		"overall_pass": bool,
		"score_pct": float,
		"moving_averages": {
			"sma50": float,
			"sma150": float,
			"sma200": float,
			"sma200_1mo_ago": float
		}
	}

Example:
	>>> python trend_template.py check NVDA --period 2y
	{
		"symbol": "NVDA",
		"date": "2026-02-07",
		"current_price": 135.50,
		"criteria": [
			{"id": 1, "description": "Price > 150-day MA AND 200-day MA", "passed": true, "value": "135.50 > 120.30 (SMA150) & 110.80 (SMA200)", "threshold": "Price above both MAs"},
			...
		],
		"passed_count": 8,
		"total_count": 8,
		"overall_pass": true,
		"score_pct": 100.0
	}

Use Cases:
	- Quick qualification check for SEPA methodology stock selection
	- Filter universe to only Stage 2 uptrend candidates
	- Monitor existing positions for trend degradation
	- Batch screening when combined with watchlist

Notes:
	- All 8 criteria must pass for a stock to qualify as a Trend Template pass.
	- Criterion 8 resolves the project's authoritative ibd-rs-rating score first, then the labelled local proxy, then unavailable.
	- Only the local proxy's 12-month historical percentile may provisionally carry criterion 8; short lookbacks remain timing evidence.
	- 200-day MA uptrend check uses the original one-month minimum, with four-to-five months preferred.

See Also:
	- stage_analysis.py: Detailed Stage 1-4 classification
	- rs_ranking.py: Full RS ranking calculation and screening
	- pipeline qualify: Stage-2 plus Trend-Template hard-gate context
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import yfinance as yf
from rs_ranking import MIN_RS_ELIGIBILITY, resolve_rs_score
from utils import JsonArgumentParser, calculate_sma, error_json, output_json, safe_run


DOCTRINE = (
	"[M] The eight Trend Template criteria are a non-negotiable AND gate applied before fundamentals because price "
	"and institutional demand lead reported business results. Criterion 8 requires RS >= 70, with the 80s-90s "
	"preferred. A source outage is incomplete evidence, not evidence that the stock failed."
)

PROVENANCE = {
	"criteria_1_8": "[M] Minervini knowledge map, cluster C",
	"rs_fallback": "Harness spec Implementation rulings; [TL] 12M eligibility versus short-lookback timing separation",
}


def _configure_cache(no_cache=False):
	"""Configure the shared cache without making parser construction network-active."""
	try:
		from utils import cache_disabled, configure_cache
	except ImportError:
		return
	configure_cache(bool(no_cache) or cache_disabled())


def _criterion(identifier, description, passed, value, threshold):
	"""Build a criterion with a three-state contract."""
	status = "UNAVAILABLE" if passed is None else ("PASS" if passed else "FAIL")
	return {
		"id": identifier,
		"description": description,
		"status": status,
		"passed": passed,
		"value": value,
		"threshold": threshold,
	}


@safe_run
def cmd_check(args):
	"""Run 8-criteria Trend Template check."""
	_configure_cache(args.no_cache)
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1d")
	# Drop the partial current-session bar yfinance appends mid-day: its NaN OHLC
	# would make current_price NaN and silently fail all 8 criteria (1/8 for a
	# leader), turning the live gate into a blanket AVOID during market hours.
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 200:
		error_json(f"Insufficient data for {symbol}. Need at least 200 trading days; received {len(data)}.")

	closes = data["Close"]
	current_price = float(closes.iloc[-1])
	date_str = str(data.index[-1].date())

	# Calculate moving averages
	sma50 = calculate_sma(closes, 50)
	sma150 = calculate_sma(closes, 150)
	sma200 = calculate_sma(closes, 200)

	current_sma50 = float(sma50.iloc[-1])
	current_sma150 = float(sma150.iloc[-1])
	current_sma200 = float(sma200.iloc[-1])

	# 200-day MA from ~1 month ago (22 trading days)
	sma200_1mo_ago = float(sma200.iloc[-22]) if len(sma200) >= 22 else float(sma200.iloc[0])

	# 52-week high and low
	one_year_data = closes.tail(252) if len(closes) >= 252 else closes
	week52_high = float(one_year_data.max())
	week52_low = float(one_year_data.min())

	# Criterion 8 source order is binding: authoritative project backend, labelled
	# outage-only proxy, then unavailable. The detailed result preserves provenance.
	rs_result = resolve_rs_score(symbol, no_cache=args.no_cache)
	rs_score = rs_result.get("score")

	# Evaluate 8 criteria
	criteria = []

	# 1. Price > 150-day MA AND 200-day MA
	c1_pass = current_price > current_sma150 and current_price > current_sma200
	criteria.append(_criterion(
		1,
		"Price > 150-day MA AND 200-day MA",
		c1_pass,
		f"{current_price:.2f} vs SMA150={current_sma150:.2f}, SMA200={current_sma200:.2f}",
		"[M] Price above both MAs",
	))

	# 2. 150-day MA > 200-day MA
	c2_pass = current_sma150 > current_sma200
	criteria.append(_criterion(
		2,
		"150-day MA > 200-day MA",
		c2_pass,
		f"SMA150={current_sma150:.2f} vs SMA200={current_sma200:.2f}",
		"[M] SMA150 above SMA200",
	))

	# 3. 200-day MA trending up (at least 1 month)
	c3_pass = current_sma200 > sma200_1mo_ago
	c3_change = ((current_sma200 / sma200_1mo_ago) - 1) * 100 if sma200_1mo_ago > 0 else 0
	criteria.append(_criterion(
		3,
		"200-day MA trending up (at least 1 month)",
		c3_pass,
		f"SMA200 now={current_sma200:.2f} vs 1mo ago={sma200_1mo_ago:.2f} ({c3_change:+.2f}%)",
		"[M] SMA200 rising for 1+ month (4-5 months preferred)",
	))

	# 4. 50-day MA > 150-day MA AND 200-day MA
	c4_pass = current_sma50 > current_sma150 and current_sma50 > current_sma200
	criteria.append(_criterion(
		4,
		"50-day MA > 150-day MA AND 200-day MA",
		c4_pass,
		f"SMA50={current_sma50:.2f} vs SMA150={current_sma150:.2f}, SMA200={current_sma200:.2f}",
		"[M] SMA50 above both longer MAs",
	))

	# 5. Price > 50-day MA
	c5_pass = current_price > current_sma50
	criteria.append(_criterion(
		5,
		"Price > 50-day MA",
		c5_pass,
		f"{current_price:.2f} vs SMA50={current_sma50:.2f}",
		"[M] Price above SMA50",
	))

	# 6. Price >= 52-week low * 1.30 (at least 30% above)
	low_threshold = week52_low * 1.30
	c6_pass = current_price >= low_threshold
	pct_above_low = ((current_price / week52_low) - 1) * 100 if week52_low > 0 else 0
	criteria.append(_criterion(
		6,
		"Price at least 30% above 52-week low",
		c6_pass,
		f"{current_price:.2f} is {pct_above_low:.1f}% above 52w low {week52_low:.2f}",
		f"[M] Price >= {low_threshold:.2f} (52w low * 1.30)",
	))

	# 7. Price within 25% of 52-week high (>= 75% of high)
	high_threshold = week52_high * 0.75
	c7_pass = current_price >= high_threshold
	pct_from_high = ((current_price / week52_high) - 1) * 100 if week52_high > 0 else 0
	criteria.append(_criterion(
		7,
		"Price within 25% of 52-week high",
		c7_pass,
		f"{current_price:.2f} is {pct_from_high:.1f}% from 52w high {week52_high:.2f}",
		f"[M] Price >= {high_threshold:.2f} (52w high * 0.75)",
	))

	# 8. RS Ranking >= 70. Missing source data is not a failed criterion.
	c8_pass = rs_result.get("passed") if rs_result.get("status") == "available" else None
	rs_value = f"RS Score = {rs_score} ({rs_result.get('source')})" if rs_score is not None else "RS Score = unavailable"
	criteria.append(_criterion(
		8,
		"RS Ranking >= 70",
		c8_pass,
		rs_value,
		f"[M] RS >= {MIN_RS_ELIGIBILITY}; local proxy uses only its 12M historical percentile provisionally",
	))

	passed_count = sum(1 for c in criteria if c["passed"] is True)
	evaluated_count = sum(1 for c in criteria if c["passed"] is not None)
	if any(c["passed"] is False for c in criteria):
		overall_status = "FAIL"
		overall_pass = False
	elif any(c["passed"] is None for c in criteria):
		overall_status = "UNAVAILABLE"
		overall_pass = None
	elif passed_count == 8:
		overall_status = "PASS"
		overall_pass = True
	else:  # Defensive: eight determinate criteria should be covered above.
		overall_status = "UNAVAILABLE"
		overall_pass = None

	full_result = {
		"symbol": symbol,
		"date": date_str,
		"current_price": round(current_price, 2),
		"criteria": criteria,
		"passed_count": passed_count,
		"evaluated_count": evaluated_count,
		"total_count": 8,
		"overall_status": overall_status,
		"overall_pass": overall_pass,
		"score_pct": round(passed_count / 8 * 100, 1),
		"moving_averages": {
			"sma50": round(current_sma50, 2),
			"sma150": round(current_sma150, 2),
			"sma200": round(current_sma200, 2),
			"sma200_1mo_ago": round(sma200_1mo_ago, 2),
		},
		"week52": {
			"high": round(week52_high, 2),
			"low": round(week52_low, 2),
		},
		"rs_score": rs_score,
		"rs": rs_result,
		"doctrine": DOCTRINE,
		"provenance": PROVENANCE,
	}

	# Compressed view for pipeline consumption
	_compressed = {k: v for k, v in full_result.items()
				   if k not in ("symbol", "date", "current_price")}
	_pc = _compressed.pop("passed_count", 0)
	_ec = _compressed.pop("evaluated_count", 8)
	_tc = _compressed.pop("total_count", 8)
	_compressed.pop("overall_pass", None)
	_compressed.pop("score_pct", None)
	_compressed.pop("moving_averages", None)
	_compressed.pop("week52", None)
	_compressed["passed"] = f"{_pc}/{_tc}"
	_compressed["evaluated"] = f"{_ec}/{_tc}"
	# Remove description from each criterion (threshold suffices)
	_comp_criteria = _compressed.get("criteria", [])
	if _comp_criteria:
		_compressed["criteria"] = [{k: v for k, v in c.items() if k != "description"} for c in _comp_criteria]
	full_result["compressed"] = _compressed

	output_json(full_result)


def main():
	parser = JsonArgumentParser(description="Minervini Trend Template 8-criteria check")
	sub = parser.add_subparsers(dest="command", required=True)

	sp = sub.add_parser("check", help="Run Trend Template check for a ticker")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--period", default="2y", help="Data period (default: 2y)")
	sp.add_argument("--no-cache", action="store_true", help="Bypass shared cache reads and writes for this invocation")
	sp.set_defaults(func=cmd_check)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
