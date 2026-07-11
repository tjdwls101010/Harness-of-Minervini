#!/usr/bin/env python3
"""Earnings Acceleration Analysis: Code 33 validation and earnings pattern detection.

Analyzes earnings acceleration patterns to detect Code 33 (Triple Acceleration:
EPS + Sales + Margins all accelerating for 3 quarters), earnings surprise history,
and analyst revision trends.

Commands:
	code33: Check for Code 33 (Triple Acceleration) pattern
	acceleration: Analyze quarterly EPS and sales growth trends
	surprise: Get earnings surprise history and post-earnings drift signals
	revisions: Track analyst estimate revision trends
	valuation: Forward P/E + embedded-growth expectation barometer (NOT a gate;
		absorbs the former forward_pe module — no GARP cheap/expensive bands)
	margin: Net-headline quarterly margin trajectory (gross/op/net), no
		classification badge (absorbs the former margin_tracker module)

Args:
	symbol (str): Ticker symbol (e.g., "AAPL", "NVDA", "META")

Returns:
	For code33:
		dict: {
			"symbol": str,
			"code33_status": str,
			"eps_accelerating": bool,
			"eps_improving": bool,
			"sales_accelerating": bool,
			"sales_improving": bool,
			"margin_expanding": bool,
			"margin_basis": str,        # "net" | "operating" (fallback) | "unavailable"
			"margin_data_quality": str,
			"quarters_analyzed": int,
			"eps_growth_rates": [float],
			"sales_growth_rates": [float],
			"margin_trend": [float],
			"eps_quarters_available": int,
			"sales_quarters_available": int,
			"data_quality": str,
			"thresholds": {
				"acceleration": str,
				"improving": str,
				"margin_expansion": str,
				"margin_min_change_ppt": float
			}
		}

	For acceleration:
		dict: {
			"symbol": str,
			"eps_acceleration": [{"quarter": str, "growth_rate": float, "accelerating": bool, "improving": bool}],
			"sales_acceleration": [{"quarter": str, "growth_rate": float, "accelerating": bool, "improving": bool}],
			"overall_trend": str
		}

	For surprise:
		dict: {
			"symbol": str,
			"surprise_history": [{
				"date": str, "estimate": float, "actual": float,
				"surprise_pct": float, "pct_skipped_reason": str,
				"beat": bool,
				"eps_yoy_pct": float, "eps_qoq_pct": float,
				"revenue": float, "revenue_yoy_pct": float, "revenue_qoq_pct": float,
				"post_er_return_1d": float,
				"post_er_return_5d": float, "post_er_gap": float
			}],
			"consecutive_beats": int,
			"avg_surprise_pct": float,
			"avg_surprise_method": str,
			"cockroach_effect": str,
			"total_quarters_analyzed": int
		}

	For revisions:
		dict: {
			"symbol": str,
			"revision_direction": str,
			"current_quarter_revisions": dict,
			"next_quarter_revisions": dict
		}

Example:
	>>> python earnings_acceleration.py code33 NVDA
	{
		"symbol": "NVDA",
		"code33_status": "PASS",
		"eps_accelerating": true,
		"eps_improving": true,
		"sales_accelerating": true,
		"sales_improving": true,
		"margin_expanding": true,
		"margin_data_quality": "full",
		"eps_growth_rates": [25.3, 38.5, 52.1],
		"sales_growth_rates": [18.2, 28.7, 42.3]
	}

	>>> python earnings_acceleration.py acceleration AAPL
	{
		"symbol": "AAPL",
		"eps_acceleration": [
			{"quarter": "2025Q4", "growth_rate": 12.5, "accelerating": true, "improving": true},
			{"quarter": "2025Q3", "growth_rate": 8.2, "accelerating": false, "improving": false}
		],
		"overall_trend": "accelerating"
	}

	>>> python earnings_acceleration.py surprise NVDA
	{
		"symbol": "NVDA",
		"surprise_history": [
			{
				"date": "2025-11-20",
				"estimate": 0.81,
				"actual": 0.89,
				"surprise_pct": 9.88,
				"beat": true,
				"post_er_return_1d": 3.25,
				"post_er_return_5d": 5.12,
				"post_er_gap": 2.10
			}
		],
		"consecutive_beats": 4,
		"avg_surprise_pct": 8.45,
		"cockroach_effect": "strong",
		"total_quarters_analyzed": 8
	}

Use Cases:
	- Validate Code 33 for earnings-driven stock selection
	- Track earnings momentum for position management
	- Identify cockroach effect (one surprise predicts more)
	- Monitor analyst revisions for sentiment shifts

Notes:
	- [M] Code 33 requires 3 consecutive improvements (4 observations) in ALL three metrics
	- EPS growth rates compare to same quarter prior year (YoY)
	- Margin expansion uses NET margin (operating-margin fallback when net is unavailable, flagged via margin_basis; never gross)
	- [M] Margin acceleration is directional; --margin-min-ppt may impose a stricter heuristic
	- Analyst revisions of 5%+ are generally considered significant
	- Post-Earnings Drift: market underreacts to earnings surprises
	- Data quality levels: full (3+ quarters), partial (2 quarters), minimal (0-1 quarters)
	- Surprise % set to null when |estimate| < 0.05 (near-zero denominator floor)
	- Average surprise uses trimmed mean (top/bottom 10% removed) when 5+ data points available
	- accelerating: each quarter's growth rate > prior quarter's growth rate (rate of change)
	- improving: trajectory getting better (rates becoming less negative or more positive)

See Also:
	- trend_template.py: Trend Template check (price-based qualification)
	- stage_analysis.py: Stage classification (technical context)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import yfinance as yf
from utils import cache_disabled, configure_cache, error_json, output_json, safe_run

# --- Tunable defaults (CLI-overridable; see argparse) ----------------------
# [M] EPS YoY growth may be tuned upward with the regime, but 20% is the
# corpus-backed lower bound and may not be relaxed by a CLI override.
EPS_GROWTH_LOCKED_FLOOR_PCT = 20.0
_EPS_MIN_PCT = EPS_GROWTH_LOCKED_FLOOR_PCT
# Sales-strength fallback floor. yfinance gives only ~5 quarters of revenue =>
# at most ONE YoY rate, so the 3-consecutive-quarter ACCELERATION test the EPS
# leg uses (deep earnings_dates history) is structurally unobtainable for sales.
# When sales history is too shallow to test acceleration, the leg falls back to
# STRENGTH — is the most recent YoY revenue growth strong and positive? — which
# is the faithful substitute: revenue is the un-fakeable substrate ("EPS without
# sales is gimmickry"), so the leg's real job is to prove real top-line demand.
# A FLOOR, raisable per cohort/regime like the EPS bar.
_SALES_STRENGTH_MIN_PCT = 20.0
# Post-earnings drift horizons (trading days after the report). Drift is a
# multi-MONTH phenomenon (bigger surprises drift longer); 1/5d only catch the
# immediate gap — widen for the fuller effect.
_DRIFT_DAYS = "1,5"
# Consecutive-beat bucket cutoffs for the cockroach effect. Heuristic — depends
# on the cohort's beat base-rate; raise where beating is near-universal.
_COCKROACH_STRONG = 4
_COCKROACH_MODERATE = 2
# Rolling surprise-history lookback. Spec calls for a variable 4/6/8-quarter window.
_SURPRISE_QUARTERS = 8

# [M] Code 33 is three consecutive improvements in EPS, sales, and net margin.
# Three transitions require four observations; this is a locked definition.
CODE33_LOCKED_TRANSITIONS = 3
CODE33_LOCKED_OBSERVATIONS = CODE33_LOCKED_TRANSITIONS + 1
# [M] A +/-5% estimate revision is the corpus's meaningful-change reference.
# It is descriptive here, not an automatic qualification gate.
REVISION_SIGNIFICANCE_LOCKED_PCT = 5.0

_MODULE_DOCTRINE = (
	"[M] Earnings evidence is contextual, not a standalone buy signal: technical "
	"eligibility gates fundamentals, and EPS must be confirmed by sales, margins, "
	"expectation changes, and the stock's price/volume response."
)


def _emit_result(result, doctrine=None):
	"""Emit one JSON result with an explicit, provenance-tagged doctrine lens."""
	result.setdefault("doctrine", doctrine or _MODULE_DOCTRINE)
	output_json(result)


class _JsonArgumentParser(argparse.ArgumentParser):
	"""Route CLI usage errors through the module's JSON/exit-1 contract."""

	def __init__(self, *args, **kwargs):
		kwargs.setdefault("formatter_class", argparse.ArgumentDefaultsHelpFormatter)
		super().__init__(*args, **kwargs)

	def error(self, message):
		error_json(message)


