#!/usr/bin/env python3
"""Entry-pattern candidates for a qualified ticker; never a standalone buy gate.

Scans for currently active entry patterns on individual stocks or batches.
Detects TraderLion opt-in MA pullback, consolidation pivot, and support reclaim
setups after the Minervini eligibility gate. Each pattern includes
trigger price, stop price, and quality grading. Persona-neutral module
reusable by any pipeline.

Commands:
	scan: Scan for currently active entry patterns on a single stock
	screen: Batch scan multiple stocks for entry patterns

Args:
	symbol (str): Ticker symbol (e.g., "AAPL", "NVDA", "META")
	symbols (str): Space-separated ticker symbols for screen command

Returns:
	For scan:
	dict: {
		"symbol": str,
		"active_patterns": [
			{
				"pattern": str,
				"trigger_price": float,
				"stop_price": float,
				"stop_pct": float,
				"quality": str,
				...pattern-specific fields
			}
		],
		"pattern_count": int,
		"setup_readiness": {
			"classification": str,
			"thresholds": {...}
		}
	}

	For screen:
	dict: {
		"results": [
			{
				"symbol": str,
				"pattern_count": int,
				"best_pattern": str,
				"best_quality": str,
				"setup_readiness": str
			}
		],
		"ranked_by": "pattern_count"
	}

Example:
	>>> python entry_patterns.py scan NVDA
	{
		"symbol": "NVDA",
		"active_patterns": [
			{
				"pattern": "MA_PULLBACK",
				"ma_type": "21_EMA",
				"distance_pct": 0.3,
				"pullback_volume_ratio": 0.65,
				"trigger_price": 142.50,
				"stop_price": 138.80,
				"stop_pct": 2.6,
				"quality": "high"
			}
		],
		"pattern_count": 1,
		"setup_readiness": {"classification": "candidate_requires_upstream_qualification", "thresholds": {...}}
	}

Use Cases:
	- Identify low-risk pullback entries into leading stocks
	- Detect consolidation pivot breakout setups
	- Find shakeout recovery (support reclaim) patterns
	- Screen a qualified watchlist for opt-in tactic candidates ranked by count and quality

Notes:
	- [TL opt-in] MA_PULLBACK: a respected MA approached on contracting volume; RS confirmation is required outside this module
	- [TL opt-in] CONSOLIDATION_PIVOT: short internal resistance plus a defined failure level; volume dry-up strengthens the candidate
	- [TL opt-in] SUPPORT_RECLAIM: a recent 50 SMA undercut followed by a reclaim; reclaim volume strengthens the candidate
	- Quality: "high" (strongest conviction), "moderate" (developing)
	- stop_pct = abs(trigger_price - stop_price) / trigger_price * 100
	- All calculations use yfinance daily data with 1-year history
	- Minimum 50 trading days required for meaningful analysis

See Also:
	- vcp.py: [M] canonical VCP and pivot setup geometry
	- stage_analysis.py: stage classification + risk sell-tells (decline-since-S2, climax, character)
	- tight_closes.py: Tight close cluster detection for supply drying up
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import yfinance as yf
from utils import cache_disabled, configure_cache, error_json, output_json, safe_run


# --- Tunable context parameters (CLI-overridable, default to these constants) ---
# Pullback volume window: how many days define "the pullback" (np.mean(vol_arr[-N:])).
PULLBACK_VOL_DAYS = 3
# Pivot-detection window range: a valid base/pivot length scales with the base's timeframe.
PIVOT_MIN_DAYS = 10
PIVOT_MAX_DAYS = 25
# Support-reclaim undercut lookback: how far back to scan for the undercut-and-reclaim.
UNDERCUT_LOOKBACK_DAYS = 5
# Legacy short-consolidation range ceiling. This detector is [TL] opt-in; it is
# not the [M] 4-7 week flat-base definition and the value is a flex heuristic.
PIVOT_RANGE_MAX = 15.0

# --- Legacy detector heuristics (not canonical doctrine) -------------------
DEFAULT_PULLBACK_VOL_RATIO = 0.8
DEFAULT_MA_PROXIMITY_PCT = 1.0
DEFAULT_PIVOT_HIGH_RANGE_PCT = 7.0
DEFAULT_PIVOT_HIGH_MIN_DAYS = 15
DEFAULT_UNDERCUT_DEPTH_PCT = 1.0
DEFAULT_RECLAIM_VOL_RATIO = 1.5
DEFAULT_MA_TRIGGER_BUFFER_PCT = 0.5
DEFAULT_MA_STOP_BUFFER_PCT = 1.5
DEFAULT_PIVOT_TRIGGER_BUFFER_PCT = 0.3
# [TL] The harness adopts the map's conservative chase default as a flex cap.
DEFAULT_CHASE_MAX_PCT = 1.5
# [TL] Above/below-average volume uses average +/-25%; callers may tune the band.
DEFAULT_VOLUME_BAND_PCT = 25.0

# [M] The risk plan may never exceed the method's absolute 10% stop cap. This
# does not invent a closer stop; detections above it are flagged unusable.
LOCKED_MAX_STOP_PCT = 10.0
# Fifty observations are mathematically required for this module's 50 SMA and
# 50-day volume baseline; this data-sufficiency floor is not trading doctrine.
LOCKED_MIN_HISTORY_DAYS = 50

_ENTRY_DOCTRINE = (
	"[M] A completed VCP pivot (or VCP-anchored cheat) after Stage-2 and Trend "
	"Template qualification remains the default entry. [TL] MA_PULLBACK, "
	"CONSOLIDATION_PIVOT, and SUPPORT_RECLAIM are opt-in practice-layer tactics; "
	"a pattern match never waives the upstream technical gate, and an MA pullback "
	"also requires relative-strength evidence that this module does not evaluate."
)


def _emit_result(result):
	"""Emit JSON with the module's provenance-tagged doctrine."""
	result.setdefault("doctrine", _ENTRY_DOCTRINE)
	output_json(result)


