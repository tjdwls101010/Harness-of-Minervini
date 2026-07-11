#!/usr/bin/env python3
"""Detect Minervini-map VCP-family price/volume evidence.

``detect`` reports 2-6 progressively tightening contractions over a 3-65 week
base, the ``nW d/f nT`` footprint, pivot and volume evidence, shakeouts, the 3C
turn, and the locked Power Play prerequisites. Flat Base is classified only in
its mapped 4-7 week and 10-15% scope. Daily and weekly intervals are supported.

The weighted readiness value is an explicitly labeled implementation heuristic.
This command does not establish Stage 2, Trend Template, market alignment,
fundamentals, or a trade decision; use the qualification pipeline for those
separate gates.

Example: ``python vcp.py detect NVDA --period 1y --interval 1d``
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import yfinance as yf
from utils import cache_disabled, configure_cache, error_json, output_json, safe_run


class JsonArgumentParser(argparse.ArgumentParser):
	"""Keep usage failures on the same JSON/exit-1 contract as runtime failures."""

	def error(self, message):
		error_json(message)

# --- Locked [M] gates: callers may tighten these, never relax them. ---
MIN_VCP_CONTRACTIONS = 2  # [M] A VCP needs at least two contractions; one pullback is not contraction evidence.
MAX_VCP_CONTRACTIONS = 6  # [M] More than six contractions is outside the canonical 2-6 sequence.
MIN_VCP_BASE_WEEKS = 3  # [M] A valid base needs at least three weeks; a shorter move is not a completed VCP base.
MAX_VCP_BASE_WEEKS = 65  # [M] Sixty-five weeks is the outer canonical VCP/base duration.
MAX_VCP_DEPTH_PCT = 60.0  # [M] A correction at or beyond 60% is rejected because the base is structurally broken.
MINERVINI_BREAKOUT_VOL_MULT = 1.0  # [M] Breakout volume must exceed the stock's own 50-day average.
MINERVINI_STRICT_BREAKOUT_VOL_MULT = 1.5  # [M] The strict confirmation variant is 50% above the 50-day average.
POWER_PLAY_ADVANCE_FLOOR_PCT = 100.0  # [M] A Power Play starts with a 100%+ advance; rarity is not permission to weaken it.
POWER_PLAY_MAX_ADVANCE_BARS = 39  # [M] The doubling must occur in less than eight 5-session weeks.
POWER_PLAY_FLAG_MIN_BARS = 12  # [M] The flag lasts at least 12 sessions and normally 3-6 weeks.
POWER_PLAY_FLAG_MAX_BARS = 30  # [M] Six 5-session weeks is the outer flag duration.
POWER_PLAY_MAX_CORRECTION_PCT = 25.0  # [M] The post-surge correction may not exceed the 20-25% band.
POWER_PLAY_TIGHT_RANGE_PCT = 10.0  # [M] The flag must be <=10% tight unless a clear VCP supplies the contraction evidence.
PIVOT_BUFFER_MIN_DOLLARS = 0.05  # [M] Confirmation begins five cents above the pivot, never at an invented percentage.
PIVOT_BUFFER_MAX_DOLLARS = 0.20  # [M] The canonical trigger buffer tops out twenty cents above the pivot.

# [M] Cup Completion Cheat prerequisites from the binding knowledge map.
CHEAT_PRIOR_ADVANCE_MIN_PCT = 25.0
CHEAT_PATTERN_MIN_WEEKS = 3
CHEAT_PATTERN_MAX_WEEKS = 45
CHEAT_CUP_DEPTH_MIN_PCT = 15.0
CHEAT_CUP_DEPTH_MAX_PCT = 40.0
CHEAT_CUP_DEPTH_HOSTILE_MAX_PCT = 50.0  # [M] Severe-bear exception; requires explicit caller context.
CHEAT_RECOVERY_MIN_PCT = 100.0 / 3.0
CHEAT_RECOVERY_MAX_PCT = 50.0
CHEAT_PLATEAU_MIN_PCT = 5.0
CHEAT_PLATEAU_MAX_PCT = 10.0

# --- Flex defaults and implementation heuristics (overridable via `detect`). ---
DEFAULT_MAX_DEPTH = MAX_VCP_DEPTH_PCT  # A flex cap can only make the locked [M] redline stricter.
DEFAULT_DRYUP_PCT = 70.0  # Heuristic: pivot-area volume below this % of base average is a dry-up proxy.
DEFAULT_BREAKOUT_VOL_MULT = MINERVINI_BREAKOUT_VOL_MULT
DEFAULT_POWERPLAY_ADVANCE_BARS = POWER_PLAY_MAX_ADVANCE_BARS
DEFAULT_CHEAT_PAUSE_BARS = 30  # cup-completion pause lookback window
DEFAULT_SHAKEOUT_SEARCH_BARS = 20  # undercut/recovery search horizon past a swing low
DEFAULT_REL_CORRECTION_RATIO = 2.5  # [M] Flex midpoint within the 2-3x relative-correction caution band.

# --- Implementation heuristics: diagnostics only, never canonical gates. ---
SHAKEOUT_RECOVERY_SURGE_MULT = 1.5  # Heuristic proxy for the map's unquantified recovery-volume surge.
DEMAND_SPIKE_MULT = 1.5  # Heuristic demand-spike proxy; not a standalone canonical gate.
STRONGLY_DECLINING_CONTRACTION_RATIO = 0.75  # Heuristic steep-dry-up grade, never an eligibility gate.


def _interval_rules(interval):
	"""Return session-equivalent windows without relabelling weeks as days."""
	if interval == "1wk":
		return {
			"bar_unit": "week",
			"bars_per_week": 1,
			"volume_baseline_bars": 10,  # 10 weeks ~= the canonical 50 sessions.
			"breakout_scan_bars": 1,
			"power_max_advance_bars": 7,  # strictly fewer than eight weeks.
			"power_flag_min_bars": 3,
			"power_flag_max_bars": 6,
			"shakeout_quick_bars": 1,
			"shakeout_destructive_bars": 2,
			"post_shakeout_bars": 1,
			"pivot_short_bars": 1,
			"pivot_baseline_bars": 10,
		}
	return {
		"bar_unit": "session",
		"bars_per_week": 5,
		"volume_baseline_bars": 50,
		"breakout_scan_bars": 5,
		"power_max_advance_bars": POWER_PLAY_MAX_ADVANCE_BARS,
		"power_flag_min_bars": POWER_PLAY_FLAG_MIN_BARS,
		"power_flag_max_bars": POWER_PLAY_FLAG_MAX_BARS,
		"shakeout_quick_bars": 3,
		"shakeout_destructive_bars": 5,
		"post_shakeout_bars": 3,
		"pivot_short_bars": 5,
		"pivot_baseline_bars": 50,
	}


def _find_swing_points(highs, lows, closes, window=5):
	"""Identify swing highs and swing lows in price data.

	A swing high is a high that is higher than `window` bars on each side.
	A swing low is a low that is lower than `window` bars on each side.
	"""
	swing_highs = []
	swing_lows = []

	highs_arr = highs.values.astype(float)
	lows_arr = lows.values.astype(float)

	for i in range(window, len(highs_arr) - window):
		# Swing high
		if all(highs_arr[i] >= highs_arr[i - j] for j in range(1, window + 1)) and all(
			highs_arr[i] >= highs_arr[i + j] for j in range(1, window + 1)
		):
			swing_highs.append((i, highs_arr[i]))

		# Swing low
		if all(lows_arr[i] <= lows_arr[i - j] for j in range(1, window + 1)) and all(
			lows_arr[i] <= lows_arr[i + j] for j in range(1, window + 1)
		):
			swing_lows.append((i, lows_arr[i]))

	return swing_highs, swing_lows


def _detect_contractions(swing_highs, swing_lows, closes):
	"""Detect VCP contractions from swing points.

	A contraction is measured as the decline from a swing high to the next swing low,
	expressed as a percentage.
	"""
	if not swing_highs or not swing_lows:
		return []

	contractions = []
	used_lows = set()

	for h_idx, h_price in swing_highs:
		# Find the nearest swing low after this high
		best_low = None
		for l_idx, l_price in swing_lows:
			if l_idx > h_idx and l_idx not in used_lows:
				best_low = (l_idx, l_price)
				break

		if best_low is not None:
			l_idx, l_price = best_low
			depth_pct = (h_price - l_price) / h_price * 100
			if depth_pct > 0:  # [M] supplies no minimum contraction depth; do not promote a worked 2% example into a gate.
				contractions.append(
					{
						"high_idx": h_idx,
						"high_price": round(h_price, 2),
						"low_idx": l_idx,
						"low_price": round(l_price, 2),
						"depth_pct": round(depth_pct, 2),
					}
				)
				used_lows.add(l_idx)

	return contractions


def _classify_pattern(contractions, base_weeks):
	"""Classify only VCP and map-scoped Flat Base geometry."""
	if not contractions:
		return "No Pattern"

	depth = contractions[0]["depth_pct"]
	num_contractions = len(contractions)

	# [M] Flat Base is narrowly scoped to 4-7 weeks and a 10-15% correction.
	if 4 <= base_weeks <= 7 and 10 <= depth <= 15:
		return "Flat Base"

	# Progressive 3T: 3 contractions with verified progressive tightening
	if num_contractions == 3:
		depths = [c["depth_pct"] for c in contractions]
		if all(depths[i] < depths[i - 1] for i in range(1, len(depths))):
			return "Progressive 3T"

	return "Standard VCP"


def _analyze_contraction_volume(volumes, contractions):
	"""Analyze volume behavior across successive VCP contractions.

	For each contraction, calculates the average daily volume across the
	high-to-low span. Computes volume ratios between successive contractions
	to determine if volume is declining (supply drying up).
	"""
	vol_arr = volumes.values.astype(float)
	avg_volumes = []
	for c in contractions:
		start = c["high_idx"]
		end = c["low_idx"]
		span = end - start
		if span < 3:
			continue
		seg = vol_arr[start : end + 1]
		avg_volumes.append(round(float(np.mean(seg))))

	vol_ratios = []
	for i in range(1, len(avg_volumes)):
		if avg_volumes[i - 1] > 0:
			vol_ratios.append(round(avg_volumes[i] / avg_volumes[i - 1], 3))

	declining = len(vol_ratios) > 0 and all(r < 1.0 for r in vol_ratios)
	strongly_declining = len(vol_ratios) > 0 and all(r < STRONGLY_DECLINING_CONTRACTION_RATIO for r in vol_ratios)

	return {
		"avg_volumes": avg_volumes,
		"vol_ratios": vol_ratios,
		"declining": declining,
		"strongly_declining": strongly_declining,
	}


def _check_volume_dryup(volumes, base_start_idx, pivot_idx, lookback=10, dryup_pct=DEFAULT_DRYUP_PCT):
	"""Check if volume dries up near the pivot relative to the full base.

	Compares average volume in the pivot area (last ``lookback`` days before
	the pivot) against the average volume across the entire base formation.
	"""
	vol_arr = volumes.values.astype(float)

	pivot_start = max(base_start_idx, pivot_idx - lookback)
	pivot_area = vol_arr[pivot_start : pivot_idx + 1]
	base_area = vol_arr[base_start_idx : pivot_idx + 1]

	if len(pivot_area) == 0 or len(base_area) == 0:
		return {
			"dryup_detected": False,
			"pivot_area_avg_vol": 0,
			"base_avg_vol": 0,
			"ratio_pct": 100.0,
		}

	pivot_avg = float(np.mean(pivot_area))
	base_avg = float(np.mean(base_area))
	ratio_pct = round(pivot_avg / base_avg * 100, 1) if base_avg > 0 else 100.0

	return {
		"dryup_detected": ratio_pct < dryup_pct,
		"pivot_area_avg_vol": round(pivot_avg),
		"base_avg_vol": round(base_avg),
		"ratio_pct": ratio_pct,
	}


def _assess_breakout_volume(
	volumes,
	closes,
	pivot_price=None,
	breakout_vol_mult=DEFAULT_BREAKOUT_VOL_MULT,
	*,
	baseline_bars=50,
	confirmation_bars=5,
	bar_unit="session",
):
	"""Confirm price *and* volume above a VCP pivot.

	[M] Volume must be strictly above the stock's 50-session average (10-week
	equivalent for weekly bars), and price must first clear the pivot by at least
	the canonical five-cent confirmation buffer. Merely trading near/below the
	pivot is not a breakout.
	"""
	vol_arr = volumes.values.astype(float)
	close_arr = closes.values.astype(float)
	window = min(max(1, baseline_bars), len(vol_arr))
	volume_baseline_avg = float(np.mean(vol_arr[-window:]))
	current_vol = float(vol_arr[-1])
	current_vs_avg_pct = round(current_vol / volume_baseline_avg * 100, 1) if volume_baseline_avg > 0 else 0.0

	# Check recent completed bars for price confirmation plus volume confirmation.
	breakout_confirmed = False
	confirmed_date = None
	scan_bars = min(max(1, confirmation_bars), len(vol_arr) - 1)
	if scan_bars >= 1:
		for i in range(-scan_bars, 0):
			price_up = close_arr[i] > close_arr[i - 1]
			vol_above = vol_arr[i] > volume_baseline_avg * breakout_vol_mult
			price_confirmed = close_arr[i] >= pivot_price + PIVOT_BUFFER_MIN_DOLLARS if pivot_price else True
			if price_up and vol_above and price_confirmed:
				breakout_confirmed = True
				confirmed_date = str(closes.index[i].date())
				break

	return {
		"volume_baseline_avg": round(volume_baseline_avg),
		"volume_baseline_bars": window,
		"volume_baseline_unit": bar_unit,
		"volume_baseline_equivalent": "50 sessions" if bar_unit == "session" else "10 weeks (~50 sessions)",
		"current_vol": round(current_vol),
		"current_vs_avg_pct": current_vs_avg_pct,
		"breakout_target_min": round(volume_baseline_avg * breakout_vol_mult),
		"breakout_target_strict": round(volume_baseline_avg * MINERVINI_STRICT_BREAKOUT_VOL_MULT),
		"price_confirmation_min": round(pivot_price + PIVOT_BUFFER_MIN_DOLLARS, 2) if pivot_price else None,
		"breakout_volume_confirmed": breakout_confirmed,
		"confirmed_date": confirmed_date,
		"provenance": "[M] price >= pivot+$0.05 and volume >50-session average; strict volume variant >=1.5x",
	}


def _detect_shakeouts(
	lows,
	closes,
	volumes,
	swing_lows,
	contractions,
	volume_baseline_avg,
	search_bars=DEFAULT_SHAKEOUT_SEARCH_BARS,
	*,
	bar_unit="session",
	quick_recovery_bars=3,
	destructive_bars=5,
):
	"""Detect shakeout events within the base formation with grading.

	A shakeout occurs when price undercuts a prior swing low then recovers
	quickly on above-average volume, trapping weak holders before the real
	advance.  One or more price shakeouts at key points during the
	base-building period is a constructive sign.

	Each shakeout is graded as constructive, neutral, or destructive based on
	recovery speed, volume surge, and location within the base.
	"""
	location_weights = {"pivot_area": 3, "right_side": 2, "handle": 2, "base_bottom": 1}
	grade_multipliers = {"constructive": 1.0, "neutral": 0.5, "destructive": 0.0}

	if not contractions or not swing_lows:
		return {
			"count": 0,
			"has_constructive_shakeout": False,
			"last_shakeout_date": None,
			"last_shakeout_location": None,
			"last_shakeout_recovery_volume_surge": False,
			"shakeout_quality_score": 0,
			"shakeouts_detail": [],
		}

	lows_arr = lows.values.astype(float)
	close_arr = closes.values.astype(float)
	vol_arr = volumes.values.astype(float)
	dates = lows.index

	base_start = contractions[0]["high_idx"]
	base_end = contractions[-1]["low_idx"]
	base_mid = (base_start + base_end) // 2
	pivot_zone_start = max(base_start, base_end - 15)

	shakeouts = []
	for i, (sl_idx, sl_price) in enumerate(swing_lows):
		if sl_idx < base_start or sl_idx > base_end:
			continue
		# Check if a subsequent low undercuts this swing low
		for j in range(sl_idx + 1, min(sl_idx + search_bars, len(lows_arr))):
			if j > base_end + 10:
				break
			if lows_arr[j] < sl_price:
				# Undercut detected -- measure recovery
				recovered = False
				surge = False
				duration_below = 0
				recovery_vol_ratio = 0.0
				reclaimed = False

				for k in range(j, min(j + search_bars, len(lows_arr))):
					if close_arr[k] < sl_price:
						duration_below += 1
					else:
						reclaimed = True
						if k > j:
							recovery_vol_ratio = round(vol_arr[k] / volume_baseline_avg, 2) if volume_baseline_avg > 0 else 0.0
							surge = recovery_vol_ratio >= SHAKEOUT_RECOVERY_SURGE_MULT
						recovered = True
						break

				if recovered:
					if sl_idx >= pivot_zone_start:
						loc = "pivot_area"
					elif sl_idx >= base_mid:
						loc = "right_side"
					elif sl_idx <= base_start + (base_mid - base_start) // 3:
						loc = "base_bottom"
					else:
						loc = "handle"

					# Grade: constructive / neutral / destructive
					if duration_below <= quick_recovery_bars and surge:
						grade = "constructive"
					elif duration_below >= destructive_bars or (duration_below >= quick_recovery_bars and not surge):
						grade = "destructive"
					else:
						grade = "neutral"

					shakeouts.append(
						{
							"idx": j,
							"date": str(dates[j].date()) if j < len(dates) else None,
							"location": loc,
							"volume_surge": surge,
							"duration_below_bars": duration_below,
							"bar_unit": bar_unit,
							"recovery_volume_ratio": recovery_vol_ratio,
							"reclaimed_support": reclaimed,
							"grade": grade,
						}
					)
				break  # only count one undercut per swing low

	# Shakeout quality score (0-10)
	raw_score = 0
	for s in shakeouts:
		loc_w = location_weights.get(s["location"], 1)
		grade_m = grade_multipliers.get(s["grade"], 0.5)
		raw_score += loc_w * grade_m
	shakeout_quality_score = min(10, round(raw_score, 1))

	last = shakeouts[-1] if shakeouts else None
	has_constructive = any(s["grade"] == "constructive" for s in shakeouts)
	return {
		"count": len(shakeouts),
		"has_constructive_shakeout": has_constructive,
		"last_shakeout_date": last["date"] if last else None,
		"last_shakeout_location": last["location"] if last else None,
		"last_shakeout_recovery_volume_surge": last["volume_surge"] if last else False,
		"shakeout_quality_score": shakeout_quality_score,
		"shakeouts_detail": [
			{
				"date": s["date"],
				"location": s["location"],
				"grade": s["grade"],
				"duration_below_bars": s["duration_below_bars"],
				"bar_unit": s["bar_unit"],
				"recovery_volume_ratio": s["recovery_volume_ratio"],
				"reclaimed_support": s["reclaimed_support"],
			}
			for s in shakeouts
		],
	}


def _detect_time_symmetry(contractions, *, bar_unit="session", bars_per_week=5):
	"""Assess left-side vs right-side time symmetry of the base.

	If a stock advances too quickly up the right side, this forms a
	hazardous time compression.  A V-shaped recovery is less reliable
	than a gradual, constructive right side.
	"""
	if not contractions:
		return {
			"left_side_bars": 0,
			"right_side_bars": 0,
			"bar_unit": bar_unit,
			"symmetry_ratio": 0.0,
			"time_compressed": False,
			"right_side_quality": "constructive",
		}

	base_high_idx = contractions[0]["high_idx"]
	base_low_idx = min(c["low_idx"] for c in contractions)
	pivot_idx = contractions[-1]["high_idx"]

	left_side_bars = max(1, base_low_idx - base_high_idx)
	right_side_bars = max(1, pivot_idx - base_low_idx)
	ratio = round(right_side_bars / left_side_bars, 2)

	compressed = ratio < 0.3
	v_shape = right_side_bars / bars_per_week < 2 and left_side_bars / bars_per_week > 4

	if v_shape:
		quality = "v_shape"
	elif compressed:
		quality = "compressed"
	else:
		quality = "constructive"

	return {
		"left_side_bars": left_side_bars,
		"right_side_bars": right_side_bars,
		"bar_unit": bar_unit,
		"left_side_weeks_equivalent": round(left_side_bars / bars_per_week, 1),
		"right_side_weeks_equivalent": round(right_side_bars / bars_per_week, 1),
		"symmetry_ratio": ratio,
		"time_compressed": compressed or v_shape,
		"right_side_quality": quality,
	}


def _detect_demand_evidence(
	closes, volumes, contractions, shakeout_result, volume_baseline_avg, *, post_shakeout_bars=3
):
	"""Detect demand evidence on the right side of the base.

	Look for significant, above-average increases in volume on upward
	moves coming off the lows and up the right side of the base.
	Compares volume spikes on up-days (right side) vs down-days
	(left side) to gauge institutional demand.
	"""
	if not contractions:
		return {
			"right_side_up_spikes": 0,
			"left_side_down_spikes": 0,
			"demand_dominance": False,
			"post_shakeout_demand": False,
		}

	close_arr = closes.values.astype(float)
	vol_arr = volumes.values.astype(float)
	spike_threshold = volume_baseline_avg * DEMAND_SPIKE_MULT

	base_low_idx = min(c["low_idx"] for c in contractions)
	base_start = contractions[0]["high_idx"]
	base_end = contractions[-1]["low_idx"]

	# Left side: base_start to base_low -- count volume spikes on down-days
	left_down_spikes = 0
	for i in range(base_start + 1, min(base_low_idx + 1, len(close_arr))):
		if close_arr[i] < close_arr[i - 1] and vol_arr[i] >= spike_threshold:
			left_down_spikes += 1

	# Right side: base_low to base_end -- count volume spikes on up-days
	right_up_spikes = 0
	for i in range(base_low_idx + 1, min(base_end + 1, len(close_arr))):
		if close_arr[i] > close_arr[i - 1] and vol_arr[i] >= spike_threshold:
			right_up_spikes += 1

	demand_dominance = right_up_spikes > left_down_spikes

	# Post-shakeout demand: 1.5x+ volume up-day within 3 days after last shakeout
	post_shakeout_demand = False
	if shakeout_result.get("has_constructive_shakeout"):
		last_date = shakeout_result.get("last_shakeout_date")
		if last_date:
			dates = closes.index
			date_strs = [str(d.date()) for d in dates]
			if last_date in date_strs:
				shake_idx = date_strs.index(last_date)
				for k in range(shake_idx + 1, min(shake_idx + post_shakeout_bars + 1, len(close_arr))):
					if close_arr[k] > close_arr[k - 1] and vol_arr[k] >= spike_threshold:
						post_shakeout_demand = True
						break

	return {
		"right_side_up_spikes": right_up_spikes,
		"left_side_down_spikes": left_down_spikes,
		"demand_dominance": demand_dominance,
		"post_shakeout_demand": post_shakeout_demand,
	}


def _check_pivot_tightness(
	highs,
	lows,
	closes,
	volumes,
	pivot_idx,
	base_start_idx,
	*,
	short_bars=5,
	baseline_bars=50,
	bar_unit="session",
):
	"""Evaluate price and volume tightness near the pivot area.

	Tightness in price from absolute highs to lows and tight closes with
	little change in price from one day to the next.  Tight, low-volume
	pivots produce more reliable breakouts.
	"""
	high_arr = highs.values.astype(float)
	low_arr = lows.values.astype(float)
	close_arr = closes.values.astype(float)
	vol_arr = volumes.values.astype(float)

	if pivot_idx < short_bars or pivot_idx >= len(close_arr):
		return {
			"atr_ratio": None,
			"max_close_change_5d_pct": None,
			"pre_pivot_volume_percentile": None,
			"is_tight": False,
		}

	# Short-window range near pivot.
	pivot_start = max(0, pivot_idx - short_bars + 1)
	pivot_ranges = high_arr[pivot_start : pivot_idx + 1] - low_arr[pivot_start : pivot_idx + 1]
	atr_5d = float(np.mean(pivot_ranges))

	# 50-session / 10-week equivalent baseline (or shorter available span).
	baseline_start = max(0, pivot_idx - baseline_bars + 1)
	baseline_ranges = high_arr[baseline_start : pivot_idx + 1] - low_arr[baseline_start : pivot_idx + 1]
	atr_baseline = float(np.mean(baseline_ranges)) if len(baseline_ranges) > 0 else atr_5d
	atr_ratio = round(atr_5d / atr_baseline, 2) if atr_baseline > 0 else 1.0

	# Max close-to-close change in the short window (%).
	max_cc_change = 0.0
	for i in range(pivot_start + 1, pivot_idx + 1):
		if close_arr[i - 1] > 0:
			change = abs(close_arr[i] - close_arr[i - 1]) / close_arr[i - 1] * 100
			max_cc_change = max(max_cc_change, change)
	max_cc_change = round(max_cc_change, 2)

	# Pre-pivot volume percentile (5-day avg ranked within base rolling windows)
	pivot_vol_avg = float(np.mean(vol_arr[pivot_start : pivot_idx + 1]))
	base_span = pivot_idx - base_start_idx
	if base_span >= 10:
		window_avgs = []
		for w in range(base_start_idx, pivot_idx - 4):
			window_avgs.append(float(np.mean(vol_arr[w : w + 5])))
		if window_avgs:
			rank = sum(1 for v in window_avgs if v <= pivot_vol_avg)
			percentile = round(rank / len(window_avgs) * 100, 1)
		else:
			percentile = 50.0
	else:
		percentile = 50.0

	is_tight = atr_ratio < 0.5 and percentile < 30

	return {
		"atr_ratio": atr_ratio,
		"max_close_change_5d_pct": max_cc_change,
		"pre_pivot_volume_percentile": percentile,
		"is_tight": is_tight,
		"short_window_bars": short_bars,
		"baseline_window_bars": baseline_bars,
		"bar_unit": bar_unit,
	}


def _flag_vcp_structure(highs, lows, closes):
	"""Return flag-local VCP evidence; never borrow structure from another base."""
	if len(closes) < 5:
		return {"detected": False, "contractions": 0, "depths": []}
	window = 1 if len(closes) < 20 else 2
	swing_highs, swing_lows = _find_swing_points(highs, lows, closes, window=window)
	contractions = _detect_contractions(swing_highs, swing_lows, closes)
	depths = [c["depth_pct"] for c in contractions]
	detected = (
		MIN_VCP_CONTRACTIONS <= len(depths) <= MAX_VCP_CONTRACTIONS
		and all(depths[i] < depths[i - 1] for i in range(1, len(depths)))
	)
	return {"detected": detected, "contractions": len(depths), "depths": depths}


def _detect_power_play(
	opens,
	highs,
	closes,
	volumes,
	volume_baseline_avg,
	advance_bars=DEFAULT_POWERPLAY_ADVANCE_BARS,
	has_vcp_structure=False,
	*,
	lows=None,
	interval="1d",
):
	"""Detect the quantified [M] Power Play gates in the current flag.

	The advance window is a *maximum*, not an exact duration: any 100%+ move in
	strictly fewer than eight weeks can qualify. A 3-6 week flag must correct no
	more than 25% and be <=10% tight or show VCP contractions inside that same
	flag. Prior dormancy remains chart context rather than an invented formula.
	"""
	del opens  # Preserved in the public helper signature for compatibility.
	rules = _interval_rules(interval)
	close_arr = closes.values.astype(float)
	high_arr = highs.values.astype(float)
	low_series = lows if lows is not None else closes
	low_arr = low_series.values.astype(float)
	vol_arr = volumes.values.astype(float)
	n = len(close_arr)
	dates = closes.index

	if interval == "1wk":
		max_advance_bars = min(
			rules["power_max_advance_bars"],
			max(1, int(np.ceil(advance_bars / 5.0))),
		)
	else:
		max_advance_bars = min(rules["power_max_advance_bars"], advance_bars)
	flag_min = rules["power_flag_min_bars"]
	flag_max = rules["power_flag_max_bars"]
	if n < max_advance_bars + flag_min:
		return {"detected": False, "reason": "insufficient_data_for_advance_plus_flag"}

	best_play = None
	# The flag either reaches the latest bar, or the latest bar is its breakout.
	for trailing_breakout_bars in (0, 1):
		flag_end = n - trailing_breakout_bars
		for flag_bars in range(flag_min, flag_max + 1):
			flag_start = flag_end - flag_bars
			advance_end = flag_start - 1
			if advance_end < 1:
				continue
			advance_start_floor = max(0, advance_end - max_advance_bars)
			window = close_arr[advance_start_floor:advance_end]
			if len(window) == 0:
				continue
			# When the dormant floor repeats, use its most recent occurrence: the
			# rule is any qualifying move inside the maximum window, not an exact
			# 39-session measurement forced back to the earliest equal low.
			min_price = float(np.min(window))
			start_i = advance_start_floor + int(np.flatnonzero(window == min_price)[-1])
			start_price = close_arr[start_i]
			if start_price <= 0:
				continue
			advance_pct = (close_arr[advance_end] / start_price - 1) * 100
			advance_duration = advance_end - start_i
			if advance_pct < POWER_PLAY_ADVANCE_FLOOR_PCT or advance_duration > max_advance_bars:
				continue

			advance_high = float(np.max(high_arr[start_i:advance_end + 1]))
			flag_highs = high_arr[flag_start:flag_end]
			flag_lows = low_arr[flag_start:flag_end]
			flag_vols = vol_arr[flag_start:flag_end]
			if len(flag_highs) != flag_bars:
				continue
			flag_high = float(np.max(flag_highs))
			flag_low = float(np.min(flag_lows))
			flag_range_pct = (flag_high - flag_low) / flag_high * 100 if flag_high > 0 else 999.0
			correction_from_high = (advance_high - flag_low) / advance_high * 100 if advance_high > 0 else 999.0
			if correction_from_high > POWER_PLAY_MAX_CORRECTION_PCT:
				continue

			flag_vcp = _flag_vcp_structure(
				highs.iloc[flag_start:flag_end],
				low_series.iloc[flag_start:flag_end],
				closes.iloc[flag_start:flag_end],
			)
			# ``has_vcp_structure`` is kept only as a compatibility hint for direct
			# callers; command code never passes a global/unrelated base verdict.
			flag_vcp_detected = flag_vcp["detected"] or bool(has_vcp_structure)
			if flag_range_pct > POWER_PLAY_TIGHT_RANGE_PCT and not flag_vcp_detected:
				continue

			if trailing_breakout_bars:
				breakout_close = close_arr[-1]
				if breakout_close < flag_high + PIVOT_BUFFER_MIN_DOLLARS:
					continue

			advance_vols = vol_arr[start_i:advance_end + 1]
			max_advance_volume_ratio = (
				float(np.max(advance_vols)) / volume_baseline_avg
				if volume_baseline_avg > 0 and len(advance_vols)
				else None
			)
			heavy_volume_observed = max_advance_volume_ratio is not None and max_advance_volume_ratio > 1.0
			if not heavy_volume_observed:
				continue

			if len(flag_vols) >= 2:
				mid = max(1, len(flag_vols) // 2)
				volume_contracting = float(np.mean(flag_vols[mid:])) < float(np.mean(flag_vols[:mid]))
			else:
				volume_contracting = None

			candidate = {
				"advance_pct": round(advance_pct, 1),
				"advance_bars": advance_duration,
				"advance_bar_unit": rules["bar_unit"],
				"advance_weeks_equivalent": round(advance_duration / rules["bars_per_week"], 1),
				"advance_start_date": str(dates[start_i].date()),
				"advance_end_date": str(dates[advance_end].date()),
				"flag_bars": flag_bars,
				"flag_bar_unit": rules["bar_unit"],
				"flag_weeks_equivalent": round(flag_bars / rules["bars_per_week"], 1),
				"flag_range_pct": round(flag_range_pct, 2),
				"correction_from_high_pct": round(correction_from_high, 2),
				"qualification_mode": "tight_range" if flag_range_pct <= POWER_PLAY_TIGHT_RANGE_PCT else "flag_local_vcp",
				"flag_vcp": flag_vcp,
				"volume_contracting": volume_contracting,
				"advance_max_volume_ratio": round(max_advance_volume_ratio, 2),
				"heavy_volume_observed": heavy_volume_observed,
				"dormancy_context": "needs_chart",
				"pivot_price": round(flag_high, 2),
				"state": "breakout_confirmed" if trailing_breakout_bars else "flag_in_progress_or_ready",
			}
			if best_play is None or candidate["advance_pct"] > best_play["advance_pct"]:
				best_play = candidate

	if best_play is None:
		return {"detected": False, "reason": "no_canonical_100pct_advance_and_qualified_current_flag"}

	best_play["quality"] = (
		"textbook"
		if best_play["flag_range_pct"] <= POWER_PLAY_TIGHT_RANGE_PCT and best_play["volume_contracting"] is not False
		else "acceptable"
	)
	best_play["detected"] = True
	best_play["fundamentals_exception"] = {
		"status": "map_authorized_only_for_this_vcp-qualified_setup",
		"may_omit": ["verified_fundamentals"],
		"never_waives": ["Stage-2 eligibility", "price/volume structure", "market alignment", "risk controls"],
	}
	return best_play


def _detect_3c_entry(
	closes,
	highs,
	lows,
	volumes,
	volume_baseline_avg,
	pause_bars=DEFAULT_CHEAT_PAUSE_BARS,
	*,
	interval="1d",
	hostile_market=False,
):
	"""Detect a 3C only when every quantified [M] prerequisite is observable."""
	rules = _interval_rules(interval)
	close_arr = closes.values.astype(float)
	high_arr = highs.values.astype(float)
	low_arr = lows.values.astype(float)
	vol_arr = volumes.values.astype(float)
	n = len(close_arr)
	ma_period = 40 if interval == "1wk" else 200
	ma_slope_bars = 4 if interval == "1wk" else 22
	prior_min_bars = 13 if interval == "1wk" else 63
	prior_max_bars = 156 if interval == "1wk" else 756
	peak_exclusion = 4 if interval == "1wk" else 20
	min_pause_bars = 2 if interval == "1wk" else 5
	configured_pause_bars = max(min_pause_bars, int(np.ceil(pause_bars / 5.0))) if interval == "1wk" else pause_bars

	if n < ma_period + ma_slope_bars:
		return {"detected": False, "reason": "insufficient_history_for_rising_200day_equivalent"}

	search_end = n - peak_exclusion
	if search_end <= prior_min_bars:
		return {"detected": False, "reason": "insufficient_prior_advance_context"}
	peak_idx = int(np.argmax(high_arr[:search_end]))
	peak_price = float(high_arr[peak_idx])
	if peak_idx < prior_min_bars or peak_price <= 0:
		return {"detected": False, "reason": "insufficient_3_to_36_month_prior_advance_context"}

	prior_start = max(0, peak_idx - prior_max_bars)
	prior_low_idx = prior_start + int(np.argmin(low_arr[prior_start:peak_idx]))
	prior_low = float(low_arr[prior_low_idx])
	prior_advance_pct = (peak_price / prior_low - 1) * 100 if prior_low > 0 else 0.0
	if prior_advance_pct < CHEAT_PRIOR_ADVANCE_MIN_PCT:
		return {"detected": False, "reason": f"prior_advance_{prior_advance_pct:.1f}pct_below_[M]_25pct_floor"}

	pattern_bars = n - peak_idx
	pattern_weeks = pattern_bars / rules["bars_per_week"]
	if not CHEAT_PATTERN_MIN_WEEKS <= pattern_weeks <= CHEAT_PATTERN_MAX_WEEKS:
		return {"detected": False, "reason": f"pattern_duration_{pattern_weeks:.1f}w_outside_[M]_3_45w"}

	bottom_idx = peak_idx + int(np.argmin(low_arr[peak_idx:]))
	bottom_price = float(low_arr[bottom_idx])
	cup_depth_pct = (peak_price - bottom_price) / peak_price * 100
	depth_ceiling = _three_c_depth_ceiling(hostile_market)
	if not CHEAT_CUP_DEPTH_MIN_PCT <= cup_depth_pct <= depth_ceiling:
		reason = "needs_hostile_market_context" if CHEAT_CUP_DEPTH_MAX_PCT < cup_depth_pct <= CHEAT_CUP_DEPTH_HOSTILE_MAX_PCT else "out_of_range"
		return {"detected": False, "reason": f"cup_depth_{cup_depth_pct:.1f}pct_{reason}"}

	cup_range = peak_price - bottom_price
	recovery_pct = (close_arr[-1] - bottom_price) / cup_range * 100 if cup_range > 0 else 0.0
	if not CHEAT_RECOVERY_MIN_PCT <= recovery_pct <= CHEAT_RECOVERY_MAX_PCT:
		return {"detected": False, "reason": f"recovery_{recovery_pct:.1f}pct_outside_[M]_one-third_to_one-half"}

	# [M] The plateau itself is 5-10%. Find the longest recent window that
	# satisfies it, rather than widening the source band to force a detection.
	max_pause = min(configured_pause_bars, n - bottom_idx)
	pause = None
	for length in range(max_pause, min_pause_bars - 1, -1):
		start = n - length
		segment_high = float(np.max(high_arr[start:]))
		segment_low = float(np.min(low_arr[start:]))
		range_pct = (segment_high - segment_low) / segment_high * 100 if segment_high > 0 else 999.0
		if CHEAT_PLATEAU_MIN_PCT <= range_pct <= CHEAT_PLATEAU_MAX_PCT:
			pause = (start, length, segment_high, segment_low, range_pct)
			break
	if pause is None:
		return {"detected": False, "reason": "no_[M]_5_10pct_plateau"}
	pause_start, pause_duration, pause_high, pause_low, pause_range_pct = pause

	ma = closes.rolling(ma_period, min_periods=ma_period).mean()
	ma_now = float(ma.iloc[-1])
	ma_then = float(ma.iloc[-1 - ma_slope_bars])
	ma_rising = ma_now > ma_then
	price_above_rising_ma = close_arr[-1] > ma_now and ma_rising
	if not price_above_rising_ma:
		return {"detected": False, "reason": "price_not_above_rising_200day_equivalent"}

	pause_avg_vol = float(np.mean(vol_arr[pause_start:]))
	pause_volume_dryup = pause_avg_vol < volume_baseline_avg if volume_baseline_avg > 0 else False

	# Optional [M] shakeout evidence: an intrabar undercut of already-established
	# plateau support followed by a close back above it within three sessions
	# (one weekly bar). This is a quality bonus, not a 3C hard prerequisite.
	has_shakeout = False
	recovery_window = 1 if interval == "1wk" else 3
	for i in range(pause_start + 1, n):
		prior_support = float(np.min(low_arr[pause_start:i]))
		if low_arr[i] < prior_support:
			for j in range(i, min(i + recovery_window + 1, n)):
				if close_arr[j] >= prior_support:
					has_shakeout = True
					break
		if has_shakeout:
			break

	return {
		"detected": True,
		"prior_advance_pct": round(prior_advance_pct, 1),
		"prior_advance_start_date": str(closes.index[prior_low_idx].date()),
		"cup_peak_price": round(peak_price, 2),
		"cup_bottom_price": round(bottom_price, 2),
		"cup_depth_pct": round(cup_depth_pct, 1),
		"hostile_market_context": bool(hostile_market),
		"pattern_duration_weeks": round(pattern_weeks, 1),
		"recovery_pct": round(recovery_pct, 1),
		"pause_range_pct": round(pause_range_pct, 1),
		"pause_duration_bars": pause_duration,
		"pause_bar_unit": rules["bar_unit"],
		"pause_volume_dryup": pause_volume_dryup,
		"price_above_rising_200day_equivalent": price_above_rising_ma,
		"has_shakeout_in_pause": has_shakeout,
		"pivot_price": round(pause_high, 2),
		"entry_price": round(pause_high + PIVOT_BUFFER_MIN_DOLLARS, 2),
		"entry_buffer_zone": {
			"min_price": round(pause_high + PIVOT_BUFFER_MIN_DOLLARS, 2),
			"max_price": round(pause_high + PIVOT_BUFFER_MAX_DOLLARS, 2),
			"provenance": "[M] 5-20 cents above the pivot",
		},
		"quality": "textbook" if pause_volume_dryup and has_shakeout else "acceptable",
		"locked_gates": {
			"prior_advance": "[M] >=25% within 3-36 months",
			"trend": "[M] above a rising 200-day MA equivalent",
			"duration": "[M] 3-45 weeks",
			"cup_depth": "[M] 15-40%; explicit --hostile-market permits the severe-bear exception through 50%",
			"recovery": "[M] one-third to one-half",
			"plateau": "[M] 5-10%",
		},
	}


def _three_c_depth_ceiling(hostile_market):
	"""Return the [M] 3C depth ceiling for explicit market context."""
	return CHEAT_CUP_DEPTH_HOSTILE_MAX_PCT if hostile_market else CHEAT_CUP_DEPTH_MAX_PCT


def _volume_confirmation_grade(contraction_vol, dryup):
	"""Synthesize contraction volume analysis and dryup into a single grade.

	Returns one of: strongly_confirmed, confirmed, supportive, neutral,
	suspect, divergent.
	"""
	vol_declining = contraction_vol["declining"]
	vol_strongly = contraction_vol["strongly_declining"]
	vol_ratios = contraction_vol["vol_ratios"]
	dryup_detected = dryup["dryup_detected"]

	# divergent: volume increasing each contraction
	if len(vol_ratios) > 0 and all(r > 1.0 for r in vol_ratios):
		return "divergent"

	# suspect: volume mostly rising
	if len(vol_ratios) > 0 and sum(1 for r in vol_ratios if r > 1.0) > len(vol_ratios) / 2:
		return "suspect"

	# strongly_confirmed: strongly declining contraction volume AND dryup
	if vol_strongly and dryup_detected:
		return "strongly_confirmed"

	# confirmed: declining contraction volume AND dryup detected
	if vol_declining and dryup_detected:
		return "confirmed"

	# supportive: one of the two present
	if vol_declining or dryup_detected:
		return "supportive"

	return "neutral"


def _grade_contraction_ratios(contraction_ratios):
	"""Grade each contraction ratio individually.

	ideal: 0.4-0.6, acceptable: 0.3-0.75, poor: outside range.
	"""
	grades = []
	for r in contraction_ratios:
		if 0.4 <= r <= 0.6:
			grades.append("ideal")
		elif 0.3 <= r <= 0.75:
			grades.append("acceptable")
		else:
			grades.append("poor")
	return grades


def _vcp_gate_checks(correction_depths, min_contractions, max_depth, base_weeks):
	"""Evaluate the locked [M] geometry/duration gates without a weighted score."""
	count = len(correction_depths)
	progressive = count >= 2 and all(
		correction_depths[i] < correction_depths[i - 1]
		for i in range(1, count)
	)
	checks = {
		"contractions_within_locked_2_to_6": MIN_VCP_CONTRACTIONS <= count <= MAX_VCP_CONTRACTIONS,
		"contractions_at_least_requested_min": count >= min_contractions,
		"progressively_tightening": progressive,
		"depth_below_locked_60pct": bool(
			correction_depths and correction_depths[0] < min(max_depth, MAX_VCP_DEPTH_PCT)
		),
		"duration_3_to_65_weeks": MIN_VCP_BASE_WEEKS <= base_weeks <= MAX_VCP_BASE_WEEKS,
	}
	return checks, all(checks.values())


def _classify_first_correction(depth_pct):
	"""Classify the first correction depth zone.

	shallow: <10%, constructive_shallow: 10-15%, constructive: 15-25%,
	deep_acceptable: 25-35%, excessive: >35%.
	"""
	if depth_pct < 10:
		return "shallow"
	elif depth_pct < 15:
		return "constructive_shallow"
	elif depth_pct <= 25:
		return "constructive"
	elif depth_pct <= 35:
		return "deep_acceptable"
	else:
		return "excessive"


def _calculate_setup_readiness(
	contraction_ratios,
	vol_grade,
	pivot_tightness,
	shakeout,
	time_symmetry,
	demand_evidence,
	power_play,
):
	"""Calculate VCP setup readiness composite score (0-100).

	Components:
	- Contraction quality (0-25)
	- Volume confirmation (0-20)
	- Pivot tightness (0-15)
	- Shakeout quality (0-15)
	- Time symmetry (0-10)
	- Demand evidence (0-10)
	- Pattern type bonus (0-5)
	"""
	score = 0

	# Contraction quality (0-25)
	if contraction_ratios:
		ideal_count = sum(1 for r in contraction_ratios if 0.4 <= r <= 0.6)
		acceptable_count = sum(1 for r in contraction_ratios if 0.3 <= r <= 0.75)
		ratio_pct = (ideal_count * 1.0 + (acceptable_count - ideal_count) * 0.6) / len(contraction_ratios)
		score += round(ratio_pct * 25, 1)

	# Volume confirmation (0-20)
	vol_scores = {
		"strongly_confirmed": 20,
		"confirmed": 16,
		"supportive": 12,
		"neutral": 8,
		"suspect": 4,
		"divergent": 0,
	}
	score += vol_scores.get(vol_grade, 8)

	# Pivot tightness (0-15)
	if pivot_tightness.get("is_tight"):
		score += 15
	elif pivot_tightness.get("atr_ratio") is not None:
		atr = pivot_tightness["atr_ratio"]
		if atr < 0.7:
			score += 10
		elif atr < 1.0:
			score += 5

	# Shakeout quality (0-15)
	sq = shakeout.get("shakeout_quality_score", 0)
	score += min(15, round(sq * 1.5, 1))

	# Time symmetry (0-10)
	ts_quality = time_symmetry.get("right_side_quality", "constructive")
	if ts_quality == "constructive":
		score += 10
	elif ts_quality == "compressed":
		score += 5
	else:
		score += 2

	# Demand evidence (0-10)
	if demand_evidence.get("demand_dominance"):
		score += 7
	if demand_evidence.get("post_shakeout_demand"):
		score += 3

	# Pattern type bonus (0-5): use the strongest detected pattern once, never stack bonuses past the stated cap.
	pattern_bonus = 0
	if power_play.get("detected") and power_play.get("quality") == "textbook":
		pattern_bonus = max(pattern_bonus, 5)
	elif power_play.get("detected"):
		pattern_bonus = max(pattern_bonus, 3)
	score += pattern_bonus

	score = min(100, round(score, 1))

	# Pattern-evidence classification only; the command does not evaluate Stage 2,
	# Trend Template, market alignment, or fundamentals.
	if score >= 80:
		classification = "pattern_evidence_exceptional"
	elif score >= 60:
		classification = "pattern_evidence_strong"
	elif score >= 40:
		classification = "pattern_evidence_developing"
	elif score >= 20:
		classification = "pattern_evidence_early"
	else:
		classification = "pattern_evidence_weak"

	return {
		"score": score,
		"unit": "implementation-heuristic weighted composite (contraction 25 + volume 20 + pivot_tightness 15 + shakeout 15 + time_symmetry 10 + demand 10 + pattern 5 = 100 max); never an eligibility gate",
		"thresholds": {
			"status": "implementation heuristic; labels rank pattern evidence only",
			"exceptional_pattern_evidence": ">=80 heuristic points",
			"strong_pattern_evidence": "60-79 heuristic points",
			"developing_pattern_evidence": "40-59 heuristic points",
			"early_pattern_evidence": "20-39 heuristic points",
			"weak_pattern_evidence": "<20 heuristic points",
		},
		"classification": classification,
	}


@safe_run
def cmd_detect(args):
	"""Detect VCP pattern in a ticker's price data."""
	symbol = args.symbol.upper()
	if not MIN_VCP_CONTRACTIONS <= args.min_contractions <= MAX_VCP_CONTRACTIONS:
		error_json(f"--min-contractions must be within the locked [M] range {MIN_VCP_CONTRACTIONS}-{MAX_VCP_CONTRACTIONS}.")
	if not 0 < args.max_depth <= MAX_VCP_DEPTH_PCT:
		error_json(f"--max-depth may tighten but never relax the locked [M] rejection boundary of {MAX_VCP_DEPTH_PCT:g}%.")
	if not 0 < args.dryup_pct <= 100:
		error_json("--dryup-pct must be within (0, 100].")
	if args.breakout_vol_mult < MINERVINI_BREAKOUT_VOL_MULT:
		error_json(f"--breakout-vol-mult cannot be below the locked [M] floor of {MINERVINI_BREAKOUT_VOL_MULT:g}x.")
	if not 1 <= args.powerplay_advance_bars <= POWER_PLAY_MAX_ADVANCE_BARS:
		error_json(f"--powerplay-advance-bars must be 1-{POWER_PLAY_MAX_ADVANCE_BARS}; a Power Play must double in less than eight weeks [M].")
	if args.cheat_pause_bars < 5 or args.shakeout_search_bars < 1:
		error_json("--cheat-pause-bars must be >=5 and --shakeout-search-bars must be >=1.")
	if not 0 < args.rel_correction_ratio <= 3.0:
		error_json("--rel-correction-ratio must be within (0, 3]; [M] treats more than 2-3x the market decline as excessive.")
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval=args.interval)
	# Drop the partial current-session bar yfinance appends mid-day (NaN OHLC).
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if args.interval == "1wk":
		swing_window = 3  # 3 weekly bars (~3 weeks)
		min_data_points = 26  # ~6 months weekly
	else:
		swing_window = 5
		min_data_points = 60
	interval_rules = _interval_rules(args.interval)

	if data.empty or len(data) < min_data_points:
		error_json(f"Insufficient data for {symbol}. Need at least {min_data_points} {interval_rules['bar_unit']} bars (received {len(data)}).")

	closes = data["Close"]
	highs = data["High"]
	lows = data["Low"]
	volumes = data["Volume"]
	current_price = float(closes.iloc[-1])

	# Find swing points
	swing_highs, swing_lows = _find_swing_points(highs, lows, closes, window=swing_window)

	# Detect contractions
	contractions = _detect_contractions(swing_highs, swing_lows, closes)

	# Filter: only use recent contractions (within the base formation)
	# Look back from the highest recent swing high
	if contractions:
		# Find the highest swing high as the base start
		max_high = max(contractions, key=lambda c: c["high_price"])
		max_high_idx = contractions.index(max_high)
		# Use contractions from the highest point onward
		relevant_contractions = contractions[max_high_idx:]
	else:
		relevant_contractions = []

	# Check for progressive tightening
	correction_depths = [c["depth_pct"] for c in relevant_contractions]
	contraction_ratios = []
	is_tightening = True

	for i in range(1, len(correction_depths)):
		if correction_depths[i - 1] > 0:
			ratio = correction_depths[i] / correction_depths[i - 1]
			contraction_ratios.append(round(ratio, 2))
			if ratio >= 1.0:
				is_tightening = False

	# Volume analysis (contraction volume; breakout volume computed after pivot)
	contraction_vol = _analyze_contraction_volume(volumes, relevant_contractions)

	# Classify failure pattern when VCP not detected
	failure_pattern = None
	if not is_tightening and len(correction_depths) >= 2:
		if correction_depths[-1] > correction_depths[-2]:
			failure_pattern = "distribution_pattern"
		else:
			failure_pattern = "inconclusive"

	# Base duration in weeks
	if relevant_contractions:
		start_idx = relevant_contractions[0]["high_idx"]
		end_idx = relevant_contractions[-1]["low_idx"]
		base_bars = end_idx - start_idx + 1
		base_weeks = max(1, base_bars if args.interval == "1wk" else (base_bars + 4) // 5)
	else:
		base_weeks = 0
	vcp_gate_checks, vcp_detected = _vcp_gate_checks(
		correction_depths, args.min_contractions, args.max_depth, base_weeks
	)

	# Pivot price (high of the last contraction or recent resistance)
	if relevant_contractions:
		pivot_price = relevant_contractions[-1]["high_price"]
		pivot_idx = relevant_contractions[-1]["high_idx"]
	else:
		pivot_price = float(highs.tail(20).max())
		pivot_idx = len(closes) - 1

	# Breakout volume (pivot-aware: checks proximity to pivot price)
	breakout_vol = _assess_breakout_volume(
		volumes,
		closes,
		pivot_price=pivot_price,
		breakout_vol_mult=args.breakout_vol_mult,
		baseline_bars=interval_rules["volume_baseline_bars"],
		confirmation_bars=interval_rules["breakout_scan_bars"],
		bar_unit=interval_rules["bar_unit"],
	)
	volume_baseline_avg = breakout_vol["volume_baseline_avg"]

	# Volume dryup near pivot (adaptive lookback scales with base duration)
	base_start = relevant_contractions[0]["high_idx"] if relevant_contractions else 0
	dryup_base_span = pivot_idx - base_start if relevant_contractions else 0
	dryup_floor_bars = 2 if args.interval == "1wk" else 10
	dryup_lookback = max(dryup_floor_bars, dryup_base_span // 10)
	dryup = _check_volume_dryup(volumes, base_start, pivot_idx, lookback=dryup_lookback, dryup_pct=args.dryup_pct)

	# Volume confirmation grade
	vol_grade = _volume_confirmation_grade(contraction_vol, dryup)

	# Volume divergence as additional failure pattern
	if vol_grade == "divergent" and failure_pattern is None:
		failure_pattern = "volume_divergence"

	# Shakeout detection
	shakeout_search_bars = (
		max(1, int(np.ceil(args.shakeout_search_bars / 5.0)))
		if args.interval == "1wk"
		else args.shakeout_search_bars
	)
	shakeout = _detect_shakeouts(
		lows, closes, volumes, swing_lows, relevant_contractions,
		volume_baseline_avg,
		search_bars=shakeout_search_bars,
		bar_unit=interval_rules["bar_unit"],
		quick_recovery_bars=interval_rules["shakeout_quick_bars"],
		destructive_bars=interval_rules["shakeout_destructive_bars"],
	)

	# Time symmetry / compression
	time_symmetry = _detect_time_symmetry(
		relevant_contractions,
		bar_unit=interval_rules["bar_unit"],
		bars_per_week=interval_rules["bars_per_week"],
	)

	# Demand evidence (depends on shakeout result)
	demand_evidence = _detect_demand_evidence(
		closes,
		volumes,
		relevant_contractions,
		shakeout,
		volume_baseline_avg,
		post_shakeout_bars=interval_rules["post_shakeout_bars"],
	)

	# Pivot tightness
	pivot_tightness = _check_pivot_tightness(
		highs,
		lows,
		closes,
		volumes,
		pivot_idx,
		base_start,
		short_bars=interval_rules["pivot_short_bars"],
		baseline_bars=interval_rules["pivot_baseline_bars"],
		bar_unit=interval_rules["bar_unit"],
	)

	# Cup Completion Cheat (3C) entry detection
	cup_completion_cheat = _detect_3c_entry(
		closes, highs, lows, volumes, volume_baseline_avg,
		pause_bars=args.cheat_pause_bars, interval=args.interval, hostile_market=args.hostile_market,
	)

	# Power Play detection
	opens = data["Open"]
	power_play = _detect_power_play(
		opens,
		highs,
		closes,
		volumes,
		volume_baseline_avg,
		advance_bars=args.powerplay_advance_bars,
		lows=lows,
		interval=args.interval,
	)

	# Contraction ratio grades
	ratio_grades = _grade_contraction_ratios(contraction_ratios)

	# Technical footprint notation: "XW Y/Z/... NT"
	if correction_depths:
		depths_str = f"{int(round(correction_depths[0]))}/{int(round(correction_depths[-1]))}"
		footprint = f"{base_weeks}W {depths_str} {len(relevant_contractions)}T"
	else:
		footprint = "N/A"

	# Pattern classification
	overall_depth = correction_depths[0] if correction_depths else 0
	pattern_type = _classify_pattern(relevant_contractions, base_weeks)
	if power_play.get("detected"):
		pattern_type = "Power Play"

	# First correction zone classification
	first_correction_zone = _classify_first_correction(overall_depth)

	# Relative correction comparison vs SPY
	relative_correction = {"stock_correction_pct": 0, "spy_correction_pct": 0, "ratio": 0, "excessive_relative": False}
	if relevant_contractions:
		first_c = relevant_contractions[0]
		stock_corr = first_c["depth_pct"]
		try:
			spy_data = yf.Ticker("SPY").history(period=args.period, interval=args.interval)
			if not spy_data.empty and len(spy_data) >= len(data):
				# Map stock contraction indices to SPY data
				spy_closes = spy_data["Close"].values.astype(float)
				c_high_idx = first_c["high_idx"]
				c_low_idx = first_c["low_idx"]
				if c_high_idx < len(spy_closes) and c_low_idx < len(spy_closes):
					spy_high = float(np.max(spy_closes[c_high_idx : c_low_idx + 1]))
					spy_low = float(np.min(spy_closes[c_high_idx : c_low_idx + 1]))
					spy_corr = round((spy_high - spy_low) / spy_high * 100, 2) if spy_high > 0 else 0
					ratio = round(stock_corr / spy_corr, 2) if spy_corr > 0 else 0
					relative_correction = {
						"stock_correction_pct": round(stock_corr, 2),
						"spy_correction_pct": spy_corr,
						"ratio": ratio,
						"excessive_relative": ratio > args.rel_correction_ratio,
					}
		except Exception:
			pass

	# Pattern quality assessment (volume-adjusted, shakeout-adjusted)
	if vcp_detected:
		if all(r <= 0.6 for r in contraction_ratios) and len(relevant_contractions) >= 3:
			quality = "high"
		elif all(r <= 0.75 for r in contraction_ratios):
			quality = "moderate"
		else:
			quality = "low"
		# Volume caps quality
		if vol_grade == "divergent":
			quality = "low"
		elif vol_grade == "suspect" and quality == "high":
			quality = "moderate"
		# Shakeout adjustment
		has_constructive = any(s.get("grade") == "constructive" for s in shakeout.get("shakeouts_detail", []))
		has_destructive = any(s.get("grade") == "destructive" for s in shakeout.get("shakeouts_detail", []))
		if has_constructive and quality == "moderate":
			quality = "high"
		if has_destructive and quality == "high":
			quality = "moderate"
		# A first correction far deeper than the market's in the same window is
		# relative weakness, not leadership — so the excessive_relative signal, which
		# was being computed and then ignored, now actually gates the quality.
		if relative_correction.get("excessive_relative"):
			if quality == "high":
				quality = "moderate"
			elif quality == "moderate":
				quality = "low"
	else:
		quality = "none"

	# Setup readiness composite score
	setup_readiness = _calculate_setup_readiness(
		contraction_ratios,
		vol_grade,
		pivot_tightness,
		shakeout,
		time_symmetry,
		demand_evidence,
		power_play,
	)
	if not vcp_detected:
		setup_readiness["classification"] = "not_applicable"
		setup_readiness["eligibility_note"] = "Locked VCP structure/duration did not pass; the heuristic score is descriptive only."
	else:
		setup_readiness["eligibility_note"] = "Pattern-only ranking; Stage 2 and Trend Template eligibility remain external."

	# Integrate ratio/grade into contractions_detail
	for i, c in enumerate(relevant_contractions):
		if i > 0 and i - 1 < len(contraction_ratios):
			c["ratio_vs_prior"] = contraction_ratios[i - 1]
			c["ratio_grade"] = ratio_grades[i - 1] if i - 1 < len(ratio_grades) else None

	# Add thresholds to pivot_tightness
	pivot_tightness["unit"] = (
		f"{interval_rules['pivot_short_bars']}-{interval_rules['bar_unit']} range / "
		f"{interval_rules['pivot_baseline_bars']}-{interval_rules['bar_unit']} range"
	)
	pivot_tightness["thresholds"] = {"tight": "implementation heuristic: atr_ratio < 0.5 AND volume_percentile < 30"}

	volume_data = {
		"contraction_vol_declining": contraction_vol["declining"],
		"contraction_vol_strongly_declining": contraction_vol["strongly_declining"],
		"contraction_vol_ratios": contraction_vol["vol_ratios"],
		"contraction_avg_volumes": contraction_vol["avg_volumes"],
		"pivot_area_dryup": dryup["dryup_detected"],
		"pivot_vol_vs_base_pct": dryup["ratio_pct"],
		"volume_baseline_avg": breakout_vol["volume_baseline_avg"],
		"volume_baseline_bars": breakout_vol["volume_baseline_bars"],
		"volume_baseline_unit": breakout_vol["volume_baseline_unit"],
		"current_vol": breakout_vol["current_vol"],
		"current_vs_avg_pct": breakout_vol["current_vs_avg_pct"],
		"breakout_vol_target_min": breakout_vol["breakout_target_min"],
		"breakout_vol_target_strict": breakout_vol["breakout_target_strict"],
		"breakout_volume_confirmed": breakout_vol["breakout_volume_confirmed"],
		"volume_confirmation": vol_grade,
		"thresholds": {
			"declining": "each contraction avg vol < prior",
			"dryup": f"implementation heuristic: pivot area avg vol < {args.dryup_pct:g}% of base avg",
			"confirmation": "implementation heuristic: strongly_confirmed=strongly declining+dryup | confirmed=declining+dryup | supportive=either | neutral=mixed | suspect=rising | divergent=expanding",
		},
	}

	full_result = {
		"symbol": symbol,
		"date": str(data.index[-1].date()),
		"interval": args.interval,
		"current_price": round(current_price, 2),
		"vcp_detected": vcp_detected,
		"vcp_gate_checks": vcp_gate_checks,
		"contractions_count": len(relevant_contractions),
		"contraction_ratios": contraction_ratios,
		"contraction_ratio_grades": ratio_grades,
		"correction_depths": correction_depths,
		"base_duration_weeks": base_weeks,
		"pivot_price": round(pivot_price, 2),
		"technical_footprint": footprint,
		"pattern_type": pattern_type,
		"pattern_quality": quality,
		"is_tightening": is_tightening,
		"failure_pattern": failure_pattern,
		"first_correction_pct": round(overall_depth, 1),
		"first_correction_zone": first_correction_zone,
		"relative_correction": relative_correction,
		"setup_readiness": setup_readiness,
		"doctrine": {
			"pivot": "[M] The pivot is the final filter where price confirms demand has won. Front-running saves negligible price but assumes the full risk of an unconfirmed setup, so wait for the 5-20-cent confirmation zone above the pivot.",
			"pivot_volume_dryup": "[M] Volume is supply made visible: contraction and final-pivot dry-up show the last weak holders have been absorbed, leaving a line of least resistance for renewed demand.",
			"power_play": "[M] Power Play is a locked +100% in under eight weeks followed by a 3-6 week, <=25% correction that is <=10% tight or contains a clear VCP. It is the sole setup that can waive verified fundamentals, but it never waives Stage 2, price/volume structure, market alignment, or risk controls.",
			"scope": "[M] This command measures setup geometry only. It does not verify Stage 2 or the 8-of-8 Trend Template; run pipeline qualify before treating any pattern as eligible, and interpret rather than predict an unfinished pattern.",
		},
		"provenance": {
			"vcp_contractions_and_depth": "[M] locked 2-6 contractions, 3-65 weeks, and >=60% rejection",
			"breakout_volume": "[M] price >= pivot+$0.05 and volume >50-session average; strict [M] volume >=1.5x",
			"power_play": "[M] locked prerequisites",
			"relative_correction": "[M] flex default 2.5 within the 2-3x caution band",
			"dryup_and_score_cutoffs": "implementation heuristics; diagnostics, not doctrine or eligibility gates",
		},
		"contractions_detail": relevant_contractions,
		"cup_completion_cheat": cup_completion_cheat,
		"power_play": power_play,
		"shakeout": shakeout,
		"time_symmetry": time_symmetry,
		"demand_evidence": demand_evidence,
		"pivot_tightness": pivot_tightness,
		"volume": volume_data,
	}

	# --- Build compressed view for pipeline consumption ---
	# Cap shakeout details
	_shakeout = dict(shakeout)
	_shakeout_details = _shakeout.get("shakeouts_detail", [])
	if len(_shakeout_details) > 3:
		_shakeout["shakeouts_detail"] = _shakeout_details[:3]
		_shakeout["shakeouts_capped"] = True

	# Compress contractions_detail
	_compressed_detail = []
	for _c in relevant_contractions:
		_entry = {
			"high_price": _c.get("high_price"),
			"low_price": _c.get("low_price"),
			"depth_pct": _c.get("depth_pct"),
		}
		if "high_date" in _c:
			_entry["high_date"] = _c["high_date"]
		if "low_date" in _c:
			_entry["low_date"] = _c["low_date"]
		if "ratio_vs_prior" in _c:
			_entry["ratio_vs_prior"] = _c["ratio_vs_prior"]
		if "ratio_grade" in _c:
			_entry["ratio_grade"] = _c["ratio_grade"]
		_compressed_detail.append(_entry)

	compressed = {}
	for _key in ("vcp_detected", "contractions_count",
				"base_duration_weeks",
				"correction_depths", "pivot_price", "technical_footprint",
				"pattern_type", "pattern_quality", "first_correction_zone",
				"setup_readiness"):
		if _key in full_result:
			compressed[_key] = full_result[_key]
	compressed["contractions_detail"] = _compressed_detail

	_ccc = cup_completion_cheat
	if _ccc.get("detected"):
		compressed["cup_completion_cheat"] = _ccc
	_pp = power_play
	if _pp.get("detected"):
		compressed["power_play"] = _pp
	if relative_correction:
		compressed["relative_correction"] = relative_correction
	if _shakeout.get("count", 0) > 0:
		compressed["shakeout"] = _shakeout
	if volume_data:
		compressed["volume"] = {
			"contraction_vol_declining": volume_data.get("contraction_vol_declining"),
			"pivot_area_dryup": volume_data.get("pivot_area_dryup"),
			"pivot_vol_vs_base_pct": volume_data.get("pivot_vol_vs_base_pct"),
			"breakout_vol_target_min": volume_data.get("breakout_vol_target_min"),
			"volume_confirmation": volume_data.get("volume_confirmation"),
		}
		if "thresholds" in volume_data:
			compressed["volume"]["thresholds"] = volume_data["thresholds"]
	if pivot_tightness:
		compressed["pivot_tightness"] = pivot_tightness

	full_result["compressed"] = compressed

	output_json(full_result)


def main():
	parser = JsonArgumentParser(description="Volatility Contraction Pattern (VCP) Detection")
	sub = parser.add_subparsers(dest="command", required=True)

	sp = sub.add_parser("detect", help="Detect VCP pattern for a ticker")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--period", default="1y", help="Data period (default: 1y)")
	sp.add_argument(
		"--interval", default="1d", choices=["1d", "1wk"], help="Data interval: 1d (daily, default) or 1wk (weekly)"
	)
	sp.add_argument(
		"--min-contractions",
		type=int,
		default=MIN_VCP_CONTRACTIONS,
		help="[M] Minimum contractions (default: 2); may tighten only within locked 2-6 range.",
	)
	sp.add_argument(
		"--max-depth", type=float, default=DEFAULT_MAX_DEPTH,
		help="[M] Stricter first-correction cap %% (default: 60); >=60 is always rejected and callers may never relax it.",
	)
	sp.add_argument(
		"--dryup-pct", type=float, default=DEFAULT_DRYUP_PCT,
		help="Heuristic pivot-area dry-up proxy vs base avg %% (default: 70); diagnostic, not a canonical gate.",
	)
	sp.add_argument(
		"--breakout-vol-mult", type=float, default=DEFAULT_BREAKOUT_VOL_MULT,
		help="[M] Breakout volume multiple vs 50d avg (default: 1.0, must exceed it); 1.5 is the strict [M] variant, while 1.25 is [MM-Ryan].",
	)
	sp.add_argument(
		"--powerplay-advance-bars", type=int, default=DEFAULT_POWERPLAY_ADVANCE_BARS,
		help="[M] Maximum prior-advance scan window (default: 39 sessions, strictly <8 weeks); may only tighten.",
	)
	sp.add_argument(
		"--cheat-pause-bars", type=int, default=DEFAULT_CHEAT_PAUSE_BARS,
		help="Heuristic cup-completion pause search lookback (default: 30); pattern gates remain [M].",
	)
	sp.add_argument(
		"--hostile-market",
		action="store_true",
		help="[M] Explicitly enable the severe-bear 3C depth exception (40-50%%); never inferred from price history alone.",
	)
	sp.add_argument(
		"--shakeout-search-bars", type=int, default=DEFAULT_SHAKEOUT_SEARCH_BARS,
		help="Heuristic undercut/recovery search horizon after a swing low (default: 20); not a canonical threshold.",
	)
	sp.add_argument(
		"--rel-correction-ratio", type=float, default=DEFAULT_REL_CORRECTION_RATIO,
		help="[M] Flex threshold for stock/market correction ratio (default: 2.5 within canonical 2-3x band; cannot exceed 3).",
	)
	sp.add_argument("--no-cache", action="store_true", help="Bypass the shared read-through cache for this command")
	sp.set_defaults(func=cmd_detect)

	args = parser.parse_args()
	configure_cache(args.no_cache or cache_disabled())
	args.func(args)


if __name__ == "__main__":
	main()