def _get_quarterly_financials(symbol):
	"""Retrieve quarterly income statement data and earnings dates.

	Tries ticker.quarterly_income_stmt first for broader historical coverage
	(8+ quarters), falls back to get_income_stmt(freq="quarterly") if unavailable.
	"""
	ticker = yf.Ticker(symbol)

	# Try quarterly_income_stmt for more historical quarters
	income = None
	try:
		qi = ticker.quarterly_income_stmt
		if qi is not None and not qi.empty and len(qi.columns) >= 4:
			income = qi
	except Exception:
		pass

	# Fallback to standard API
	if income is None or income.empty:
		income = ticker.get_income_stmt(freq="quarterly")

	return ticker, income


def _get_eps_growth_from_earnings_dates(ticker, limit=12):
	"""Extract YoY EPS growth from earnings_dates (up to 12 quarters).

	earnings_dates provides more historical EPS data than income statements.
	Returns list of (quarter_label, growth_rate) tuples, most recent first.
	"""
	try:
		ed = ticker.get_earnings_dates(limit=limit)
	except Exception:
		return []

	if ed is None or ed.empty or "Reported EPS" not in ed.columns:
		return []

	# Filter rows with actual reported EPS
	ed = ed.dropna(subset=["Reported EPS"])
	if len(ed) < 5:  # Need at least 5 quarters for 1 YoY comparison
		return []

	# Sort by date descending
	ed = ed.sort_index(ascending=False)
	eps_values = list(zip(ed.index, ed["Reported EPS"]))

	results = []
	for i in range(len(eps_values)):
		current_date, current_eps = eps_values[i]
		# Find same quarter prior year (4 quarters back)
		yoy_idx = i + 4
		if yoy_idx < len(eps_values):
			prior_date, prior_eps = eps_values[yoy_idx]
			# A percent growth rate across a zero/negative EPS denominator is not
			# comparable with ordinary YoY growth; turnaround evidence is reported
			# elsewhere rather than smuggled into the acceleration sequence.
			if prior_eps > 0:
				growth = ((current_eps / prior_eps) - 1) * 100
				label = str(current_date.date()) if hasattr(current_date, "date") else str(current_date)
				results.append((label, round(growth, 2)))

	return results


def _extract_growth_series(income_df, metric_name):
	"""Extract YoY growth rates for a metric across quarters.

	Returns list of (quarter_label, growth_rate) tuples, most recent first.
	"""
	if income_df is None or income_df.empty:
		return []

	# income_df columns are dates, rows are metrics
	if metric_name not in income_df.index:
		return []

	values = income_df.loc[metric_name]
	# Sort by date descending (most recent first)
	values = values.sort_index(ascending=False)

	results = []
	dates = list(values.index)

	for i, date in enumerate(dates):
		current_val = values[date]
		if current_val is None or (hasattr(current_val, "__class__") and current_val != current_val):
			continue

		# Find same quarter from prior year (4 quarters back)
		yoy_idx = i + 4
		if yoy_idx < len(dates):
			prior_val = values[dates[yoy_idx]]
			if (
				prior_val is not None
				and float(prior_val) > 0
				and not (hasattr(prior_val, "__class__") and prior_val != prior_val)
			):
				growth = ((float(current_val) / float(prior_val)) - 1) * 100
				quarter_label = str(date.date()) if hasattr(date, "date") else str(date)
				results.append((quarter_label, round(growth, 2)))

	return results


def _is_accelerating(growth_rates, min_transitions=CODE33_LOCKED_TRANSITIONS):
	"""Check sequential acceleration across the requested number of transitions.

	Acceleration means the rate of change is improving, regardless of sign.
	Example: -20% -> -10% -> +5% IS acceleration (improving trajectory).

	growth_rates: list of (quarter, rate) tuples, most recent first.
	Returns (is_accelerating, is_improving, rates_used).
	  - accelerating: each rate > prior rate (rate of change improvement)
	  - improving: same as accelerating (rates becoming less negative or more positive)
	"""
	required_observations = min_transitions + 1
	if len(growth_rates) < required_observations:
		return False, False, []

	# Three improving quarters require four observed YoY rates.
	recent = growth_rates[:required_observations]
	rates = [r[1] for r in recent]

	# Accelerating means each quarter's growth > the previous quarter's growth
	# Since list is most-recent-first, rates[0] > rates[1] > rates[2]
	accelerating = all(rates[i] > rates[i + 1] for i in range(len(rates) - 1))

	# Improving: trajectory getting better (rates becoming less negative or more positive)
	# Same check as accelerating -- each rate > prior rate regardless of sign
	improving = accelerating

	return accelerating, improving, rates


def _is_decelerating(growth_rates, min_quarters=3):
	"""Check if growth rates are decelerating (each quarter's rate < prior quarter's rate).

	Minervini Ch.5: "A trend of material deceleration should raise suspicion."
	Example: 50% -> 40% -> 30% IS decelerating.
	"""
	if len(growth_rates) < min_quarters:
		return False

	recent = growth_rates[:min_quarters]
	rates = [r[1] for r in recent]

	# Decelerating: each rate < prior rate (most-recent-first: rates[0] < rates[1] < rates[2])
	return all(rates[i] < rates[i + 1] for i in range(len(rates) - 1))


def _is_growth_sufficient(growth_rates, min_pct=20.0):
	"""Check if most recent quarter's YoY growth meets minimum threshold.

	Minervini Ch.7: "20 to 25 percent year-over-year increases" minimum.
	"Really successful companies report 30 to 40 percent or more."
	"""
	if not growth_rates:
		return False
	most_recent_rate = growth_rates[0][1]
	return most_recent_rate >= min_pct


def _parse_drift_days(spec):
	"""Parse a comma-separated drift-horizon spec ('1,5') into a sorted int list."""
	days = sorted({int(p) for p in str(spec).split(",") if p.strip()})
	if not days or any(d < 1 for d in days):
		raise ValueError(f"--drift-days must be positive integers, got {spec!r}")
	return days


def _assess_data_quality(eps_count, sales_count):
	"""Assess earnings data completeness for analysis reliability."""
	min_count = min(eps_count, sales_count)
	if min_count >= 3:
		return "full"
	elif min_count >= 2:
		return "partial"
	else:
		return "minimal"


# [M] Code 33 specifies directional margin acceleration, so 0.0 is the
# canonical flex default. A caller may raise it (for example to the legacy
# 0.5-ppt heuristic), but that magnitude is implementation policy, not canon.
_MARGIN_MIN_CHANGE_PPT = 0.0