class _JsonArgumentParser(argparse.ArgumentParser):
	"""Route CLI usage errors through the module's JSON/exit-1 contract."""

	def __init__(self, *args, **kwargs):
		kwargs.setdefault("formatter_class", argparse.ArgumentDefaultsHelpFormatter)
		super().__init__(*args, **kwargs)

	def error(self, message):
		error_json(message)


def _stop_pct(entry_price, stop_price):
	"""Calculate stop percentage: abs(entry - stop) / entry * 100."""
	if entry_price <= 0:
		return 0.0
	return round(abs(entry_price - stop_price) / entry_price * 100, 2)


def _detect_ma_pullback(
	close_arr,
	vol_arr,
	pullback_vol_days=PULLBACK_VOL_DAYS,
	pullback_vol_ratio_max=DEFAULT_PULLBACK_VOL_RATIO,
	ma_proximity_pct=DEFAULT_MA_PROXIMITY_PCT,
	ma_trigger_buffer_pct=DEFAULT_MA_TRIGGER_BUFFER_PCT,
	ma_stop_buffer_pct=DEFAULT_MA_STOP_BUFFER_PCT,
):
	"""Detect MA_PULLBACK pattern.

	[TL opt-in] Checks a 10 SMA, 21 EMA, or 50 SMA approach on contracting
	volume. The numeric proximity, volume, trigger, and stop tolerances are
	flexible implementation heuristics; [TL] also requires RS evidence outside
	this price-only module.
	"""
	n = len(close_arr)
	if n < LOCKED_MIN_HISTORY_DAYS:
		return []

	current_price = float(close_arr[-1])

	# Calculate MAs
	sma10 = np.mean(close_arr[-10:])
	sma50 = np.mean(close_arr[-50:])
	# EMA 21
	ema21_arr = np.full(n, np.nan)
	if n >= 21:
		ema21_arr[20] = np.mean(close_arr[:21])
		mult = 2.0 / (21 + 1)
		for i in range(21, n):
			ema21_arr[i] = close_arr[i] * mult + ema21_arr[i - 1] * (1 - mult)
	ema21 = float(ema21_arr[-1]) if not np.isnan(ema21_arr[-1]) else 0.0

	# Pullback volume: avg of last N days
	pullback_vol = float(np.mean(vol_arr[-pullback_vol_days:]))
	avg_vol_50 = float(np.mean(vol_arr[-50:]))
	if avg_vol_50 <= 0:
		return []
	observed_vol_ratio = round(pullback_vol / avg_vol_50, 2)
	low_volume = observed_vol_ratio < pullback_vol_ratio_max

	if not low_volume:
		return []

	ma_configs = [
		("10_SMA", sma10),
		("21_EMA", ema21),
		("50_SMA", sma50),
	]

	patterns = []
	for ma_type, ma_val in ma_configs:
		if ma_val <= 0 or np.isnan(ma_val):
			continue

		distance_pct = abs(current_price - ma_val) / ma_val * 100
		if distance_pct > ma_proximity_pct:
			continue

		trigger_price = round(ma_val * (1 + ma_trigger_buffer_pct / 100), 2)
		stop_price = round(ma_val * (1 - ma_stop_buffer_pct / 100), 2)

		if ma_type in ("21_EMA", "50_SMA") and observed_vol_ratio < pullback_vol_ratio_max:
			quality = "high"
		else:
			quality = "moderate"

		patterns.append({
			"pattern": "MA_PULLBACK",
			"provenance": "[TL]",
			"tactic_layer": "opt_in",
			"ma_type": ma_type,
			"distance_pct": round(distance_pct, 2),
			"distance_pct_unit": "% from MA",
			"pullback_volume_ratio": observed_vol_ratio,
			"pullback_volume_ratio_unit": f"{pullback_vol_days}d avg vol / 50d avg vol",
			"heuristic_thresholds": {
				"pullback_volume_ratio_max": pullback_vol_ratio_max,
				"ma_proximity_pct": ma_proximity_pct,
				"trigger_buffer_pct": ma_trigger_buffer_pct,
				"stop_buffer_pct": ma_stop_buffer_pct,
			},
			"relative_strength_confirmation": "required_not_evaluated",
			"trigger_price": trigger_price,
			"stop_price": stop_price,
			"stop_pct": _stop_pct(trigger_price, stop_price),
			"stop_pct_unit": "% risk from trigger to stop",
			"quality": quality,
		})

	return patterns


