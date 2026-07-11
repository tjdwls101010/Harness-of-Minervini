#!/usr/bin/env python3
"""Base Counting: track base number within a Stage 2 advance.

Identifies and counts price bases (consolidation patterns) that form during
a stock's Stage 2 uptrend. Each base represents a distinct "step" in the
advance: the stock must make a new high above the prior breakout before a new pullback counts as a separate base. An optional non-canonical flex flag can demand a larger step.

Grounded in the M-map's Stage-2 maturity rules (cluster C) and its separate VCP/base-structure rules (cluster D). The detector does not establish the eight-part Trend Template prerequisite.

Commands:
	count: Count bases and assess current base stage for a ticker

Args:
	symbol (str): Ticker symbol (e.g., "AAPL", "NVDA", "META")
	--period (str): Historical data period (default: "2y")
	--min-base-weeks (int): Minimum weeks for a formation to count as base (default: 3)
	--no-cache: Bypass the shared read-through cache for this invocation

Returns:
	dict: {
		"current_base_number": int,
		"forming_base": dict|null,
		"base_history": [...],
		"cross_base_analysis": {"correction_trend": str, "depths": [float]},
		"risk_level": str,
		"base_count_reset_detected": bool,
		"thresholds": {...}
	}

Use Cases:
	- Determine if a stock is in early (base 1-2) or late (base 4+) stage
	- Add maturity context to an independently qualified Stage-2 candidate
	- Detect deepening corrections across bases (exhaustion signal)
	- Identify reset events that restart the base count

Notes:
	- [M] Bases 1-2 are prime, base 3 remains tradeable, and bases 4-5 are late-stage with abrupt failures more common
	- [heuristic] A higher step separates detected bases; the maps provide no fixed percentage advance and this discretization is not doctrine
	- [M] Constructive VCP/base depth is 10-35%; roughly 50% is admissible only in a severe bear market, and 60% or deeper is rejected
	- [heuristic] The 30-of-40-day reset proxy and 3-point cross-base trend band are implementation discretizations, not Minervini doctrine

See Also:
	- vcp.py: VCP detection within individual bases
	- stage_analysis.py: Stage classification for context
	- volume_analysis.py: Volume patterns during base formation
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import yfinance as yf
from utils import cache_disabled, calculate_sma, configure_cache, error_json, output_json, safe_run

# ── Constants ──────────────────────────────────────────────────────────
# [M] Locked broad VCP-envelope boundaries. Ordinary counted Stage-2 bases are usually 5-26 weeks, while the broader VCP/cheat envelope spans 3-65 weeks; 10-35% is constructive and 60% or deeper is rejected because overhead supply overwhelms the setup.
MIN_BASE_WEEKS = 3
MIN_CORRECTION_PCT = 10.0
REDLINE_DEPTH_PCT = 60.0
MAX_BASE_WEEKS = 65

# [M] A stock correcting more than roughly two-to-three times its market is progressively suspect; above three times is the deterministic excessive band used here.
REL_CORRECTION_NORMAL_RATIO = 2.0
REL_CORRECTION_ELEVATED_RATIO = 3.0

# Flex-tier detector defaults. These discretize structure for a scanner and are not canonical Minervini thresholds.
MIN_ADVANCE_PCT = 0.0
SWING_HIGH_WINDOW = 20
FORMING_RECENCY_DAYS = 60
RESET_WINDOW = 40
RESET_THRESHOLD = 30
CROSS_BASE_TREND_BAND_PPT = 3.0


def _is_swing_high(highs_arr, idx, window=SWING_HIGH_WINDOW):
	"""Check if idx is a swing high within a symmetric window.

	A swing high is the highest point in a window of 2*window days
	centered on idx. This filters out minor peaks.
	"""
	start = max(0, idx - window)
	end = min(len(highs_arr), idx + window + 1)

	if end - start < window:  # Not enough data
		return False

	return highs_arr[idx] == np.max(highs_arr[start:end])


def _find_bases(closes, highs, lows, sma200, min_base_weeks=3,
				swing_window=SWING_HIGH_WINDOW, max_base_days=MAX_BASE_WEEKS * 5,
				forming_recency_days=FORMING_RECENCY_DAYS, min_advance_pct=MIN_ADVANCE_PCT):
	"""Identify bases within a Stage 2 advance.

	A base is a distinct step in the stock's advance:
	1. Price above the 200SMA is used only as a partial candidate filter; confirmed Stage 2 still requires the external Trend Template 8/8 gate
	2. A significant swing high forms (swing_window-day window)
	3. [heuristic] For base 2+, a higher step above the prior breakout separates detector candidates
	4. [M] Price corrects at least 10% and remains below the locked 60% redline; 10-35% is constructive, while deeper candidates require explicit context
	5. Price breaks out above the high (base complete)

	Returns:
		(list of completed bases, forming_base or None)
	"""
	closes_arr = closes.values.astype(float)
	highs_arr = highs.values.astype(float)
	lows_arr = lows.values.astype(float)
	sma200_arr = sma200.values.astype(float)
	dates = closes.index
	n = len(closes_arr)

	min_base_days = min_base_weeks * 5
	completed_bases = []
	forming_base = None
	last_breakout_price = 0.0

	i = 0
	while i < n - min_base_days:
		# [M] Partial structural screen only. This is not a declaration of confirmed Stage 2.
		if np.isnan(sma200_arr[i]) or closes_arr[i] < sma200_arr[i]:
			i += 1
			continue

		# Check for swing high
		if not _is_swing_high(highs_arr, i, swing_window):
			i += 1
			continue

		base_high = highs_arr[i]
		base_start_idx = i

		# For base 2+: require minimum advance from prior breakout
		if last_breakout_price > 0:
			advance_pct = (base_high - last_breakout_price) / last_breakout_price * 100
			if advance_pct < min_advance_pct:
				i += 1
				continue

		# Find pullback low after the swing high
		search_end = min(i + max_base_days, n)
		if search_end <= i + min_base_days:
			i += 1
			continue

		# Find the lowest low in the base period
		segment_lows = lows_arr[i:search_end]
		low_offset = np.argmin(segment_lows)
		base_low_idx = i + low_offset
		base_low = lows_arr[base_low_idx]

		# Check correction depth
		correction_depth = (base_high - base_low) / base_high * 100

		if correction_depth < MIN_CORRECTION_PCT:
			# Too shallow — not a real base, skip past this high
			i += swing_window
			continue

		if correction_depth >= REDLINE_DEPTH_PCT:
			# [M] At the 60% rejection line, overhead supply makes the base non-constructive regardless of duration.
			i += swing_window
			continue

		# Find breakout: close above base_high after the low
		breakout_idx = None
		for k in range(base_low_idx + 1, min(base_low_idx + max_base_days, n)):
			if closes_arr[k] > base_high:
				breakout_idx = k
				break

		if breakout_idx is None:
			# No breakout found — check if base is still forming
			duration_days = n - 1 - base_start_idx
			duration_weeks = max(1, duration_days // 5)
			if min_base_weeks <= duration_weeks <= max_base_days // 5 and base_low_idx > n - forming_recency_days:
				# Recent base, still forming
				forming_base = {
					"start_idx": base_start_idx,
					"start_date": str(dates[base_start_idx].date()),
					"duration_weeks": duration_weeks,
					"correction_depth_pct": round(correction_depth, 1),
					"high_price": round(float(base_high), 2),
					"low_price": round(float(base_low), 2),
					"status": "forming",
				}
			# Move past the low and continue searching
			i = base_low_idx + swing_window
			continue

		# Base completed — validate duration
		duration_days = breakout_idx - base_start_idx
		duration_weeks = max(1, duration_days // 5)

		if duration_weeks < min_base_weeks or duration_days > max_base_days:
			# Too short to be a real base
			i = breakout_idx + 1
			continue

		# Record completed base
		completed_bases.append({
			"start_idx": base_start_idx,
			"end_idx": breakout_idx,
			"start_date": str(dates[base_start_idx].date()),
			"end_date": str(dates[breakout_idx].date()),
			"duration_weeks": duration_weeks,
			"correction_depth_pct": round(correction_depth, 1),
			"high_price": round(float(base_high), 2),
			"low_price": round(float(base_low), 2),
			"status": "completed",
		})

		# Update tracking — advance past breakout
		last_breakout_price = float(base_high)
		i = breakout_idx + 1

	return completed_bases, forming_base


def _classify_base_pattern(depth, duration_weeks):
	"""Classify only what duration and depth can establish honestly."""
	if 4 <= duration_weeks <= 7 and 10 <= depth <= 15:
		return "flat_base_candidate_[M]"
	return "base_candidate"


def _check_base_reset(closes, sma200, reset_window=RESET_WINDOW, reset_threshold=RESET_THRESHOLD):
	"""Apply the non-canonical below-200SMA reset proxy; this does not classify Stage 4."""
	closes_arr = closes.values.astype(float)
	sma200_arr = sma200.values.astype(float)

	# Build boolean array: 1 if below 200MA, 0 otherwise
	valid_mask = ~np.isnan(sma200_arr)
	below = np.zeros(len(closes_arr), dtype=int)
	below[valid_mask] = (closes_arr[valid_mask] < sma200_arr[valid_mask]).astype(int)

	if len(below) < reset_window:
		return []

	# Rolling sum of days below 200MA
	kernel = np.ones(reset_window, dtype=int)
	rolling_sum = np.convolve(below, kernel, mode="valid")

	# Find points where rolling sum exceeds threshold
	reset_indices = np.where(rolling_sum >= reset_threshold)[0]
	if len(reset_indices) == 0:
		return []

	# Convert to original index space and deduplicate (keep first of each cluster)
	reset_points = []
	last_reset = -reset_window
	for idx in reset_indices:
		original_idx = idx + reset_window - 1
		if original_idx - last_reset >= reset_window:
			reset_points.append(original_idx)
			last_reset = original_idx

	return reset_points


def _compute_relative_correction(dates, start_idx, end_idx, stock_correction_pct):
	"""Compute stock correction depth relative to SPY during the same period."""
	start_date = str(dates[start_idx].date())
	end_date = str(dates[end_idx].date())

	try:
		spy = yf.Ticker("SPY")
		spy_data = spy.history(start=start_date, end=end_date, interval="1d")
		if spy_data.empty or len(spy_data) < 5:
			return None, "unknown"

		spy_high = float(spy_data["High"].max())
		spy_low = float(spy_data["Low"].min())
		if spy_high <= 0:
			return None, "unknown"

		spy_correction = (spy_high - spy_low) / spy_high * 100
		if spy_correction < 0.5:
			return None, "unknown"

		ratio = round(stock_correction_pct / spy_correction, 2)

		if ratio <= REL_CORRECTION_NORMAL_RATIO:
			severity = "normal"
		elif ratio <= REL_CORRECTION_ELEVATED_RATIO:
			severity = "elevated"
		else:
			severity = "excessive"

		return ratio, severity
	except Exception:
		return None, "unknown"


def _compute_cross_base_analysis(bases):
	"""Summarize cross-base depth changes with an explicit implementation band."""
	if len(bases) < 2:
		return None

	depths = [b["correction_depth_pct"] for b in bases]

	# Compare successive depths
	changes = [depths[i + 1] - depths[i] for i in range(len(depths) - 1)]
	avg_change = sum(changes) / len(changes)

	if avg_change > CROSS_BASE_TREND_BAND_PPT:
		trend = "deepening"
	elif avg_change < -CROSS_BASE_TREND_BAND_PPT:
		trend = "shallowing"
	else:
		trend = "stable"

	return {
		"correction_trend": trend,
		"depths": depths,
	}


@safe_run
def cmd_count(args):
	"""Count bases and assess current base stage."""
	configure_cache(args.no_cache or cache_disabled())
	if args.min_base_weeks < MIN_BASE_WEEKS:
		error_json(f"--min-base-weeks must be at least {MIN_BASE_WEEKS} [M].")
	if args.max_base_weeks > MAX_BASE_WEEKS:
		error_json(f"--max-base-weeks cannot exceed {MAX_BASE_WEEKS} [M].")
	if args.max_base_weeks < args.min_base_weeks:
		error_json("--max-base-weeks must be greater than or equal to --min-base-weeks.")
	if args.swing_window < 1 or args.forming_recency_days < 1:
		error_json("--swing-window and --forming-recency-days must be positive integers.")
	if args.reset_window < 1 or not 1 <= args.reset_days <= args.reset_window:
		error_json("--reset-days must be between 1 and --reset-window.")
	if args.min_advance_pct < 0:
		error_json("--min-advance-pct cannot be negative.")

	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1d")
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 200:
		error_json(f"Insufficient data for {symbol}. Need at least 200 trading days; received {len(data)}.")

	closes = data["Close"]
	highs = data["High"]
	lows = data["Low"]
	sma200 = calculate_sma(closes, 200)

	# Check for base count resets
	reset_points = _check_base_reset(closes, sma200, args.reset_window, args.reset_days)

	# Find bases
	all_bases, forming_base = _find_bases(
		closes, highs, lows, sma200, args.min_base_weeks,
		swing_window=args.swing_window,
		max_base_days=args.max_base_weeks * 5,
		forming_recency_days=args.forming_recency_days,
		min_advance_pct=args.min_advance_pct,
	)

	# Apply the heuristic reset consistently to completed and forming candidates.
	last_reset = reset_points[-1] if reset_points else None
	if last_reset is not None:
		all_bases = [b for b in all_bases if b["start_idx"] > last_reset]
		if forming_base and forming_base["start_idx"] <= last_reset:
			forming_base = None
	if forming_base:
		forming_base["pattern_type"] = _classify_base_pattern(forming_base["correction_depth_pct"], forming_base["duration_weeks"])
		forming_base.pop("start_idx", None)

	# Number bases, classify, compute relative correction
	dates = closes.index
	for i, base in enumerate(all_bases):
		base["base_number"] = i + 1
		depth = base["correction_depth_pct"]
		if depth <= 35:
			base["depth_context"] = "[M] constructive_10_35pct"
		elif depth <= 50:
			base["depth_context"] = "[M] deep_requires_severe_bear_context"
		else:
			base["depth_context"] = "[M] excessive_below_locked_60pct_redline"
		base["pattern_type"] = _classify_base_pattern(
			depth,
			base["duration_weeks"],
		)
		if base["correction_depth_pct"] <= 35:
			base["depth_assessment"] = "constructive_[M]"
		elif base["correction_depth_pct"] <= 50:
			base["depth_assessment"] = "severe_bear_context_required_[M]"
		else:
			base["depth_assessment"] = "generally_excessive_[M]"
		ratio, severity = _compute_relative_correction(
			dates, base["start_idx"], base["end_idx"], base["correction_depth_pct"]
		)
		base["relative_correction_ratio"] = ratio
		base["correction_severity"] = severity
		# Remove internal index fields
		base.pop("start_idx", None)
		base.pop("end_idx", None)

	current_base_number = len(all_bases)

	# [M] Maturity labels are contextual, not a standalone low/high risk score.
	if current_base_number == 0:
		assessment = "No bases detected"
		maturity = "unknown"
	elif current_base_number <= 2:
		assessment = "[M] Prime maturity band; still requires every independent entry gate"
		maturity = "prime"
	elif current_base_number == 3:
		assessment = "[M] Third base remains tradeable; maturity is advancing"
		maturity = "tradeable"
	elif current_base_number <= 5:
		assessment = "[M] Late-stage band; abrupt base failures become more frequent"
		maturity = "late"
	else:
		assessment = "Outside the corpus's stated 3-5-base topping sequence; no canonical risk category"
		maturity = "outside_canonical_band"

	# Cross-base analysis
	cross_base = _compute_cross_base_analysis(all_bases)

	output_json({
		"symbol": symbol,
		"date": str(data.index[-1].date()),
		"current_price": round(float(closes.iloc[-1]), 2),
		"current_base_number": current_base_number,
		"forming_base": forming_base,
		"base_history": all_bases,
		"cross_base_analysis": cross_base,
		"base_stage_assessment": assessment,
		"maturity": maturity,
		"risk_level": "not_scored",
		"risk_level_note": "[M] Base count is a maturity lens, not a standalone risk score or sizing instruction.",
		"base_count_reset_detected": len(reset_points) > 0,
		"thresholds": {
			"base_duration": f"[M] {args.min_base_weeks}-{args.max_base_weeks} weeks effective within the broad 3-65-week VCP envelope; ordinary counted Stage-2 bases are usually 5-26 weeks",
			"min_advance_between_bases": f"[heuristic] new high must exceed prior breakout plus {args.min_advance_pct:.1f}% (0 = off); Minervini specifies structure, not a fixed percentage",
			"correction_range": f"[M] {MIN_CORRECTION_PCT:.0f}-35% constructive; roughly 50% only in a severe bear market; reject at >={REDLINE_DEPTH_PCT:.0f}%",
			"relative_correction": f"[M] avoid a correction beyond roughly {REL_CORRECTION_NORMAL_RATIO:.0f}-{REL_CORRECTION_ELEVATED_RATIO:.0f}x the market; normal/elevated/excessive labels are implementation discretizations",
			"maturity": "[M] base 1-2 prime | base 3 tradeable | base 4-5 late-stage; base 6+ is outside the stated canonical sequence",
			"reset_trigger": f"[heuristic] {args.reset_days}+ of {args.reset_window} trading days below 200SMA; proxy only, confirm the full Stage-4 structure in stage_analysis",
			"cross_base_warning": f"[heuristic] average depth change beyond +/-{CROSS_BASE_TREND_BAND_PPT:.1f} percentage points labels deepening/shallowing",
		},
		"doctrine": {
			"base_number": "[M] Base count supplies maturity context only: bases 1-2 are prime, base 3 remains tradeable, and bases 4-5 are late-stage with abrupt failures more frequent. It must be combined with price/volume, fundamentals, and market context because some advances climax without a normal base sequence.",
			"detector_limit": "[M] Base counting is a maturity lens, never a standalone entry signal. This detector uses price above the 200SMA only to find candidates; confirm Stage 2 and the full Trend Template separately before acting.",
		},
	})


def main():
	class JsonArgumentParser(argparse.ArgumentParser):
		def error(self, message):
			error_json(message)

	parser = JsonArgumentParser(description="[M] Base-count maturity lens for externally confirmed Trend Template 8/8 candidates; focused count command only")
	sub = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)

	sp = sub.add_parser("count", help="Count bases and assess base stage")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--period", default="2y", help="[heuristic] Historical scan window (default: %(default)s); a shorter window can undercount an older Stage-2 cycle")
	sp.add_argument("--min-base-weeks", type=int, default=MIN_BASE_WEEKS, help="[M] Broad VCP-envelope floor is %(default)s weeks; ordinary counted Stage-2 bases are usually 5-26 weeks; raise only to tighten")
	sp.add_argument("--swing-window", type=int, default=SWING_HIGH_WINDOW,
		help="[heuristic] Symmetric (+/-) trading-day window for swing-high detection (default: %(default)s; not doctrine).")
	sp.add_argument("--max-base-weeks", type=int, default=MAX_BASE_WEEKS,
		help="[M] Broad VCP-envelope ceiling and breakout-search horizon in weeks (locked maximum: %(default)s); lower only to tighten the scan.")
	sp.add_argument("--forming-recency-days", type=int, default=FORMING_RECENCY_DAYS,
		help="[heuristic] Recency window in trading days for an unbroken base to remain 'forming' (default: %(default)s; not doctrine).")
	sp.add_argument("--reset-days", type=int, default=RESET_THRESHOLD,
		help="[heuristic] Days below 200SMA within --reset-window used as a count-reset proxy (default: %(default)s); it cannot confirm Stage 4.")
	sp.add_argument("--reset-window", type=int, default=RESET_WINDOW,
		help="[heuristic] Rolling trading-day window for the reset proxy (default: %(default)s); confirm Stage 4 separately.")
	sp.add_argument("--min-advance-pct", type=float, default=MIN_ADVANCE_PCT,
		help="Min %% a new base's high must exceed the prior breakout to count as a separate base "
			 "(default: %(default)s = off). HEURISTIC with no canonical value — not a Minervini rule; "
			 "bases are separated by structure, not a magic %%. Raise only to demand bigger steps.")
	sp.add_argument("--no-cache", action="store_true", help="Bypass the shared read-through cache for this invocation")
	sp.set_defaults(func=cmd_count)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