def _aligned_code33_evidence(income, margin_min_ppt):
	"""Evaluate canonical [M] Code 33 on one aligned fiscal-quarter table.

	Deep earnings-date history remains useful context, but a PASS is possible only
	when EPS, sales, and net margin share the same four recent fiscal-quarter labels
	and four YoY observations can be computed from eight consecutive columns.
	"""
	if income is None or income.empty:
		return {"data_complete": False, "reason": "income_statement_unavailable"}
	eps_metric = next((name for name in ("DilutedEPS", "Diluted EPS", "BasicEPS", "Basic EPS") if name in income.index), None)
	sales_metric = next((name for name in ("TotalRevenue", "Total Revenue", "OperatingRevenue", "Operating Revenue") if name in income.index), None)
	net_metric = next((name for name in ("NetIncome", "Net Income") if name in income.index), None)
	if not all((eps_metric, sales_metric, net_metric)):
		return {"data_complete": False, "reason": "aligned_eps_sales_npm_fields_required"}
	columns = sorted(list(income.columns), reverse=True)
	if len(columns) < CODE33_LOCKED_OBSERVATIONS + 4:
		return {"data_complete": False, "reason": "eight_aligned_fiscal_quarters_required"}

	eps_growth = []
	sales_growth = []
	margins = []
	labels = []
	for i in range(CODE33_LOCKED_OBSERVATIONS):
		current_col = columns[i]
		prior_col = columns[i + 4]
		values = (
			income.loc[eps_metric, current_col], income.loc[eps_metric, prior_col],
			income.loc[sales_metric, current_col], income.loc[sales_metric, prior_col],
			income.loc[net_metric, current_col],
		)
		if any(value is None or value != value for value in values):
			return {"data_complete": False, "reason": "missing_value_in_aligned_window"}
		current_eps, prior_eps, current_sales, prior_sales, current_net = map(float, values)
		if prior_eps <= 0 or prior_sales <= 0 or current_sales == 0:
			return {"data_complete": False, "reason": "nonpositive_aligned_growth_denominator"}
		label = _format_quarter(current_col)
		labels.append(label)
		eps_growth.append((label, round((current_eps / prior_eps - 1) * 100, 2)))
		sales_growth.append((label, round((current_sales / prior_sales - 1) * 100, 2)))
		margins.append(round(current_net / current_sales * 100, 2))

	eps_accelerating = _is_accelerating(eps_growth)[0]
	sales_accelerating = _is_accelerating(sales_growth)[0]
	margin_deltas = [margins[i] - margins[i + 1] for i in range(CODE33_LOCKED_TRANSITIONS)]
	margin_accelerating = all(delta > 0 if margin_min_ppt == 0 else delta >= margin_min_ppt for delta in margin_deltas)
	return {
		"data_complete": True,
		"aligned_quarters": labels,
		"eps_growth_rates": [rate for _, rate in eps_growth],
		"sales_growth_rates": [rate for _, rate in sales_growth],
		"net_margin_pct": margins,
		"eps_accelerating": eps_accelerating,
		"sales_accelerating": sales_accelerating,
		"net_margin_accelerating": margin_accelerating,
		"pass": eps_accelerating and sales_accelerating and margin_accelerating,
	}


@safe_run
def cmd_code33(args):
	"""Check for Code 33 (Triple Acceleration) pattern."""
	configure_cache(args.no_cache or cache_disabled())
	if args.eps_min_pct < EPS_GROWTH_LOCKED_FLOOR_PCT:
		raise ValueError(
			f"--eps-min-pct cannot be below the [M] locked floor of {EPS_GROWTH_LOCKED_FLOOR_PCT:g}%"
		)
	if args.margin_min_ppt < 0 or args.sales_min_pct < 0:
		raise ValueError("--margin-min-ppt and --sales-min-pct must be non-negative")
	symbol = args.symbol.upper()
	ticker, income = _get_quarterly_financials(symbol)

	if income is None or income.empty:
		error_json(f"No quarterly financial data available for {symbol}")

	# EPS acceleration: prefer earnings_dates (12+ quarters) over income statement (5 quarters)
	eps_growth = _get_eps_growth_from_earnings_dates(ticker)
	eps_metric = "Reported EPS (earnings_dates)"
	if not eps_growth:
		# Fallback to income statement
		eps_metric = next(
			(
				m
				for m in ["DilutedEPS", "Diluted EPS", "BasicEPS", "Basic EPS", "NetIncome", "Net Income"]
				if m in income.index
			),
			"NetIncome",
		)
		eps_growth = _extract_growth_series(income, eps_metric)
	eps_acc, eps_improving, eps_rates = _is_accelerating(eps_growth)

	# Sales acceleration
	sales_metric = next(
		(m for m in ["TotalRevenue", "Total Revenue", "OperatingRevenue", "Operating Revenue"] if m in income.index),
		"TotalRevenue",
	)
	sales_growth = _extract_growth_series(income, sales_metric)
	sales_acc, sales_improving, sales_rates = _is_accelerating(sales_growth)

	# Sales-leg qualification under real-world data depth. yfinance caps quarterly
	# revenue at ~5 quarters => at most ONE YoY rate, so the strict 3-quarter
	# acceleration test (which the EPS leg runs on deep earnings_dates history) is
	# structurally unobtainable for sales. Qualify by data depth, never silently
	# failing: four YoY observations -> test three acceleration transitions; 1-3 ->
	# test STRENGTH (latest YoY >= --sales-min-pct, positive), the un-fakeable-
	# substrate read the leg exists to confirm; 0 rates -> insufficient.
	n_sales_rates = len(sales_growth)
	if n_sales_rates >= CODE33_LOCKED_OBSERVATIONS:
		sales_basis = "acceleration"
		sales_qualifies = sales_acc
		sales_data_quality = "full"
	elif n_sales_rates >= 1:
		sales_basis = "strength_shallow"
		sales_qualifies = sales_growth[0][1] >= args.sales_min_pct
		sales_data_quality = "shallow"
	else:
		sales_basis = "insufficient"
		sales_qualifies = False
		sales_data_quality = "insufficient"

	# Margin expansion — NET margin (NetIncome / Revenue). The margin leg exists to
	# confirm the acceleration survives ALL the way down the income statement, not
	# just at the gross line. Gross margin is blind to operating leverage: a business
	# can hold gross flat while SG&A leverage expands net margin, or paper over opex
	# bloat behind a strong gross line — exactly the cost-structure-blind "growth"
	# Code 33 is built to reject (its whole reason to exist). So: NET margin, falling
	# back to OPERATING (flagged via margin_basis) only when net income is missing.
	# Never gross.
	margin_expanding = False
	margin_data_quality = "insufficient"
	margin_values = []
	net_metric = next((m for m in ["NetIncome", "Net Income"] if m in income.index), None)
	op_metric = next((m for m in ["OperatingIncome", "Operating Income"] if m in income.index), None)
	if net_metric is not None:
		income_metric, margin_basis = net_metric, "net"
	elif op_metric is not None:
		income_metric, margin_basis = op_metric, "operating"
	else:
		income_metric, margin_basis = None, "unavailable"

	if income_metric is not None and sales_metric in income.index:
		earnings_line = income.loc[income_metric].sort_index(ascending=False)
		revenue = income.loc[sales_metric].sort_index(ascending=False)
		for i in range(min(5, len(earnings_line))):
			e = earnings_line.iloc[i]
			rev = revenue.iloc[i]
			# Guard None and NaN (x != x is True only for NaN).
			if e is None or rev is None or e != e or rev != rev:
				continue
			rev_f = float(rev)
			if rev_f != 0:
				margin_values.append(round(float(e) / rev_f * 100, 2))

		# margin_values is most-recent-first; 3 consecutive expansions each >=
		# margin_min_ppt above the prior quarter needs >= 4 points (3
		# comparisons). With fewer, the claim cannot be made.
		if len(margin_values) >= 4:
			consecutive = 0
			for i in range(len(margin_values) - 1):
				delta = margin_values[i] - margin_values[i + 1]
				meets_change = delta > 0 if args.margin_min_ppt == 0 else delta >= args.margin_min_ppt
				if meets_change:
					consecutive += 1
				else:
					break
			margin_expanding = consecutive >= 3
			margin_data_quality = "full"

	aligned_code33 = _aligned_code33_evidence(income, args.margin_min_ppt)
	code33_data_complete = aligned_code33["data_complete"]
	code33_pass = bool(aligned_code33.get("pass"))
	eps_sufficient = _is_growth_sufficient(eps_growth, min_pct=args.eps_min_pct)
	eps_decel = _is_decelerating(eps_growth)
	sales_decel = _is_decelerating(sales_growth)

	full_result = {
		"symbol": symbol,
		"code33_status": "PASS" if code33_pass else "FAIL" if code33_data_complete else "UNAVAILABLE",
		"code33_data_complete": code33_data_complete,
		"aligned_code33": aligned_code33,
		"eps_accelerating": eps_acc,
		"eps_improving": eps_improving,
		"eps_growth_sufficient": eps_sufficient,
		"eps_decelerating": eps_decel,
		"eps_growth_rates": eps_rates,
		"eps_quarters": [q[0] for q in eps_growth[:CODE33_LOCKED_OBSERVATIONS]] if eps_growth else [],
		"sales_accelerating": sales_acc,
		"sales_qualifies": sales_qualifies,
		"sales_basis": sales_basis,
		"sales_data_quality": sales_data_quality,
		"sales_improving": sales_improving,
		"sales_decelerating": sales_decel,
		"sales_growth_rates": sales_rates,
		"sales_quarters": [q[0] for q in sales_growth[:CODE33_LOCKED_OBSERVATIONS]] if sales_growth else [],
		"margin_expanding": margin_expanding,
		"margin_basis": margin_basis,
		"margin_data_quality": margin_data_quality,
		"margin_values_pct": margin_values[:5] if margin_values else [],
		"quarters_analyzed": min(len(eps_growth), len(sales_growth)),
		"data_quality": _assess_data_quality(len(eps_growth), len(sales_growth)),
		"thresholds": {
			"accelerating": "[M] 3 consecutive improvements, requiring 4 observed YoY growth rates",
			"growth_sufficient": f"[M] most recent quarter YoY >= {args.eps_min_pct:g}% (locked floor {EPS_GROWTH_LOCKED_FLOOR_PCT:g}%; raise with the regime)",
			"decelerating": "[M] 3 consecutive quarters with decreasing growth rate = warning",
			"code33": (
				"[M] EPS + sales + NET margin each accelerate for 3 transitions across the same 4 fiscal-quarter labels (requiring 8 aligned statement quarters for YoY rates). "
				f"Shallow sales strength >= {args.sales_min_pct:g}% is an implementation proxy reported "
				"for context and can never produce a canonical PASS."
			),
			"margin_expansion": f"[M] 3 consecutive NET-margin improvements; {args.margin_min_ppt:g} ppt is a flexible implementation heuristic (0 = source-backed directional test). Operating fallback is non-canonical context.",
		},
		"doctrine": (
			"[M] Acceleration is read against the stock's OWN history — the first material "
			"*deceleration* tops the stock even when the absolute level is still high, "
			"because price was priced for the prior rate and the market trades the delta "
			"from expectation, not the level. So don't be reassured by 'still growing "
			"nicely' — a falling second derivative breaks the discounting. (Dell EPS "
			"growth 80→65→28% topped despite 'decent growth,' then −80%.)"
		),
	}

	# Compressed view for pipeline consumption
	compressed = {}
	for key in ("eps_accelerating", "eps_improving", "sales_accelerating",
				"sales_qualifies", "sales_basis", "sales_data_quality",
				"sales_improving", "margin_expanding", "margin_basis", "margin_data_quality",
				"data_quality", "quarters_analyzed", "code33_status", "code33_data_complete"):
		if key in full_result:
			compressed[key] = full_result[key]
	for key in ("eps_growth_rates", "sales_growth_rates", "margin_values_pct"):
		if key in full_result:
			val = full_result[key]
			if isinstance(val, list):
				compressed[key] = val[:3]
	if "thresholds" in full_result:
		compressed["thresholds"] = full_result["thresholds"]
	compressed["growth_rates_order"] = "newest_first"
	full_result["compressed"] = compressed

	_emit_result(full_result)