def _detect_consolidation_pivot(
	close_arr,
	high_arr,
	low_arr,
	vol_arr,
	pivot_min_days=PIVOT_MIN_DAYS,
	pivot_max_days=PIVOT_MAX_DAYS,
	pivot_range_max=PIVOT_RANGE_MAX,
	pivot_high_range_pct=DEFAULT_PIVOT_HIGH_RANGE_PCT,
	pivot_high_min_days=DEFAULT_PIVOT_HIGH_MIN_DAYS,
	pivot_trigger_buffer_pct=DEFAULT_PIVOT_TRIGGER_BUFFER_PCT,
	chase_max_pct=DEFAULT_CHASE_MAX_PCT,
):
	"""Detect CONSOLIDATION_PIVOT pattern.

	[TL opt-in] Finds a short internal-resistance pivot plus failure level. The
	numeric range, maturity, and buffer values are transparent implementation
	heuristics. Volume contraction raises quality; unlike an [M] completed VCP
	pivot, this detector does not claim canonical breakout qualification.
	"""
	n = len(high_arr)
	if n < 10:
		return []

	avg_vol_50 = float(np.mean(vol_arr[-50:])) if len(vol_arr) >= 50 else float(np.mean(vol_arr))

	for window in range(min(pivot_max_days, n), pivot_min_days - 1, -1):
		segment_high = high_arr[-window:]
		segment_low = low_arr[-window:]

		resistance = float(np.max(segment_high))
		support = float(np.min(segment_low))

		if support <= 0:
			continue

		range_pct = (resistance - support) / support * 100
		if range_pct >= pivot_range_max:
			continue

		# Volume vacuum into the pivot: at least one of the last few days below the
		# 50-day average. Without it, the range is churn, not a base completing.
		recent_vol = vol_arr[-5:]
		dry_up_days = int(np.sum(recent_vol < avg_vol_50)) if avg_vol_50 > 0 else 0
		volume_dry_up = dry_up_days >= 1

		pivot_price = round(resistance, 2)
		trigger_price = round(resistance * (1 + pivot_trigger_buffer_pct / 100), 2)
		stop_price = round(support, 2)
		current_price = float(close_arr[-1])
		pivot_distance_pct = (current_price / resistance - 1) * 100
		if pivot_distance_pct < 0:
			trigger_state = "watch_below_pivot"
		elif pivot_distance_pct <= chase_max_pct:
			trigger_state = "triggered_within_chase_limit"
		else:
			trigger_state = "extended_above_chase_limit"

		# "high" needs a tight, mature range AND the volume vacuum — both, not either.
		if range_pct < pivot_high_range_pct and window >= pivot_high_min_days and volume_dry_up:
			quality = "high"
		else:
			quality = "moderate"

		return [{
			"pattern": "CONSOLIDATION_PIVOT",
			"provenance": "[TL]",
			"tactic_layer": "opt_in",
			"pivot_price": pivot_price,
			"current_price": round(current_price, 2),
			"pivot_distance_pct": round(pivot_distance_pct, 2),
			"trigger_state": trigger_state,
			"chase_limit_pct": chase_max_pct,
			"range_pct": round(range_pct, 2),
			"range_pct_unit": "% price range over N days",
			"days_in_range": window,
			"volume_dry_up": volume_dry_up,
			"dry_up_days_last5": dry_up_days,
			"heuristic_thresholds": {
				"range_max_pct": pivot_range_max,
				"high_quality_range_pct": pivot_high_range_pct,
				"high_quality_min_days": pivot_high_min_days,
				"trigger_buffer_pct": pivot_trigger_buffer_pct,
			},
			"trigger_price": trigger_price,
			"stop_price": stop_price,
			"stop_pct": _stop_pct(trigger_price, stop_price),
			"stop_pct_unit": "% risk from trigger to stop",
			"quality": quality,
		}]

	return []