@safe_run
def cmd_acceleration(args):
	"""Analyze quarterly EPS and sales growth acceleration trends."""
	configure_cache(args.no_cache or cache_disabled())
	symbol = args.symbol.upper()
	ticker, income = _get_quarterly_financials(symbol)

	if income is None or income.empty:
		error_json(f"No quarterly financial data available for {symbol}")

	# EPS acceleration: prefer earnings_dates (12+ quarters) over income statement
	eps_growth = _get_eps_growth_from_earnings_dates(ticker)
	eps_metric = "Reported EPS (earnings_dates)"
	if not eps_growth:
		eps_metric = next(
			(
				m
				for m in ["DilutedEPS", "Diluted EPS", "BasicEPS", "Basic EPS", "NetIncome", "Net Income"]
				if m in income.index
			),
			"NetIncome",
		)
		eps_growth = _extract_growth_series(income, eps_metric)

	eps_results = []
	for i, (quarter, rate) in enumerate(eps_growth):
		if i + 1 < len(eps_growth):
			acc = rate > eps_growth[i + 1][1]
			imp = acc  # improving = same as accelerating (rate of change improvement)
		else:
			acc = None
			imp = None
		eps_results.append(
			{
				"quarter": quarter,
				"growth_rate_yoy": rate,
				"accelerating": acc,
				"improving": imp,
			}
		)

	# Sales acceleration
	sales_metric = next(
		(m for m in ["TotalRevenue", "Total Revenue", "OperatingRevenue", "Operating Revenue"] if m in income.index),
		"TotalRevenue",
	)
	sales_growth = _extract_growth_series(income, sales_metric)

	sales_results = []
	for i, (quarter, rate) in enumerate(sales_growth):
		if i + 1 < len(sales_growth):
			acc = rate > sales_growth[i + 1][1]
			imp = acc
		else:
			acc = None
			imp = None
		sales_results.append(
			{
				"quarter": quarter,
				"growth_rate_yoy": rate,
				"accelerating": acc,
				"improving": imp,
			}
		)

	# Overall trend
	if len(eps_results) >= 2:
		recent_eps_acc = eps_results[0].get("accelerating", False)
		recent_sales_acc = sales_results[0].get("accelerating", False) if sales_results else False
		if recent_eps_acc and recent_sales_acc:
			overall = "strongly_accelerating"
		elif recent_eps_acc or recent_sales_acc:
			overall = "accelerating"
		elif eps_results[0]["growth_rate_yoy"] > 0:
			overall = "growing_but_decelerating"
		else:
			overall = "declining"
	else:
		overall = "insufficient_data"

	_emit_result(
		{
			"symbol": symbol,
			"eps_metric_used": eps_metric,
			"eps_acceleration": eps_results,
			"sales_metric_used": sales_metric,
			"sales_acceleration": sales_results,
			"overall_trend": overall,
			"thresholds": {
				"accelerating": "[M] current quarter growth rate > prior quarter growth rate (sign-agnostic)",
				"improving": "[M] rates becoming less negative or more positive",
			},
		},
		"[M] Acceleration is relative to the company's own history; material deceleration can be a top warning even while absolute growth remains positive.",
	)


def _enrich_post_er_reactions(ticker, surprises, drift_days=(1, 5)):
	"""Add post-earnings price reaction fields to each surprise entry.

	For each earnings date, fetches surrounding price data and calculates:
	- post_er_gap: gap from pre-ER close to next day open (%)
	- post_er_return_{n}d for each n in drift_days: pre-ER close to the n-th
	  trading day's close (%). Default (1, 5) yields post_er_return_1d and
	  post_er_return_5d (1d catches the gap; 5d+ catch the longer drift).

	Modifies surprises list in-place. Sets fields to None if data unavailable.
	"""
	from datetime import timedelta

	import pandas as pd

	# Keys this function owns; used to null out cleanly when data is unavailable.
	return_keys = [f"post_er_return_{n}d" for n in drift_days]

	# Null-out path mirrors the original key order (returns first, then gap).
	def _null_out(s):
		for k in return_keys:
			s[k] = None
		s["post_er_gap"] = None

	if not surprises:
		return

	# Parse all earnings dates
	er_dates = []
	for s in surprises:
		try:
			dt = pd.Timestamp(s["date"])
			er_dates.append(dt)
		except (ValueError, TypeError):
			er_dates.append(None)

	# Find date range for a single batch history fetch
	valid_dates = [d for d in er_dates if d is not None]
	if not valid_dates:
		for s in surprises:
			_null_out(s)
		return

	# Window must span the longest requested drift horizon. 15 calendar days
	# safely covers up to ~10 trading days (the default 1/5d); only widen the
	# fetch when a longer horizon is requested (keeps the default fetch unchanged).
	max_h = max(drift_days)
	latest_slack = 15 if max_h <= 10 else int(max_h * 1.5) + 10
	earliest = min(valid_dates) - timedelta(days=5)
	latest = max(valid_dates) + timedelta(days=latest_slack)

	# Fetch price history in one batch call
	try:
		hist = ticker.history(start=earliest, end=latest, auto_adjust=False)
		if hist is not None and not hist.empty:
			# Drop yfinance's trailing partial-session bar (NaN OHLC) before use.
			hist = hist.dropna(subset=["Open", "Close"])
	except Exception:
		hist = None

	if hist is None or hist.empty:
		for s in surprises:
			_null_out(s)
		return

	# Normalize index to date-only for reliable comparison
	hist.index = hist.index.normalize()
	if hist.index.tz is not None:
		hist.index = hist.index.tz_localize(None)

	for i, s in enumerate(surprises):
		er_dt = er_dates[i]
		if er_dt is None:
			_null_out(s)
			continue

		try:
			er_dt_norm = pd.Timestamp(er_dt).normalize()

			# Find pre-ER close: last trading day on or before earnings date
			mask_on_or_before = hist.index <= er_dt_norm
			if not mask_on_or_before.any():
				_null_out(s)
				continue

			pre_er_idx = hist.index[mask_on_or_before][-1]
			pre_er_close = float(hist.loc[pre_er_idx, "Close"])

			if pre_er_close <= 0:
				_null_out(s)
				continue

			# Trading days after earnings date
			mask_after = hist.index > er_dt_norm
			days_after = hist.index[mask_after]

			# post_er_gap: next trading day open vs pre-ER close
			if len(days_after) >= 1:
				next_day = days_after[0]
				next_open = float(hist.loc[next_day, "Open"])
				s["post_er_gap"] = round((next_open / pre_er_close - 1) * 100, 2)
			else:
				s["post_er_gap"] = None

			# post_er_return_{n}d: n-th trading-day close vs pre-ER close, per horizon
			for n, key in zip(drift_days, return_keys):
				if len(days_after) >= n:
					day_n = days_after[n - 1]
					day_n_close = float(hist.loc[day_n, "Close"])
					s[key] = round((day_n_close / pre_er_close - 1) * 100, 2)
				else:
					s[key] = None

		except (KeyError, IndexError, TypeError, ValueError):
			_null_out(s)


@safe_run
def cmd_surprise(args):
	"""Get earnings surprise history and post-earnings drift signals.

	Uses get_earnings_dates(limit=20) for up to 8 quarters of EPS data,
	enriched with revenue from quarterly_income_stmt and EPS/Revenue YoY/QoQ growth.
	"""
	configure_cache(args.no_cache or cache_disabled())
	if args.quarters < 1:
		raise ValueError("--quarters must be at least 1")
	if args.cockroach_moderate < 1 or args.cockroach_strong < args.cockroach_moderate:
		raise ValueError("cockroach cutoffs must satisfy 1 <= moderate <= strong")
	import pandas as pd

	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)

	# Get earnings dates (replaces get_earnings_history for broader coverage)
	try:
		earnings_dates = ticker.get_earnings_dates(limit=20)
	except Exception:
		earnings_dates = None

	if earnings_dates is None or (hasattr(earnings_dates, "empty") and earnings_dates.empty):
		error_json(f"No earnings history available for {symbol}")

	# Filter to reported results only (future entries have NaN Reported EPS)
	ed = earnings_dates.dropna(subset=["Reported EPS"])
	if ed.empty:
		error_json(f"No reported earnings available for {symbol}")

	# Sort by date descending (most recent first)
	ed = ed.sort_index(ascending=False)

	# Build surprise entries from earnings_dates
	surprises = []
	for idx, row in ed.iterrows():
		try:
			est_f = float(row.get("EPS Estimate")) if pd.notna(row.get("EPS Estimate")) else None
			act_f = float(row["Reported EPS"])
			if act_f != act_f:  # NaN check
				continue
		except (ValueError, TypeError):
			continue

		if est_f is not None and est_f != est_f:  # NaN check on estimate
			est_f = None

		surprise_pct = None
		pct_skipped_reason = None
		beat = None

		if est_f is not None:
			if abs(est_f) < 0.05:
				surprise_pct = None
				pct_skipped_reason = "estimate_near_zero"
			else:
				surprise_pct = round(((act_f - est_f) / abs(est_f) * 100), 2)
				pct_skipped_reason = None
			beat = act_f > est_f

		date_str = str(idx.date()) if hasattr(idx, "date") else str(idx)
		surprises.append({
			"date": date_str,
			"estimate": est_f,
			"actual": act_f,
			"surprise_pct": surprise_pct,
			"pct_skipped_reason": pct_skipped_reason,
			"beat": beat,
		})

	# EPS YoY/QoQ growth calculation
	for i, entry in enumerate(surprises):
		current_eps = entry["actual"]
		# QoQ: compare with previous quarter (index i+1, since list is descending)
		if i + 1 < len(surprises):
			prior_eps = surprises[i + 1]["actual"]
			if prior_eps is not None and abs(prior_eps) >= 0.01:
				entry["eps_qoq_pct"] = round(((current_eps - prior_eps) / abs(prior_eps)) * 100, 2)
			else:
				entry["eps_qoq_pct"] = None
		else:
			entry["eps_qoq_pct"] = None
		# YoY: compare with same quarter 4 entries back
		if i + 4 < len(surprises):
			prior_eps = surprises[i + 4]["actual"]
			if prior_eps is not None and abs(prior_eps) >= 0.01:
				entry["eps_yoy_pct"] = round(((current_eps - prior_eps) / abs(prior_eps)) * 100, 2)
			else:
				entry["eps_yoy_pct"] = None
		else:
			entry["eps_yoy_pct"] = None

	# Revenue enrichment from quarterly_income_stmt
	try:
		qi = ticker.quarterly_income_stmt
		if qi is not None and not qi.empty:
			revenue_metric = next(
				(m for m in ["TotalRevenue", "Total Revenue"] if m in qi.index), None
			)
			if revenue_metric:
				rev_series = qi.loc[revenue_metric].sort_index(ascending=False)
				rev_dates = list(rev_series.index)
				rev_values = list(rev_series.values)

				# Match each surprise entry to nearest income_stmt quarter (+-45 days)
				for entry in surprises:
					try:
						entry_dt = pd.Timestamp(entry["date"])
					except (ValueError, TypeError):
						entry["revenue"] = None
						entry["revenue_yoy_pct"] = None
						entry["revenue_qoq_pct"] = None
						continue

					best_match_idx = None
					best_delta = None
					for ri, rd in enumerate(rev_dates):
						rd_ts = pd.Timestamp(rd)
						delta = abs((entry_dt - rd_ts).days)
						if delta <= 45 and (best_delta is None or delta < best_delta):
							best_delta = delta
							best_match_idx = ri

					if best_match_idx is not None:
						rev_val = rev_values[best_match_idx]
						if pd.notna(rev_val):
							entry["revenue"] = float(rev_val)
							# Revenue QoQ
							if best_match_idx + 1 < len(rev_values):
								prior_rev = rev_values[best_match_idx + 1]
								if pd.notna(prior_rev) and abs(float(prior_rev)) > 0:
									entry["revenue_qoq_pct"] = round(
										((float(rev_val) - float(prior_rev)) / abs(float(prior_rev))) * 100, 2
									)
								else:
									entry["revenue_qoq_pct"] = None
							else:
								entry["revenue_qoq_pct"] = None
							# Revenue YoY
							if best_match_idx + 4 < len(rev_values):
								prior_rev = rev_values[best_match_idx + 4]
								if pd.notna(prior_rev) and abs(float(prior_rev)) > 0:
									entry["revenue_yoy_pct"] = round(
										((float(rev_val) - float(prior_rev)) / abs(float(prior_rev))) * 100, 2
									)
								else:
									entry["revenue_yoy_pct"] = None
							else:
								entry["revenue_yoy_pct"] = None
						else:
							entry["revenue"] = None
							entry["revenue_yoy_pct"] = None
							entry["revenue_qoq_pct"] = None
					else:
						entry["revenue"] = None
						entry["revenue_yoy_pct"] = None
						entry["revenue_qoq_pct"] = None
			else:
				for entry in surprises:
					entry["revenue"] = None
					entry["revenue_yoy_pct"] = None
					entry["revenue_qoq_pct"] = None
		else:
			for entry in surprises:
				entry["revenue"] = None
				entry["revenue_yoy_pct"] = None
				entry["revenue_qoq_pct"] = None
	except Exception:
		for entry in surprises:
			entry.setdefault("revenue", None)
			entry.setdefault("revenue_yoy_pct", None)
			entry.setdefault("revenue_qoq_pct", None)

	# Cap to the lookback window
	surprises = surprises[:args.quarters]

	# Enrich with post-ER price reaction data
	_enrich_post_er_reactions(ticker, surprises, _parse_drift_days(args.drift_days))

	# Consecutive beats
	consecutive_beats = 0
	for s in surprises:
		if s.get("beat"):
			consecutive_beats += 1
		else:
			break

	# Average surprise (Fix 1: trimmed mean with empty-slice fallback)
	valid_surprises = [s["surprise_pct"] for s in surprises if s["surprise_pct"] is not None]
	if len(valid_surprises) >= 5:
		# Implementation statistic: remove a full 10% from each tail only when
		# the sample is large enough; never force-trim a 5-9 point sample.
		import numpy as np
		sorted_vals = sorted(valid_surprises)
		trim_count = len(sorted_vals) // 10
		trimmed = sorted_vals[trim_count:-trim_count] if trim_count else sorted_vals
		avg_surprise_method = "trimmed_mean" if trim_count else "simple_mean"
		avg_surprise = round(float(np.mean(trimmed)), 2)
	else:
		avg_surprise = round(sum(valid_surprises) / len(valid_surprises), 2) if valid_surprises else None
		avg_surprise_method = "simple_mean" if valid_surprises else "unavailable"

	# Cockroach effect assessment
	if consecutive_beats >= args.cockroach_strong:
		cockroach = "strong"
	elif consecutive_beats >= args.cockroach_moderate:
		cockroach = "moderate"
	else:
		cockroach = "none"

	full_result = {
		"symbol": symbol,
		"surprise_history": surprises,
		"consecutive_beats": consecutive_beats,
		"avg_surprise_pct": avg_surprise,
		"avg_surprise_method": avg_surprise_method,
		"cockroach_effect": cockroach,
		"total_quarters_analyzed": len(surprises),
		"thresholds": {
			"post_earnings_drift": "[M] concept; concrete --drift-days horizons are flexible implementation windows",
			"lookback_quarters": f"implementation window: {args.quarters}",
			"cockroach_cutoffs": f"implementation heuristic (not doctrine): moderate={args.cockroach_moderate}, strong={args.cockroach_strong}",
			"near_zero_estimate": "implementation data-quality floor: |estimate| < 0.05 suppresses unstable percentages",
		},
	}

	# Compressed view: cap surprise_history to 8 entries
	compressed = {k: v for k, v in full_result.items() if k not in ("symbol",)}
	history = compressed.get("surprise_history", [])
	if len(history) > 8:
		compressed["surprise_history"] = history[:8]
	full_result["compressed"] = compressed

	# Added after compressed is built so doctrine stays a top-level lens only.
	full_result["doctrine"] = (
		"[M] A beat only carries information relative to expectations the company did NOT "
		"engineer: a sandbagged or lowered bar inverts the meaning of the same headline "
		"beat, so read WHO moved consensus. The cleanest signal is a beat PLUS a "
		"voluntary guidance RAISE — a costly signal management won't issue unless it can "
		"beat the raised bar. And post-earnings drift is a liquidity phenomenon: large "
		"buyers can't deploy at once, so a real surprise opens a multi-month window of "
		"forced accumulation — bigger surprises drift longer, not a free lunch in "
		"inefficiency."
	)

	_emit_result(full_result)