def _detect_support_reclaim(
	close_arr,
	low_arr,
	vol_arr,
	dates,
	undercut_lookback_days=UNDERCUT_LOOKBACK_DAYS,
	undercut_depth_pct=DEFAULT_UNDERCUT_DEPTH_PCT,
	reclaim_vol_ratio=DEFAULT_RECLAIM_VOL_RATIO,
):
	"""Detect SUPPORT_RECLAIM pattern.

	[TL opt-in] Detects a recent 50 SMA undercut followed by an actual later
	close back above the contemporaneous 50 SMA. The depth and volume thresholds
	are flexible implementation heuristics, not SEPA canon.
	"""
	n = len(close_arr)
	if n < LOCKED_MIN_HISTORY_DAYS:
		return []

	sma50_current = float(np.mean(close_arr[-50:]))
	if sma50_current <= 0:
		return []

	# Current close must be above 50 SMA (reclaimed)
	if close_arr[-1] <= sma50_current:
		return []

	# Check last N days for an undercut, then locate the first actual reclaim.
	for offset in range(1, undercut_lookback_days + 1):
		idx = n - 1 - offset
		if idx < 49:
			break

		sma50_at_idx = float(np.mean(close_arr[idx - 49 : idx + 1]))
		if sma50_at_idx <= 0:
			continue

		if low_arr[idx] < sma50_at_idx * (1 - undercut_depth_pct / 100):
			undercut_pct = round((sma50_at_idx - low_arr[idx]) / sma50_at_idx * 100, 2)
			reclaim_idx = None
			reclaim_sma50 = None
			for candidate_idx in range(idx + 1, n):
				if candidate_idx < LOCKED_MIN_HISTORY_DAYS - 1:
					continue
				candidate_sma50 = float(np.mean(close_arr[candidate_idx - 49 : candidate_idx + 1]))
				if close_arr[candidate_idx] > candidate_sma50:
					reclaim_idx = candidate_idx
					reclaim_sma50 = candidate_sma50
					break
			if reclaim_idx is None:
				continue

			# Volume surge check: reclaim day volume vs 50d avg
			avg_vol_50 = float(np.mean(vol_arr[reclaim_idx - 49 : reclaim_idx + 1]))
			reclaim_vol = float(vol_arr[reclaim_idx])
			observed_reclaim_vol_ratio = reclaim_vol / avg_vol_50 if avg_vol_50 > 0 else None
			vol_surge = observed_reclaim_vol_ratio is not None and observed_reclaim_vol_ratio > reclaim_vol_ratio

			# [TL] Strong reclaim volume raises the opt-in tactic's quality.
			quality = "high" if vol_surge else "moderate"

			trigger_price = round(reclaim_sma50, 2)
			stop_price = round(float(low_arr[idx]), 2)

			return [{
				"pattern": "SUPPORT_RECLAIM",
				"provenance": "[TL]",
				"tactic_layer": "opt_in",
				"support_level": round(sma50_current, 2),
				"undercut_pct": undercut_pct,
				"undercut_pct_unit": "% below 50 SMA",
				"undercut_date": str(dates[idx].date()),
				"reclaim_date": str(dates[reclaim_idx].date()),
				"as_of_date": str(dates[-1].date()),
				"volume_surge_on_reclaim": vol_surge,
				"reclaim_volume_ratio": round(observed_reclaim_vol_ratio, 2) if observed_reclaim_vol_ratio is not None else None,
				"heuristic_thresholds": {
					"undercut_depth_pct": undercut_depth_pct,
					"reclaim_volume_ratio_min": reclaim_vol_ratio,
				},
				"trigger_price": trigger_price,
				"stop_price": stop_price,
				"stop_pct": _stop_pct(trigger_price, stop_price),
				"stop_pct_unit": "% risk from trigger to stop",
				"quality": quality,
			}]

	return []