@safe_run
def cmd_revisions(args):
	"""Track analyst estimate revision trends."""
	configure_cache(args.no_cache or cache_disabled())
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)

	# EPS revisions
	eps_revisions = ticker.get_eps_revisions()
	eps_trend = ticker.get_eps_trend()
	growth_estimates = ticker.get_growth_estimates()

	full_result = {
		"symbol": symbol,
		"eps_revisions": eps_revisions,
		"eps_trend": eps_trend,
		"growth_estimates": growth_estimates,
		"interpretation": {
			"upward_revisions": "Positive - analysts raising estimates indicates strengthening fundamentals",
			"downward_revisions": "Negative - analysts cutting estimates signals potential weakness",
			"significance_threshold": f"[M] {REVISION_SIGNIFICANCE_LOCKED_PCT:g}%+ revision is meaningful context, not an automatic gate",
		},
		"thresholds": {
			"meaningful_revision_pct": f"[M] +/-{REVISION_SIGNIFICANCE_LOCKED_PCT:g}%",
			"gate": "none; revisions are contextual evidence",
		},
	}

	# Compressed view for pipeline consumption
	compressed = {}
	def as_column_mapping(value):
		"""Normalize yfinance DataFrame/dict tables to {column: {row: value}}."""
		if hasattr(value, "to_dict"):
			value = value.to_dict()
		return value if isinstance(value, dict) else {}

	revisions = as_column_mapping(full_result.get("eps_revisions", {}))
	up_30d = revisions.get("upLast30days", {}) if isinstance(revisions, dict) else {}
	down_30d = revisions.get("downLast30days", {}) if isinstance(revisions, dict) else {}
	net_up = sum(up_30d.get(k, 0) for k in ("0q", "+1q", "0y", "+1y")) if isinstance(up_30d, dict) else 0
	net_down = sum(down_30d.get(k, 0) for k in ("0q", "+1q", "0y", "+1y")) if isinstance(down_30d, dict) else 0
	compressed["direction"] = "up" if net_up > net_down else "down" if net_down > net_up else "flat"

	_eps_trend = as_column_mapping(full_result.get("eps_trend", {}))
	_current = _eps_trend.get("current", {}) if isinstance(_eps_trend, dict) else {}
	compressed["current_quarter_estimate"] = _current.get("0q") if isinstance(_current, dict) else None

	_ago_7d = _eps_trend.get("7daysAgo", {}) if isinstance(_eps_trend, dict) else {}
	_ago_30d = _eps_trend.get("30daysAgo", {}) if isinstance(_eps_trend, dict) else {}
	_ago_90d = _eps_trend.get("90daysAgo", {}) if isinstance(_eps_trend, dict) else {}
	cq = _current.get("0q") if isinstance(_current, dict) else None
	if cq and isinstance(_ago_7d, dict) and _ago_7d.get("0q"):
		compressed["revision_7d_pct"] = round((cq - _ago_7d["0q"]) / abs(_ago_7d["0q"]) * 100, 1) if _ago_7d["0q"] != 0 else 0.0
	if cq and isinstance(_ago_30d, dict) and _ago_30d.get("0q"):
		compressed["revision_30d_pct"] = round((cq - _ago_30d["0q"]) / abs(_ago_30d["0q"]) * 100, 1) if _ago_30d["0q"] != 0 else 0.0
	if cq and isinstance(_ago_90d, dict) and _ago_90d.get("0q"):
		compressed["revision_90d_pct"] = round((cq - _ago_90d["0q"]) / abs(_ago_90d["0q"]) * 100, 1) if _ago_90d["0q"] != 0 else 0.0

	growth = as_column_mapping(full_result.get("growth_estimates", {}))
	stock_trend = growth.get("stockTrend", {}) if isinstance(growth, dict) else {}
	if isinstance(stock_trend, dict):
		if stock_trend.get("0y") is not None:
			compressed["stock_growth_0y"] = round(stock_trend["0y"] * 100, 1)
		if stock_trend.get("+1y") is not None:
			compressed["stock_growth_1y"] = round(stock_trend["+1y"] * 100, 1)

	compressed["thresholds"] = f"[M] {REVISION_SIGNIFICANCE_LOCKED_PCT:g}%+ revision in 30d is significant context"
	full_result["compressed"] = compressed

	_emit_result(
		full_result,
		"[M] Revisions matter because a genuine surprise can lift institutional earnings models and sustain accumulation; direction and the 30-day change are evidence, not a standalone buy gate.",
	)


# ===========================================================================
# Valuation  (folded in from the former forward_pe module)
#
# Forward P/E and the growth the price is discounting — an EXPECTATIONS
# barometer, NOT a valuation gate. Ch.4: P/E is "overused and misunderstood";
# the biggest winners routinely traded at 30-40x+ BEFORE their largest advance,
# so rejecting a leader for a rich multiple is the canonical way to miss it.
# The deleted PEG cheap/fair/expensive bands were a GARP lens this method
# rejects. What survives is the only part that is actionable here: what the
# market has ALREADY priced in. High embedded growth = little room to surprise
# and a low bar to disappoint; forward multiples that CONTRACT across years
# (fwd_2y < fwd_1y) mean earnings are outrunning price — growing into the multiple.
# ===========================================================================


def _compute_valuation(symbol):
	"""Forward P/E + embedded-growth expectation barometer. No buy/avoid bands."""
	ticker = yf.Ticker(symbol)

	current_price = None
	try:
		current_price = ticker.info.get("currentPrice")
	except Exception:
		pass
	if current_price is None:
		try:
			current_price = ticker.fast_info.last_price
		except Exception:
			pass
	if current_price is None:
		error_json(f"Cannot retrieve current price for {symbol}")

	# Forward EPS estimates (0y = this fiscal year, +1y = next).
	forward_1y_eps = None
	forward_2y_eps = None
	try:
		est = ticker.get_earnings_estimate()
		if est is not None and not est.empty and "avg" in est.columns:
			if "0y" in est.index and est.loc["0y", "avg"] == est.loc["0y", "avg"]:
				forward_1y_eps = float(est.loc["0y", "avg"])
			if "+1y" in est.index and est.loc["+1y", "avg"] == est.loc["+1y", "avg"]:
				forward_2y_eps = float(est.loc["+1y", "avg"])
			if forward_1y_eps is None and forward_2y_eps is not None:
				forward_1y_eps, forward_2y_eps = forward_2y_eps, None
	except Exception:
		pass

	forward_pe_1y = round(current_price / forward_1y_eps, 1) if forward_1y_eps and forward_1y_eps > 0 else None
	forward_pe_2y = round(current_price / forward_2y_eps, 1) if forward_2y_eps and forward_2y_eps > 0 else None
	pe_contracting = (
		forward_pe_1y is not None and forward_pe_2y is not None and forward_pe_2y < forward_pe_1y
	) if (forward_pe_1y is not None and forward_pe_2y is not None) else None

	# Revenue growth (next year preferred, else current).
	revenue_growth = None
	try:
		rev = ticker.get_revenue_estimate()
		if rev is not None and not rev.empty and "growth" in rev.columns:
			for key in ("+1y", "0y"):
				if key in rev.index and rev.loc[key, "growth"] == rev.loc[key, "growth"]:
					revenue_growth = round(float(rev.loc[key, "growth"]) * 100, 1)
					break
	except Exception:
		pass

	# Expected EPS growth rate (for the raw PEG scalar).
	eps_growth_rate = None
	try:
		ge = ticker.get_growth_estimates()
		if ge is not None and not ge.empty and "stockTrend" in ge.columns and "0y" in ge.index:
			val = ge.loc["0y", "stockTrend"]
			if val == val:
				eps_growth_rate = round(float(val) * 100, 1)
	except Exception:
		pass

	peg_ratio = None
	if forward_pe_1y and eps_growth_rate and eps_growth_rate > 0:
		peg_ratio = round(forward_pe_1y / eps_growth_rate, 2)

	gross_margin_pct = None
	try:
		gm = ticker.info.get("grossMargins")
		if gm is not None:
			gross_margin_pct = round(gm * 100, 2)
	except Exception:
		pass

	result = {
		"symbol": symbol.upper(),
		"current_price": round(current_price, 2),
		"forward_pe_1y": forward_pe_1y,
		"forward_pe_2y": forward_pe_2y,
		"forward_pe_contracting": pe_contracting,
		"peg_ratio": peg_ratio,
		"peg_ratio_unit": "forward P/E / expected EPS growth % — years-of-growth priced in, NOT a cheap/expensive verdict",
		"eps_growth_rate_used_pct": eps_growth_rate,
		"revenue_growth_yoy_pct": revenue_growth,
		"gross_margin_pct": gross_margin_pct,
		"interpretation": {
			"pe_is_not_a_gate": "High P/E never disqualifies — momentum leaders trade at premiums (Ch.4). Use this for context, not rejection.",
			"expectation_barometer": "Forward P/E and PEG gauge embedded expectations. High demands durable growth; low signals low expectations and often a problem, never an automatic opportunity.",
			"pe_contraction": "fwd_2y < fwd_1y means earnings are outpacing price — the stock is growing into its multiple (constructive).",
		},
		"thresholds": {
			"gate": "[M] none; P/E and PEG never qualify or disqualify a ticker",
		},
		"doctrine": (
			"[M] P/E is an expectation barometer, not a cheap/expensive verdict — it measures "
			"the LEVEL of embedded expectation, so the real question is whether the company "
			"can EXCEED it and whether that expectation is still rising. A high multiple is "
			"dangerous only if growth can't sustain it; a low one is never a buy reason and "
			"often flags a problem. (For commodity-cyclicals this cycle "
			"inverts — a high P/E marks the buy zone — so identify the business type before "
			"reading the multiple.)"
		),
	}
	result["compressed"] = {
		k: result[k] for k in (
			"forward_pe_1y", "forward_pe_2y", "forward_pe_contracting",
			"peg_ratio", "peg_ratio_unit", "eps_growth_rate_used_pct",
			"revenue_growth_yoy_pct", "gross_margin_pct",
		)
	}
	return result


@safe_run
def cmd_valuation(args):
	"""Forward P/E + embedded-growth expectation barometer (not a gate)."""
	configure_cache(args.no_cache or cache_disabled())
	_emit_result(_compute_valuation(args.symbol))


# ===========================================================================
# Margin trajectory  (folded in from the former margin_tracker module)
#
# Quarterly gross/operating/NET margins over time, with NET as the headline and
# NO classification badge. The deleted "EXPANDING/COMPRESSION" flag picked the
# BEST of gross-or-operating via max() — which exactly inverts Code-33's logic:
# Code 33 demands all legs improve TOGETHER, while max() lets a single improving
# lever paint "EXPANDING" over deterioration elsewhere. Net is the headline for
# the same reason Code-33's margin leg is net: a filter on the bottom line
# catches the opex/SG&A leverage gross margin is blind to. Gross and operating
# stay in the trajectory as diagnosis, not verdict — gross-flat + net-rising is
# SG&A leverage; gross-rising + net-flat is opex bloat. The analyst reads it.
# ===========================================================================


def _calc_margin(numerator, denominator):
	"""Margin as a percentage, or None when a value is missing/zero-denominator."""
	if numerator is None or denominator is None or denominator == 0:
		return None
	return round(float(numerator) / float(denominator) * 100, 2)


def _get_income_field(df, col, names):
	"""First non-NaN value among candidate row names in an income-statement column."""
	for name in names:
		if name in df.index:
			val = df.loc[name, col]
			if val is not None and val == val:  # not NaN
				return val
	return None


def _format_quarter(ts):
	"""Format a Timestamp into a 'YYYY-QN' quarter label."""
	month = getattr(ts, "month", None)
	year = getattr(ts, "year", None)
	if month is None or year is None:
		return str(ts)
	q = (month - 1) // 3 + 1
	return f"{year}-Q{q}"