def _add_risk_contract(pattern):
	"""Attach source-tagged risk validity without inventing a closer stop."""
	stop_pct = pattern.get("stop_pct")
	if stop_pct is None:
		status = "unavailable"
	elif stop_pct > LOCKED_MAX_STOP_PCT:
		status = "invalid_above_[M]_hard_cap"
	elif pattern.get("pattern") in {"CONSOLIDATION_PIVOT", "SUPPORT_RECLAIM"} and stop_pct >= 5:
		status = "outside_[TL]_tactic_max"
	elif pattern.get("pattern") in {"CONSOLIDATION_PIVOT", "SUPPORT_RECLAIM"} and stop_pct >= 3:
		status = "valid_above_[TL]_ideal"
	else:
		status = "within_risk_reference"
	pattern["risk_contract"] = {
		"status": status,
		"tradable": status in {"within_risk_reference", "valid_above_[TL]_ideal"},
		"[M]_locked_hard_cap_pct": LOCKED_MAX_STOP_PCT,
		"[TL]_consolidation_reclaim_reference": "ideal <3%; maximum <5%",
	}


def _volume_band(current_volume, average_volume, band_pct):
	"""Classify volume against the [TL] average +/- band."""
	if average_volume <= 0:
		return {"ratio": None, "classification": "unavailable"}
	ratio = current_volume / average_volume
	upper = 1 + band_pct / 100
	lower = 1 - band_pct / 100
	classification = "above_average" if ratio >= upper else "below_average" if ratio <= lower else "within_average_band"
	return {"ratio": round(ratio, 2), "classification": classification}


def _chart_quantifiers(high_arr, low_arr, close_arr, vol_arr, volume_band_pct):
	"""Compute only the map-defined [TL] CR and +/-volume-band quantities."""
	daily_range = float(high_arr[-1] - low_arr[-1])
	closing_range_pct = None if daily_range == 0 else round((close_arr[-1] - low_arr[-1]) / daily_range * 100, 2)
	current_volume = float(vol_arr[-1])
	return {
		"provenance": "[TL]",
		"closing_range_pct": closing_range_pct,
		"closing_range_interpretation": "buyer_dominant" if closing_range_pct is not None and closing_range_pct > 50 else "neutral" if closing_range_pct == 50 else "seller_dominant" if closing_range_pct is not None else "unavailable",
		"volume_band_pct": volume_band_pct,
		"volume_vs_20d": _volume_band(current_volume, float(np.mean(vol_arr[-20:])), volume_band_pct),
		"volume_vs_50d": _volume_band(current_volume, float(np.mean(vol_arr[-50:])), volume_band_pct),
		"adr_pct": None,
		"adr_note": "not computed: the binding knowledge maps provide the screen band but no formula, so this module does not invent one",
	}


def _determine_readiness(patterns):
	"""Report pattern candidacy without bypassing upstream qualification."""
	usable = [p for p in patterns if p.get("risk_contract", {}).get("tradable")]
	if not patterns:
		classification = "none"
	elif usable:
		classification = "candidate_requires_upstream_qualification"
	else:
		classification = "detected_but_risk_invalid"

	return {
		"classification": classification,
		"best_pattern_quality": "high" if any(p["quality"] == "high" for p in usable) else "moderate" if usable else None,
		"stage2_trend_template": "required_not_evaluated",
		"ma_pullback_relative_strength": "required_not_evaluated" if any(p["pattern"] == "MA_PULLBACK" for p in patterns) else "not_applicable",
		"thresholds": {
			"candidate": "[TL] pattern + valid tactic risk; still requires the [M] upstream gate",
			"risk_invalid": f"[M] stop above {LOCKED_MAX_STOP_PCT:g}% hard cap or outside the [TL] tactic risk band",
			"none": "no opt-in patterns detected",
		},
	}


def _scan_symbol(
	symbol,
	pullback_vol_days=PULLBACK_VOL_DAYS,
	pivot_min_days=PIVOT_MIN_DAYS,
	pivot_max_days=PIVOT_MAX_DAYS,
	undercut_lookback_days=UNDERCUT_LOOKBACK_DAYS,
	pivot_range_max=PIVOT_RANGE_MAX,
	pullback_vol_ratio_max=DEFAULT_PULLBACK_VOL_RATIO,
	ma_proximity_pct=DEFAULT_MA_PROXIMITY_PCT,
	pivot_high_range_pct=DEFAULT_PIVOT_HIGH_RANGE_PCT,
	pivot_high_min_days=DEFAULT_PIVOT_HIGH_MIN_DAYS,
	undercut_depth_pct=DEFAULT_UNDERCUT_DEPTH_PCT,
	reclaim_vol_ratio=DEFAULT_RECLAIM_VOL_RATIO,
	ma_trigger_buffer_pct=DEFAULT_MA_TRIGGER_BUFFER_PCT,
	ma_stop_buffer_pct=DEFAULT_MA_STOP_BUFFER_PCT,
	pivot_trigger_buffer_pct=DEFAULT_PIVOT_TRIGGER_BUFFER_PCT,
	chase_max_pct=DEFAULT_CHASE_MAX_PCT,
	volume_band_pct=DEFAULT_VOLUME_BAND_PCT,
):
	"""Core scan logic for a single symbol. Returns the result dict."""
	ticker = yf.Ticker(symbol)
	data = ticker.history(period="1y", interval="1d")
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < LOCKED_MIN_HISTORY_DAYS:
		return {
			"error": f"Insufficient data for {symbol}. Need at least {LOCKED_MIN_HISTORY_DAYS} trading days.",
			"data_points": len(data),
		}

	close_arr = data["Close"].values.astype(float)
	high_arr = data["High"].values.astype(float)
	low_arr = data["Low"].values.astype(float)
	vol_arr = data["Volume"].values.astype(float)
	dates = data.index

	# Run the explicitly opt-in [TL] tactic detectors. Upstream [M] qualification
	# is deliberately not duplicated or inferred here.
	active_patterns = []
	active_patterns.extend(
		_detect_ma_pullback(
			close_arr, vol_arr, pullback_vol_days, pullback_vol_ratio_max,
			ma_proximity_pct, ma_trigger_buffer_pct, ma_stop_buffer_pct,
		)
	)
	active_patterns.extend(
		_detect_consolidation_pivot(
			close_arr, high_arr, low_arr, vol_arr, pivot_min_days, pivot_max_days,
			pivot_range_max, pivot_high_range_pct, pivot_high_min_days,
			pivot_trigger_buffer_pct, chase_max_pct,
		)
	)
	active_patterns.extend(
		_detect_support_reclaim(
			close_arr, low_arr, vol_arr, dates, undercut_lookback_days,
			undercut_depth_pct, reclaim_vol_ratio,
		)
	)
	for pattern in active_patterns:
		_add_risk_contract(pattern)

	return {
		"symbol": symbol,
		"active_patterns": active_patterns,
		"pattern_count": len(active_patterns),
		"setup_readiness": _determine_readiness(active_patterns),
		"latest_bar_quantifiers": _chart_quantifiers(high_arr, low_arr, close_arr, vol_arr, volume_band_pct),
		"doctrine": _ENTRY_DOCTRINE,
	}


def _validate_tuning_args(args):
	"""Reject nonsensical flex values through the JSON/exit-1 contract."""
	for name in ("pullback_vol_days", "pivot_min_days", "pivot_max_days", "undercut_lookback_days", "pivot_high_min_days"):
		if getattr(args, name) < 1:
			raise ValueError(f"--{name.replace('_', '-')} must be at least 1")
	if args.pivot_min_days > args.pivot_max_days:
		raise ValueError("--pivot-min-days cannot exceed --pivot-max-days")
	for name in ("pivot_range_max", "pullback_vol_ratio_max", "reclaim_vol_ratio"):
		if getattr(args, name) <= 0:
			raise ValueError(f"--{name.replace('_', '-')} must be positive")
	for name in ("ma_proximity_pct", "pivot_high_range_pct", "undercut_depth_pct", "ma_trigger_buffer_pct", "ma_stop_buffer_pct", "pivot_trigger_buffer_pct", "chase_max_pct"):
		if getattr(args, name) < 0:
			raise ValueError(f"--{name.replace('_', '-')} must be non-negative")
	if not 0 <= args.volume_band_pct < 100:
		raise ValueError("--volume-band-pct must be in [0, 100)")
	if args.ma_stop_buffer_pct >= 100:
		raise ValueError("--ma-stop-buffer-pct must be below 100")
	if args.undercut_depth_pct >= 100:
		raise ValueError("--undercut-depth-pct must be below 100")