def _build_margin_trajectory(income, quarters):
	"""Gross/operating/net margin per quarter, most-recent-first."""
	cols = sorted(list(income.columns), reverse=True)[:quarters]
	trajectory = []
	for col in cols:
		revenue = _get_income_field(income, col, ["TotalRevenue", "Total Revenue", "Revenue"])
		gross = _get_income_field(income, col, ["GrossProfit", "Gross Profit"])
		operating = _get_income_field(income, col, ["OperatingIncome", "Operating Income", "EBIT"])
		net = _get_income_field(
			income, col,
			["NetIncome", "Net Income", "NetIncomeCommonStockholders", "Net Income Common Stockholders"],
		)
		trajectory.append({
			"period": _format_quarter(col),
			"gross": _calc_margin(gross, revenue),
			"operating": _calc_margin(operating, revenue),
			"net": _calc_margin(net, revenue),
		})
	return trajectory


def _ppt_delta(a, b):
	"""Percentage-point change a - b, or None if either is missing."""
	if a is None or b is None:
		return None
	return round(a - b, 2)


@safe_run
def cmd_margin(args):
	"""Net-headline margin trajectory (gross/op/net), no classification band."""
	configure_cache(args.no_cache or cache_disabled())
	if args.quarters < 1:
		raise ValueError("--quarters must be at least 1")
	symbol = args.symbol.upper()
	ticker, income = _get_quarterly_financials(symbol)
	if income is None or income.empty:
		error_json(f"No quarterly financial data available for {symbol}")

	trajectory = _build_margin_trajectory(income, args.quarters)
	if not trajectory:
		error_json(f"No quarterly margin data available for {symbol}")

	latest = trajectory[0]
	prev = trajectory[1] if len(trajectory) >= 2 else None
	yoy = trajectory[4] if len(trajectory) >= 5 else None

	# Per-entry net QoQ delta, so the trajectory itself shows the bottom-line slope.
	for i, entry in enumerate(trajectory):
		nxt = trajectory[i + 1] if i + 1 < len(trajectory) else None
		entry["net_qoq"] = _ppt_delta(entry["net"], nxt["net"]) if nxt else None

	full_result = {
		"symbol": symbol,
		"quarters_analyzed": len(trajectory),
		"latest_quarter": {
			"period": latest["period"],
			"gross_margin": latest["gross"],
			"operating_margin": latest["operating"],
			"net_margin": latest["net"],
		},
		"net_margin_qoq_change": _ppt_delta(latest["net"], prev["net"]) if prev else None,
		"net_margin_yoy_change": _ppt_delta(latest["net"], yoy["net"]) if yoy else None,
		"operating_margin_qoq_change": _ppt_delta(latest["operating"], prev["operating"]) if prev else None,
		"operating_margin_yoy_change": _ppt_delta(latest["operating"], yoy["operating"]) if yoy else None,
		"trajectory": trajectory,
		"change_unit": "percentage points (pp)",
		"interpretation": {
			"why_net": "Net is the headline — a filter on the bottom line catches opex/SG&A leverage that gross margin is blind to (the same reason Code-33's margin leg uses net).",
			"no_grade": "No EXPANDING/COMPRESSION badge: a max()-best-of-gross-or-operating flag inverts Code-33's all-legs-together logic. Read the trajectory — gross-flat + net-rising = SG&A leverage; gross-rising + net-flat = opex bloat.",
		},
		"thresholds": {
			"gate": "[M] none; read the trajectory with EPS and sales rather than assigning a standalone grade",
			"lookback_quarters": f"implementation window: {args.quarters}",
		},
	}
	full_result["compressed"] = {
		"quarters_analyzed": len(trajectory),
		"latest_quarter": full_result["latest_quarter"],
		"net_margin_qoq_change": full_result["net_margin_qoq_change"],
		"net_margin_yoy_change": full_result["net_margin_yoy_change"],
		"trajectory": trajectory[:4],
	}
	_emit_result(
		full_result,
		"[M] Margin quality is read with sales and EPS: net margin is the headline check on whether growth survives the full cost structure, while gross and operating margins diagnose where leverage or deterioration originates.",
	)


def main():
	parser = _JsonArgumentParser(description="Earnings Acceleration Analysis")
	sub = parser.add_subparsers(dest="command", required=True, parser_class=_JsonArgumentParser)

	def add_no_cache_arg(command_parser):
		command_parser.add_argument(
			"--no-cache",
			action="store_true",
			help="Bypass the transparent same-session market-data cache for this command.",
		)

	# code33
	sp = sub.add_parser("code33", help="[M] Check canonical Code 33 triple acceleration")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument(
		"--eps-min-pct", type=float, default=_EPS_MIN_PCT,
		help="[M] Most-recent-quarter YoY EPS growth floor for 'sufficient' (%%). "
			 "The 20%% lower bound is locked; this flex flag may only raise it "
			 "when the regime offers stronger growth (40-100%% in a bull market).",
	)
	sp.add_argument(
		"--margin-min-ppt", type=float, default=_MARGIN_MIN_CHANGE_PPT,
		help="[M directional definition; implementation heuristic magnitude] Per-quarter NET-margin improvement (ppt). "
			 "INVENTED magnitude floor — spec requires only DIRECTIONAL "
			 "acceleration, so the 0 default is the source-backed directional test; "
			 "raise it only as an explicitly chosen implementation filter.",
	)
	sp.add_argument(
		"--sales-min-pct", type=float, default=_SALES_STRENGTH_MIN_PCT,
		help="[M sales-confirmation principle; implementation proxy] Sales-STRENGTH floor (%%) used only when revenue history is too "
			 "shallow (<4 YoY rates, the yfinance norm) to test 3 transitions of "
			 "acceleration. This contextual proxy can never produce Code 33 PASS.",
	)
	add_no_cache_arg(sp)
	sp.set_defaults(func=cmd_code33)

	# acceleration
	sp = sub.add_parser("acceleration", help="[M] Analyze earnings acceleration trends")
	sp.add_argument("symbol", help="Ticker symbol")
	add_no_cache_arg(sp)
	sp.set_defaults(func=cmd_acceleration)

	# surprise
	sp = sub.add_parser("surprise", help="[M] Get earnings surprise and drift history")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument(
		"--quarters", type=int, default=_SURPRISE_QUARTERS,
		help="Implementation lookback window, in quarters, for [M] surprise/beat history. "
			 "Use a shorter 4/6 window to weight the current regime, longer to "
			 "establish a base-rate.",
	)
	sp.add_argument(
		"--drift-days", default=_DRIFT_DAYS,
		help="Implementation horizons for the [M] post-earnings-drift lens, in trading days "
			 "(default '1,5'). Drift is a multi-MONTH phenomenon — bigger "
			 "surprises drift longer; 1/5d only catch the immediate gap. "
			 "Widen (e.g. '1,5,20,60') for the fuller effect.",
	)
	sp.add_argument(
		"--cockroach-strong", type=int, default=_COCKROACH_STRONG,
		help="Implementation heuristic (not doctrine): consecutive beats for a 'strong' cockroach signal. "
			 "depends on the cohort's beat base-rate; raise where beating is "
			 "near-universal.",
	)
	sp.add_argument(
		"--cockroach-moderate", type=int, default=_COCKROACH_MODERATE,
		help="Implementation heuristic (not doctrine): consecutive beats for a 'moderate' cockroach signal (see "
			 "--cockroach-strong).",
	)
	add_no_cache_arg(sp)
	sp.set_defaults(func=cmd_surprise)

	# revisions
	sp = sub.add_parser("revisions", help="[M] Track analyst estimate revisions (5%% reference)")
	sp.add_argument("symbol", help="Ticker symbol")
	add_no_cache_arg(sp)
	sp.set_defaults(func=cmd_revisions)

	# valuation (absorbed from forward_pe)
	sp = sub.add_parser("valuation", help="[M] Forward P/E expectation barometer (never a gate)")
	sp.add_argument("symbol", help="Ticker symbol")
	add_no_cache_arg(sp)
	sp.set_defaults(func=cmd_valuation)

	# margin (absorbed from margin_tracker)
	sp = sub.add_parser("margin", help="[M] Net-headline margin trajectory (gross/op/net), no grade")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--quarters", type=int, default=8, help="Implementation lookback: quarters of trajectory")
	add_no_cache_arg(sp)
	sp.set_defaults(func=cmd_margin)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