@safe_run
def cmd_scan(args):
	"""Scan for currently active entry patterns on a single stock."""
	configure_cache(args.no_cache or cache_disabled())
	_validate_tuning_args(args)
	symbol = args.symbol.upper()
	result = _scan_symbol(
		symbol,
		pullback_vol_days=args.pullback_vol_days,
		pivot_min_days=args.pivot_min_days,
		pivot_max_days=args.pivot_max_days,
		undercut_lookback_days=args.undercut_lookback_days,
		pivot_range_max=args.pivot_range_max,
		pullback_vol_ratio_max=args.pullback_vol_ratio_max,
		ma_proximity_pct=args.ma_proximity_pct,
		pivot_high_range_pct=args.pivot_high_range_pct,
		pivot_high_min_days=args.pivot_high_min_days,
		undercut_depth_pct=args.undercut_depth_pct,
		reclaim_vol_ratio=args.reclaim_vol_ratio,
		ma_trigger_buffer_pct=args.ma_trigger_buffer_pct,
		ma_stop_buffer_pct=args.ma_stop_buffer_pct,
		pivot_trigger_buffer_pct=args.pivot_trigger_buffer_pct,
		chase_max_pct=args.chase_max_pct,
		volume_band_pct=args.volume_band_pct,
	)
	if "error" in result:
		error_json(result["error"])
	_emit_result(result)


@safe_run
def cmd_screen(args):
	"""Batch scan multiple stocks for entry patterns."""
	configure_cache(args.no_cache or cache_disabled())
	_validate_tuning_args(args)
	symbols = [s.upper() for s in args.symbols]
	results = []

	for symbol in symbols:
		scan = _scan_symbol(
			symbol,
			pullback_vol_days=args.pullback_vol_days,
			pivot_min_days=args.pivot_min_days,
			pivot_max_days=args.pivot_max_days,
			undercut_lookback_days=args.undercut_lookback_days,
			pivot_range_max=args.pivot_range_max,
			pullback_vol_ratio_max=args.pullback_vol_ratio_max,
			ma_proximity_pct=args.ma_proximity_pct,
			pivot_high_range_pct=args.pivot_high_range_pct,
			pivot_high_min_days=args.pivot_high_min_days,
			undercut_depth_pct=args.undercut_depth_pct,
			reclaim_vol_ratio=args.reclaim_vol_ratio,
			ma_trigger_buffer_pct=args.ma_trigger_buffer_pct,
			ma_stop_buffer_pct=args.ma_stop_buffer_pct,
			pivot_trigger_buffer_pct=args.pivot_trigger_buffer_pct,
			chase_max_pct=args.chase_max_pct,
			volume_band_pct=args.volume_band_pct,
		)

		if "error" in scan:
			results.append({
				"symbol": symbol,
				"unavailable": scan["error"],
				"pattern_count": 0,
				"best_pattern": None,
				"best_quality": None,
				"setup_readiness": "none",
			})
			continue

		best_pattern = None
		best_quality = None
		quality_rank = {"high": 2, "moderate": 1}

		for p in scan["active_patterns"]:
			q = p["quality"]
			if best_quality is None or quality_rank.get(q, 0) > quality_rank.get(best_quality, 0):
				best_pattern = p["pattern"]
				best_quality = q

		sr = scan["setup_readiness"]
		results.append({
			"symbol": symbol,
			"pattern_count": scan["pattern_count"],
			"best_pattern": best_pattern,
			"best_quality": best_quality,
			"setup_readiness": sr["classification"] if isinstance(sr, dict) else sr,
			"latest_bar_quantifiers": scan["latest_bar_quantifiers"],
		})

	results.sort(key=lambda r: (r["pattern_count"], quality_rank.get(r.get("best_quality"), 0)), reverse=True)

	_emit_result({
		"results": results,
		"ranked_by": "pattern_count_then_quality",
	})


def _add_tuning_args(p):
	"""Attach transparent [TL]/implementation flex defaults."""
	p.add_argument(
		"--pullback-vol-days",
		type=int,
		default=PULLBACK_VOL_DAYS,
		help="[TL tactic; implementation default] Days averaged to measure pullback volume. Context-dependent: how many "
		"days define 'the pullback' depends on how long the dip lasted — widen for a "
		"slower, multi-day drift; tighten for a sharp one-day shakeout.",
	)
	p.add_argument(
		"--pivot-min-days",
		type=int,
		default=PIVOT_MIN_DAYS,
		help="[TL tactic; implementation default] Shortest short-consolidation window. "
		"length scales with the base's timeframe — raise for longer consolidations.",
	)
	p.add_argument(
		"--pivot-max-days",
		type=int,
		default=PIVOT_MAX_DAYS,
		help="[TL tactic; implementation default] Longest short-consolidation window. "
		"length scales with the base's timeframe — raise to admit wider, slower bases.",
	)
	p.add_argument(
		"--undercut-lookback-days",
		type=int,
		default=UNDERCUT_LOOKBACK_DAYS,
		help="[TL tactic; implementation default] Days scanned back for the support undercut-and-reclaim. "
		"how far back to look varies with the dip's length — widen for a drawn-out shakeout.",
	)
	p.add_argument(
		"--pivot-range-max",
		type=float,
		default=PIVOT_RANGE_MAX,
		help="[TL tactic; invented flex heuristic] Short-consolidation range ceiling (%% high-to-low); not the [M] 4-7 week flat-base definition.",
	)
	p.add_argument("--pullback-vol-ratio-max", type=float, default=DEFAULT_PULLBACK_VOL_RATIO, help="[TL tactic; invented flex heuristic] Maximum pullback volume / 50d average")
	p.add_argument("--ma-proximity-pct", type=float, default=DEFAULT_MA_PROXIMITY_PCT, help="[TL tactic; invented flex heuristic] Maximum distance from a respected MA (%%)")
	p.add_argument("--pivot-high-range-pct", type=float, default=DEFAULT_PIVOT_HIGH_RANGE_PCT, help="[TL tactic; invented flex heuristic] Range ceiling for a high-quality candidate (%%)")
	p.add_argument("--pivot-high-min-days", type=int, default=DEFAULT_PIVOT_HIGH_MIN_DAYS, help="[TL tactic; invented flex heuristic] Minimum days for a high-quality candidate")
	p.add_argument("--undercut-depth-pct", type=float, default=DEFAULT_UNDERCUT_DEPTH_PCT, help="[TL tactic; invented flex heuristic] Minimum 50 SMA undercut depth (%%)")
	p.add_argument("--reclaim-vol-ratio", type=float, default=DEFAULT_RECLAIM_VOL_RATIO, help="[TL tactic; invented flex heuristic] Reclaim volume / 50d average for high quality")
	p.add_argument("--ma-trigger-buffer-pct", type=float, default=DEFAULT_MA_TRIGGER_BUFFER_PCT, help="[TL tactic; invented flex heuristic] Trigger buffer above the MA (%%)")
	p.add_argument("--ma-stop-buffer-pct", type=float, default=DEFAULT_MA_STOP_BUFFER_PCT, help="[TL tactic; invented flex heuristic] Failure level below the MA (%%)")
	p.add_argument("--pivot-trigger-buffer-pct", type=float, default=DEFAULT_PIVOT_TRIGGER_BUFFER_PCT, help="[TL tactic; invented flex heuristic] Trigger buffer above internal resistance (%%)")
	p.add_argument("--chase-max-pct", type=float, default=DEFAULT_CHASE_MAX_PCT, help="[TL] Harness default: maximum extension above pivot before the entry is chased (%%)")
	p.add_argument("--volume-band-pct", type=float, default=DEFAULT_VOLUME_BAND_PCT, help="[TL] Flex width for above/below-average volume classification (%%)")


def main():
	parser = _JsonArgumentParser(
		description="[M gate + TL opt-in] Entry Pattern Detection",
	)
	sub = parser.add_subparsers(dest="command", required=True, parser_class=_JsonArgumentParser)

	sp = sub.add_parser("scan", help="[TL opt-in after M gate] Scan one stock")
	sp.add_argument("symbol", help="Ticker symbol")
	_add_tuning_args(sp)
	sp.add_argument(
		"--no-cache",
		action="store_true",
		help="Bypass the transparent same-session market-data cache for this command.",
	)
	sp.set_defaults(func=cmd_scan)

	sp = sub.add_parser("screen", help="[TL opt-in after M gate] Batch scan stocks")
	sp.add_argument("symbols", nargs="+", help="Ticker symbols")
	_add_tuning_args(sp)
	sp.add_argument(
		"--no-cache",
		action="store_true",
		help="Bypass the transparent same-session market-data cache for this command.",
	)
	sp.set_defaults(func=cmd_screen)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
