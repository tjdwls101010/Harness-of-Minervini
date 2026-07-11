#!/usr/bin/env python3
"""Price/volume evidence for setup confirmation and intraday execution.

Commands:
	analyze: Compare up-day with down-day volume; inspect recent up-volume and
		pullback evidence; and report [TL] closing range, ±25% volume
		bands, and ADR%.
	demand-days: Find in-base up-volume footprints that overwhelm prior
		down-volume and are not immediately invalidated by a larger down-volume bar.
	runrate: Extrapolate current regular-session volume and compare it with the
		stock's completed-session 20-day and 50-day averages.

The module deliberately does not count or cluster "distribution days." The
[M] map authorizes relative up/down-volume evidence, while broad regime state
is supplied separately by ``market_breadth.py`` (including its QQQ switch).
All command output is JSON.

See Also:
	- vcp.py: price/volume contraction and setup readiness
	- base_count.py: structural base maturity
	- stage_analysis.py: independent stage structure and weekly volume evidence
"""

from datetime import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
import pandas as pd
import yfinance as yf
from market_clock import get_market_state, is_early_close, session_progress
from utils import JsonArgumentParser, calculate_sma, configure_cache, error_json, output_json, safe_run

# [TL] Chart-reading quantifiers from TL-map cluster A. These describe the bar;
# they do not override the [M] setup, trend, or risk gates.
TL_VOLUME_BAND_PCT = 25.0
TL_CLOSING_RANGE_GATE_PCT = 50.0
TL_ADR_LOOKBACK = 10
TL_ADR_FLOOR_LOW_PCT = 3.0
TL_ADR_FLOOR_HIGH_PCT = 5.0

_VOLUME_PROVENANCE = {
	"data_source": "Yahoo Finance OHLCV via yfinance",
	"methodology": [
		"[M] volume confirmation and intraday full-session run-rate extrapolation",
		"[TL] closing range, 20d/50d volume ±25% bands, and ADR% quantifiers",
	],
}


def _closing_range_percent(close, high, low):
	"""[TL] CR=(Close-Low)/(High-Low)*100; a flat bar is indeterminate."""
	range_value = high - low
	if range_value <= 0:
		return None
	return round((close - low) / range_value * 100.0, 2)


def _adr_percent(data, lookback=TL_ADR_LOOKBACK):
	"""Average daily high-low range as a percentage of that session's low."""
	valid = data.dropna(subset=["High", "Low"]).tail(lookback)
	valid = valid[valid["Low"] > 0]
	if valid.empty:
		return None
	return round(float(((valid["High"] - valid["Low"]) / valid["Low"] * 100.0).mean()), 2)


def _volume_band(current_volume, average_volume):
	"""Classify volume against the [TL] average ±25% band."""
	if average_volume is None or average_volume <= 0:
		return None
	lower = average_volume * (1.0 - TL_VOLUME_BAND_PCT / 100.0)
	upper = average_volume * (1.0 + TL_VOLUME_BAND_PCT / 100.0)
	if current_volume < lower:
		status = "below_average"
	elif current_volume > upper:
		status = "above_average"
	else:
		status = "within_average_band"
	return {
		"average": round(float(average_volume), 2),
		"lower_25pct": round(float(lower), 2),
		"upper_25pct": round(float(upper), 2),
		"value": round(float(current_volume), 2),
		"pct_of_average": round(float(current_volume) / float(average_volume) * 100.0, 2),
		"status": status,
		"provenance": "[TL] average volume ±25% classification",
	}


def _project_full_session_volume(cumulative_volume, elapsed_fraction):
	"""[M] Extrapolate cumulative volume by regular-session elapsed fraction."""
	if not 0 < elapsed_fraction <= 1:
		raise ValueError("regular-session elapsed fraction must be in (0, 1]")
	return float(cumulative_volume) / float(elapsed_fraction)

# --- analyze: tunable lookback horizons (CLI-overridable defaults) ---
# The institutional supply/demand window; scales with how much base history matters.
ACCDIST_LOOKBACK = 50
# Recent-pressure window; a shorter horizon for the secondary ratio.
SHORT_LOOKBACK = 20
# How recent an elevated up-volume observation must be.
UP_VOLUME_WINDOW = 5
# How long the pullback being assessed is.
PULLBACK_WINDOW = 20

# [MM-Ryan] An up day at least 25% above 50-day average volume is useful
# participation evidence. Without a caller-supplied pivot it does not establish
# that a breakout occurred; VCP owns price-plus-pivot breakout confirmation.
RYAN_UP_VOLUME_MULT = 1.25

# --- analyze: accumulation/distribution grade bands (A-E) ---
# DOCTRINE — read before touching these numbers.
# Graded off up_down_volume_ratio_50d: a 50-day AGGREGATE of sum(up-day vol)/sum(down-day vol).
# It reads the LEVEL of net accumulation, smoothed over the base — a bounded
# average. A real Stage-2 leader still prints ~40-45% down-days, so the down-vol
# denominator never collapses and this ratio physically tops out around ~1.6-1.9
# (observed basket max AMD ~1.87, MU ~1.51; the neutral mega-cap cluster ~1.0).
# The bands are calibrated to THAT range: A isolates the strongest, B+/B the
# strong-but-not-dwarfing, C the neutral ~1.0 cluster, D/E the real decliners.
#
# DO NOT re-point these at the method's "several hundred to ~1,000%" (3-10x)
# surge figure. That figure (the single-day demand-surge standard; book Ch.10-11:
# "a surge of several hundred percent or even as much as 1,000 percent compared
# with the AVERAGE volume") is the magnitude of a SINGLE demand DAY's volume vs
# its own average — a per-bar surge, with a "the day FOLLOWED by a bigger down
# day disqualifies" rule that only parses against one bar. An aggregate has no
# surge and no next-day: a lone 8x demand day on a neutral 24up/25down baseline
# lifts this aggregate only to ~1.28. Demanding 3x here would make every real
# leader fail and collapse all grades into D/E. (An audit recommended exactly
# this; it was a metric-mismatch. This comment exists to stop the next one.)
# The 3-10x surge standard lives on the `demand-days` per-bar volume_ratio
# (up-day vol / max prior down-day vol), NOT here. The book's hard ratios
# (Nasdaq 9:1, NYSE 21:1) are MARKET-breadth reads, not per-stock aggregates.
#
# NO DISTRIBUTION-DAY COUNTING. Down-side pressure is already priced into this
# grade through down-day VOLUME (the denominator) — the faithful asymmetry. We
# do NOT add a "N distribution days -> cap the grade" tally: that is the O'Neil
# distribution-day / follow-through mechanism the method rejects (the source
# counts no distribution days). The forward
# "bigger-down-day-follows" disqualifier in demand-days is a magnitude rule, not
# a count, and stays.
ACCDIST_GRADE_A_PLUS_RATIO = 1.8   # strong accumulation (top up/down-volume tier)
ACCDIST_GRADE_A_RATIO = 1.5        # clear accumulation
ACCDIST_GRADE_B_PLUS_RATIO = 1.3   # moderate
ACCDIST_GRADE_B_RATIO = 1.15       # slight
ACCDIST_GRADE_C_RATIO = 0.85       # neutral floor (0.85-1.15 = neutral)
ACCDIST_GRADE_D_RATIO = 0.7        # slight-distribution floor (below this = heavy, grade E)


def _calc_up_down_ratio(volumes, closes, lookback):
	"""Calculate up-day volume to down-day volume ratio."""
	recent_vol = volumes.tail(lookback)
	recent_close = closes.tail(lookback)
	price_change = recent_close.diff()

	up_vol = float(recent_vol[price_change > 0].sum())
	down_vol = float(recent_vol[price_change < 0].sum())

	if down_vol == 0:
		return None, up_vol, down_vol
	return round(up_vol / down_vol, 3), up_vol, down_vol


def _grade_accumulation(up_down_ratio):
	"""Grade accumulation/distribution A-E on the up/down *volume* ratio alone.

	The up/down volume ratio already carries the institutional footprint — down
	volume is its denominator — so the grade reads it directly. It deliberately
	does NOT layer an accumulation-day vs distribution-day *count* test on top:
	tallying distribution days is the index-timing mechanic this methodology does
	not use, and gating the grade on it would double-count what the ratio already
	reflects. No such counts are produced.

	A+: ratio > 1.8   A: > 1.5   B+: > 1.3   B: > 1.15
	C:  0.85-1.15     D: 0.7-0.85   E: < 0.7
	"""
	if up_down_ratio is None:
		return "unavailable"
	if up_down_ratio > ACCDIST_GRADE_A_PLUS_RATIO:
		return "A+"
	elif up_down_ratio > ACCDIST_GRADE_A_RATIO:
		return "A"
	elif up_down_ratio > ACCDIST_GRADE_B_PLUS_RATIO:
		return "B+"
	elif up_down_ratio > ACCDIST_GRADE_B_RATIO:
		return "B"
	elif up_down_ratio > ACCDIST_GRADE_C_RATIO:
		return "C"
	elif up_down_ratio > ACCDIST_GRADE_D_RATIO:
		return "D"
	else:
		return "E"


def _check_pullback_volume(volumes, closes, lookback=20):
	"""Check if recent pullback shows declining volume (healthy)."""
	recent_vol = volumes.tail(lookback)
	recent_close = closes.tail(lookback)
	price_change = recent_close.diff()

	# Find if we're in a pullback (recent price decline)
	last_5_change = float(recent_close.iloc[-1] / recent_close.iloc[-5] - 1) * 100
	if last_5_change >= 0:
		return None, "not_in_pullback"

	# During pullback, is volume declining?
	down_days_vol = []
	for i in range(len(recent_vol) - 10, len(recent_vol)):
		if i >= 0 and price_change.iloc[i] < 0:
			down_days_vol.append(float(recent_vol.iloc[i]))

	if len(down_days_vol) < 2:
		return None, "insufficient_data"

	# Compare first half vs second half of down-day volumes
	mid = len(down_days_vol) // 2
	first_half_avg = np.mean(down_days_vol[:mid]) if mid > 0 else 0
	second_half_avg = np.mean(down_days_vol[mid:]) if mid < len(down_days_vol) else 0

	# [M] The map specifies declining pullback volume, not a numeric discount.
	declining = second_half_avg < first_half_avg if first_half_avg > 0 else False
	return declining, "declining" if declining else "increasing"


def _volume_direction_summary(volumes, closes, lookback=20):
	"""Summary statistics for recent volume direction (up vs down).

	Lightweight summary without daily detail to avoid token waste.
	"""
	recent_vol = volumes.tail(lookback)
	recent_close = closes.tail(lookback)
	price_change = recent_close.diff()

	up_vol_total = float(recent_vol[price_change > 0].sum())
	down_vol_total = float(recent_vol[price_change < 0].sum())
	ratio = round(up_vol_total / down_vol_total, 3) if down_vol_total > 0 else None

	return {
		"up_volume_total": int(up_vol_total),
		"down_volume_total": int(down_vol_total),
		"up_down_volume_ratio_by_total": ratio,
		"ratio_status": "available" if ratio is not None else "no_down_volume",
	}


@safe_run
def cmd_analyze(args):
	"""Full volume analysis with accumulation/distribution rating."""
	if args.no_cache:
		configure_cache(True)
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1d")
	# yfinance appends a partial in-session bar whose OHLC can be NaN; that NaN
	# poisons closes.iloc[-1] and every comparison downstream. Drop it first.
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 50:
		error_json(f"Insufficient data for {symbol}. Need at least 50 trading days (got {len(data)}).")

	closes = data["Close"]
	volumes = data["Volume"]
	current_price = float(closes.iloc[-1])

	# 50-day average volume
	vol_50avg = float(volumes.tail(50).mean())
	current_vol = float(volumes.iloc[-1])
	vol_vs_50avg_pct = round(current_vol / vol_50avg * 100, 1) if vol_50avg > 0 else 0
	vol_20avg = float(volumes.tail(20).mean())
	closing_range_pct = _closing_range_percent(
		float(data["Close"].iloc[-1]),
		float(data["High"].iloc[-1]),
		float(data["Low"].iloc[-1]),
	)
	adr_pct_10d = _adr_percent(data, TL_ADR_LOOKBACK)

	# Up/Down volume ratios at different lookbacks
	ratio_20, _, _ = _calc_up_down_ratio(volumes, closes, args.short_lookback)
	ratio_50, _, _ = _calc_up_down_ratio(volumes, closes, args.lookback)

	# Grade on the up/down volume ratio
	grade = _grade_accumulation(ratio_50)

	# [MM-Ryan] Recent participation evidence only. A pivot was not supplied, so
	# this observation must not be promoted to breakout confirmation.
	recent_up_volume_evidence = False
	recent_5_vol = volumes.tail(args.up_volume_window)
	recent_5_close = closes.tail(args.up_volume_window)
	recent_5_change = recent_5_close.diff()
	for i in range(1, len(recent_5_vol)):
		if recent_5_change.iloc[i] > 0 and recent_5_vol.iloc[i] >= vol_50avg * RYAN_UP_VOLUME_MULT:
			recent_up_volume_evidence = True
			break

	# Pullback volume analysis
	pullback_declining, pullback_status = _check_pullback_volume(volumes, closes, args.pullback_window)

	# Volume trend
	if ratio_50 is None:
		vol_trend = "unavailable"
	elif ratio_50 > 1.3:
		vol_trend = "accumulation"
	elif ratio_50 < 0.7:
		vol_trend = "distribution"
	else:
		vol_trend = "neutral"

	# Volume direction summary (20-day)
	vol_summary = _volume_direction_summary(volumes, closes, lookback=args.short_lookback)

	full_result = {
		"symbol": symbol,
		"date": str(data.index[-1].date()),
		"current_price": round(current_price, 2),
		"accumulation_distribution_rating": grade,
		"up_down_volume_ratio_50d": ratio_50,
		"up_down_volume_ratio_50d_status": "available" if ratio_50 is not None else "no_down_volume",
		"up_down_volume_ratio_50d_unit": "sum(up-day vol) / sum(down-day vol) over 50d",
		"up_down_volume_ratio_20d": ratio_20,
		"up_down_volume_ratio_20d_status": "available" if ratio_20 is not None else "no_down_volume",
		"volume_vs_50day_avg_pct": vol_vs_50avg_pct,
		"volume_vs_50day_avg_pct_unit": "current vol / 50d avg vol * 100",
		"current_volume": int(current_vol),
		"avg_volume_50d": int(vol_50avg),
		"avg_volume_20d": int(vol_20avg),
		"closing_range_pct": closing_range_pct,
		"closing_range_buyers_control": (
			closing_range_pct is not None and closing_range_pct > TL_CLOSING_RANGE_GATE_PCT
		),
		"volume_bands": {
			"20d": _volume_band(current_vol, vol_20avg),
			"50d": _volume_band(current_vol, vol_50avg),
		},
		"adr_pct_10d": adr_pct_10d,
		"adr_pct_10d_formula": "mean((High-Low)/Low*100) over the latest 10 daily bars",
		"adr_meets_tl_3pct_floor": adr_pct_10d is not None and adr_pct_10d >= TL_ADR_FLOOR_LOW_PCT,
		"adr_meets_tl_5pct_floor": adr_pct_10d is not None and adr_pct_10d >= TL_ADR_FLOOR_HIGH_PCT,
		"recent_up_volume_evidence": recent_up_volume_evidence,
		"recent_up_volume_window_days": args.up_volume_window,
		"breakout_volume_confirmation": None,
		"breakout_volume_confirmation_status": "not_evaluated_without_pivot; use vcp.py detect",
		"volume_trend": vol_trend,
		"pullback_volume_declining": pullback_declining,
		"pullback_status": pullback_status,
		"volume_direction_summary_20d": vol_summary,
		"thresholds": {
			"A+": "[heuristic] up_down_volume_ratio_50d > 1.8",
			"A": "[heuristic] up_down_volume_ratio_50d > 1.5",
			"B+": "[heuristic] up_down_volume_ratio_50d > 1.3",
			"B": "[heuristic] up_down_volume_ratio_50d > 1.15",
			"C": "[heuristic] up_down_volume_ratio_50d 0.85-1.15 (neutral)",
			"D": "[heuristic] up_down_volume_ratio_50d 0.7-0.85 (slight distribution)",
			"E": "[heuristic] up_down_volume_ratio_50d < 0.7 (heavy distribution)",
			"grade_input": "[heuristic] up_down_volume_ratio_50d only; no distribution-day count",
			"recent_up_volume": "[MM-Ryan] up-day volume >=25% above 50d average; participation evidence only, not pivot-breakout confirmation",
			"closing_range": "[TL] CR=(Close-Low)/(High-Low)*100; >50% means buyers won the bar",
			"volume_band": "[TL] 20d/50d volume average ±25%",
			"adr_pct": "[TL] approximate ADR% 3-5% floor range; descriptive, not a SEPA hard gate",
		},
		"doctrine": (
			"[M] Price is the aggregate of better-informed hands, so a failure to RALLY "
			"on unambiguously good news (a beat or a guidance raise) is smart money "
			"using the good-news liquidity to distribute — the dog that doesn't bark "
			"front-runs deterioration that becomes public later; the DEPTH of the "
			"sell-off separates healthy profit-taking from broken. And tape strength "
			"here is only HALF of catalyst confirmation: it must be paired with the "
			"numbers coming in strong, or it's a narrative with no earnings. [TL] CR, "
			"volume bands, and ADR% quantify bar character but never replace the SEPA gates."
		),
		"provenance": _VOLUME_PROVENANCE,
	}

	# Compressed view for pipeline consumption
	full_result["compressed"] = {
		"accumulation_distribution_rating": full_result.get("accumulation_distribution_rating"),
		"up_down_volume_ratio_50d": full_result.get("up_down_volume_ratio_50d"),
		"up_down_volume_ratio_50d_status": full_result.get("up_down_volume_ratio_50d_status"),
		"up_down_volume_ratio_50d_unit": full_result.get("up_down_volume_ratio_50d_unit"),
		"up_down_volume_ratio_20d": full_result.get("up_down_volume_ratio_20d"),
		"up_down_volume_ratio_20d_status": full_result.get("up_down_volume_ratio_20d_status"),
		"volume_vs_50day_avg_pct": full_result.get("volume_vs_50day_avg_pct"),
		"recent_up_volume_evidence": full_result.get("recent_up_volume_evidence"),
		"breakout_volume_confirmation": None,
		"breakout_volume_confirmation_status": full_result.get("breakout_volume_confirmation_status"),
		"volume_trend": full_result.get("volume_trend"),
		"pullback_volume_declining": full_result.get("pullback_volume_declining"),
		"closing_range_pct": full_result.get("closing_range_pct"),
		"volume_bands": full_result.get("volume_bands"),
		"adr_pct_10d": full_result.get("adr_pct_10d"),
		"adr_meets_tl_3pct_floor": full_result.get("adr_meets_tl_3pct_floor"),
		"adr_meets_tl_5pct_floor": full_result.get("adr_meets_tl_5pct_floor"),
		"thresholds": full_result.get("thresholds"),
	}

	# Recheck view: minimal fields for recheck command
	full_result["recheck"] = {
		"grade": full_result.get("accumulation_distribution_rating"),
		"weighted_ratio_50d": full_result.get("up_down_volume_ratio_50d"),
		"recent_up_volume_evidence": full_result.get("recent_up_volume_evidence"),
		"breakout_volume_confirmation": None,
		"breakout_volume_confirmation_status": full_result.get("breakout_volume_confirmation_status"),
		"pullback_volume_declining": full_result.get("pullback_volume_declining"),
	}

	output_json(full_result)


# ---------------------------------------------------------------------------
# Demand days  (folded in from the former pocket_pivot module)
#
# A demand day is an up-day whose volume DWARFS the largest down-day volume in
# the prior window. It is the same up-dwarfs-down asymmetry the A/D grade above
# measures, but read on a single bar while price is still INSIDE the base —
# accumulation leaving a footprint before the breakout. It lives here, not in
# its own module, because it answers the identical funnel question ("is there
# demand-volume asymmetry in this base?") over the same OHLCV; a separate module
# only invites running one and skipping the other. The label "pocket pivot" is
# O'Neil/Morales vocabulary, absent from this method's source — so the public
# output speaks the method's own word, "demand day."
# ---------------------------------------------------------------------------

# Extension cutoffs vs the 10MA: beyond _EXTENDED a demand day is a chase, not a
# base entry; within _RIGHT_SIDE it sits in the constructive accumulation zone.
_EXTENDED_ABOVE_10MA_PCT = 10.0
_RIGHT_SIDE_ABOVE_10MA_PCT = 5.0

# Demand-day quality floors. THIS is where the method's per-bar surge standard
# lives: volume_ratio = up-day vol / max prior down-day vol (a pocket-pivot
# relative asymmetry). The book's "several hundred to ~1,000%" (3-10x) is the
# IDEAL surge magnitude, but it is a relationship/ceiling, not a copyable floor
# (a relationship, not a copyable digit): for liquid names the max-prior-down-day denominator never
# approaches zero, so even textbook footprints top out ~2.5-3x (observed basket
# max ~2.71). 2.0x is the deliberately conservative-but-reached "high" bar — one
# leg of a three-way AND (>=2.0 AND close in upper 70% of range AND above 50MA).
DEMAND_DAY_HIGH_VOL_RATIO = 2.0
DEMAND_DAY_MODERATE_VOL_RATIO = 1.5
DEMAND_DAY_HIGH_CLOSE_RANGE = 70.0
DEMAND_DAY_MODERATE_CLOSE_RANGE = 50.0


def _close_range_pct(close, high, low):
	"""[TL] Where the close sits in the day's range, expressed as 0-100%.

	A demand day that closes in the lower half of its range is buying that met
	immediate supply — conviction unconfirmed. Closing high is the tell the bid
	held into the close.
	"""
	value = _closing_range_percent(close, high, low)
	return 50.0 if value is None else value


def _max_down_volume(closes, volumes, idx, lookback, min_decline_pct):
	"""Largest volume among genuine down-days in the `lookback` sessions before idx.

	The bar a demand day must clear is the MAX prior down-day volume, not the
	mean: one real institutional down-day is the supply genuine demand has to
	overwhelm. A trivial down-tick (< min_decline_pct) is filtered as noise.
	"""
	start = max(1, idx - lookback)
	decline_threshold = 1.0 - min_decline_pct / 100.0
	max_down_vol = 0.0
	for i in range(start, idx):
		if closes[i] < closes[i - 1] * decline_threshold and volumes[i] > max_down_vol:
			max_down_vol = volumes[i]
	return max_down_vol


def _bigger_down_follows(closes, volumes, idx, demand_vol, lookahead, min_decline_pct):
	"""True if a down-day with volume > demand_vol occurs within `lookahead` of idx.

	The disqualifier half of the rule: demand that is immediately overwhelmed by a
	larger down-volume day was never accumulation. Reading only backward would
	stamp 'demand' on a footprint the method explicitly voids, so we look forward
	too. Near the right edge the lookahead is simply whatever bars exist.
	"""
	decline_threshold = 1.0 - min_decline_pct / 100.0
	end = min(len(closes), idx + lookahead + 1)
	for i in range(idx + 1, end):
		if closes[i] < closes[i - 1] * decline_threshold and volumes[i] > demand_vol:
			return True
	return False


def _demand_location(pct_above_50ma, pct_above_10ma, in_base):
	"""right_side (constructive) / handle (late-base) / extended (chase)."""
	if not in_base:
		return "extended"
	if pct_above_50ma >= 0 and pct_above_10ma <= _RIGHT_SIDE_ABOVE_10MA_PCT:
		return "right_side"
	return "handle"


def _grade_demand_day(volume_ratio, close_range_pct, above_50ma):
	"""high / moderate / low on vol-asymmetry x close-conviction x above-50MA."""
	if volume_ratio >= DEMAND_DAY_HIGH_VOL_RATIO and close_range_pct >= DEMAND_DAY_HIGH_CLOSE_RANGE and above_50ma:
		return "high"
	if volume_ratio >= DEMAND_DAY_MODERATE_VOL_RATIO and close_range_pct >= DEMAND_DAY_MODERATE_CLOSE_RANGE and above_50ma:
		return "moderate"
	return "low"


@safe_run
def cmd_demand_days(args):
	"""Scan for institutional demand days inside the base."""
	if args.no_cache:
		configure_cache(True)
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1d")
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 60:
		error_json(f"Insufficient data for {symbol}. Need at least 60 trading days (got {len(data)}).")

	closes = data["Close"].values.astype(float)
	highs = data["High"].values.astype(float)
	lows = data["Low"].values.astype(float)
	volumes = data["Volume"].values.astype(float)
	dates = data.index
	n = len(closes)

	sma50 = calculate_sma(data["Close"], 50).values
	sma10 = calculate_sma(data["Close"], 10).values
	current_price = round(float(closes[-1]), 2)

	lookback = args.down_vol_lookback
	min_decline = args.min_down_decline_pct
	stale_days = args.stale_days
	scan_start = max(lookback + 1, n - args.scan_days)

	demand_days = []
	disqualified = 0
	for i in range(scan_start, n):
		# Must be an up-day.
		if closes[i] <= closes[i - 1]:
			continue
		max_down_vol = _max_down_volume(closes, volumes, i, lookback, min_decline)
		# Up-volume must dwarf the largest prior down-volume.
		if max_down_vol <= 0 or volumes[i] <= max_down_vol:
			continue
		crp = _close_range_pct(closes[i], highs[i], lows[i])
		if crp < TL_CLOSING_RANGE_GATE_PCT:
			continue
		# Forward disqualifier: voided if an even-bigger down-volume day follows.
		if _bigger_down_follows(closes, volumes, i, volumes[i], lookback, min_decline):
			disqualified += 1
			continue

		volume_ratio = round(volumes[i] / max_down_vol, 2)
		s50 = sma50[i]
		s10 = sma10[i]
		above_50ma = bool(s50 == s50 and closes[i] > s50)
		pct_above_50ma = round((closes[i] - s50) / s50 * 100, 2) if s50 == s50 and s50 > 0 else 0.0
		pct_above_10ma = round((closes[i] - s10) / s10 * 100, 2) if s10 == s10 and s10 > 0 else 0.0
		in_base = pct_above_10ma <= _EXTENDED_ABOVE_10MA_PCT
		days_ago = n - 1 - i

		demand_days.append({
			"date": str(dates[i].date()),
			"days_ago": days_ago,
			"actionable": days_ago <= stale_days,
			"close": round(float(closes[i]), 2),
			"volume": int(volumes[i]),
			"max_down_vol_window": int(max_down_vol),
			"volume_ratio": volume_ratio,
			"volume_ratio_unit": "up-day vol / max down-day vol in lookback window",
			"close_range_pct": crp,
			"above_50ma": above_50ma,
			"in_base": in_base,
			"location": _demand_location(pct_above_50ma, pct_above_10ma, in_base),
			"quality": _grade_demand_day(volume_ratio, crp, above_50ma),
		})

	most_recent = None
	if demand_days:
		last = demand_days[-1]
		most_recent = {
			"date": last["date"],
			"days_ago": last["days_ago"],
			"quality": last["quality"],
			"actionable": last["actionable"],
		}
	actionable_count = sum(1 for d in demand_days if d["actionable"])

	# Current base context (NaN-guarded so a missing SMA reports null, not a crash).
	s50c = sma50[-1]
	s10c = sma10[-1]
	pct_above_10ma_now = round((current_price - s10c) / s10c * 100, 2) if s10c == s10c and s10c > 0 else None
	base_context = {
		"above_50ma": bool(s50c == s50c and current_price > s50c),
		"pct_above_50ma": round((current_price - s50c) / s50c * 100, 2) if s50c == s50c and s50c > 0 else None,
		"pct_above_10ma": pct_above_10ma_now,
		"in_base": pct_above_10ma_now is not None and pct_above_10ma_now <= _EXTENDED_ABOVE_10MA_PCT,
	}

	full_result = {
		"symbol": symbol,
		"date": str(dates[-1].date()),
		"current_price": current_price,
		"demand_days": demand_days,
		"demand_day_count": len(demand_days),
		"actionable_count": actionable_count,
		"disqualified_count": disqualified,
		"most_recent": most_recent,
		"base_context": base_context,
		"params": {
			"down_vol_lookback": lookback,
			"scan_days": args.scan_days,
			"min_down_decline_pct": min_decline,
			"stale_days": stale_days,
		},
		"thresholds": {
			"demand_day": "[M] up-day volume must visibly overwhelm prior down-volume; this implementation compares with the maximum prior down-day",
			"disqualifier": "[M] voided if a larger down-volume day follows within the lookback",
			"actionable": f"[heuristic] days_ago <= {stale_days}; older footprints are history, not a present entry",
			"quality_high": "[heuristic] vol_ratio >= 2.0 AND [TL] CR >=70% AND above 50 SMA",
			"quality_moderate": "[heuristic] vol_ratio >= 1.5 AND [TL] CR >=50% AND above 50 SMA",
			"location": "[heuristic] right_side / handle / extended (>10% above 10 SMA)",
		},
		"doctrine": (
			"[M] Institutional accumulation can't hide its footprint — it shows as "
			"outsized up-volume with a conspicuous absence of down-spikes; the "
			"ASYMMETRY, not the absolute level, distinguishes real sponsorship from a "
			"crowd bounce. A big demand day FOLLOWED by an even bigger down-volume day "
			"voids it — the supply came right back."
		),
		"provenance": _VOLUME_PROVENANCE,
	}

	full_result["compressed"] = {
		"demand_day_count": len(demand_days),
		"actionable_count": actionable_count,
		"disqualified_count": disqualified,
		"most_recent": most_recent,
		"base_context": base_context,
		"thresholds": full_result["thresholds"],
	}

	output_json(full_result)


def _session_rows(data, session_date):
	"""Select regular-session minute bars for one New York calendar date."""
	if data.index.tz is None:
		localized = data.copy()
		localized.index = localized.index.tz_localize("America/New_York")
	else:
		localized = data.tz_convert("America/New_York")
	mask = [
		index.date() == session_date
		and index.time() >= time(9, 30)
		and index.time() < time(16, 0)
		for index in localized.index
	]
	return localized.loc[mask]


@safe_run
def cmd_runrate(args):
	"""Extrapolate current cumulative volume to the full regular session."""
	# This command is deliberately cache-exempt: a cached cumulative volume would
	# turn an intraday confirmation tool into stale evidence.
	configure_cache(True)
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	state = get_market_state()

	intraday = ticker.history(
		period="5d",
		interval="1m",
		prepost=False,
		auto_adjust=False,
		actions=False,
	).dropna(subset=["Open", "High", "Low", "Close"])
	if intraday.empty:
		error_json(f"No regular-session intraday bars returned for {symbol}")

	if intraday.index.tz is None:
		latest_session_date = intraday.index[-1].date()
	else:
		latest_session_date = intraday.index[-1].tz_convert("America/New_York").date()
	rows = _session_rows(intraday, latest_session_date)
	if rows.empty:
		error_json(f"No regular-session minute bars returned for {symbol}")

	now_et = pd.Timestamp(state["now_et"])
	is_current_session = latest_session_date == now_et.date()
	if state.get("market_open") and not is_current_session:
		error_json(f"Current-session minute bars are not yet available for {symbol}")

	progress = session_progress() if is_current_session else None
	if state.get("market_open"):
		if progress is None or progress <= 0:
			error_json("Regular-session elapsed fraction is not yet available")
		elapsed_fraction = float(progress)
		session_status = "regular_open"
	else:
		# Outside regular hours the latest available regular session is complete;
		# report its realized full-day volume rather than manufacturing an intraday pace.
		elapsed_fraction = 1.0
		session_status = "completed_session"

	current_volume = float(rows["Volume"].fillna(0).sum())
	projected_volume = _project_full_session_volume(current_volume, elapsed_fraction)

	daily = ticker.history(
		period="6mo",
		interval="1d",
		auto_adjust=False,
		actions=False,
	).dropna(subset=["Open", "High", "Low", "Close"])
	if daily.index.tz is None:
		daily_dates = [index.date() for index in daily.index]
	else:
		daily_dates = [index.tz_convert("America/New_York").date() for index in daily.index]
	baseline = daily.loc[[date < latest_session_date for date in daily_dates]]
	if len(baseline) < 50:
		error_json(f"Insufficient completed daily data for {symbol}; need 50 sessions (got {len(baseline)})")

	avg_20 = float(baseline["Volume"].tail(20).mean())
	avg_50 = float(baseline["Volume"].tail(50).mean())
	open_price = float(rows["Open"].iloc[0])
	high_price = float(rows["High"].max())
	low_price = float(rows["Low"].min())
	close_price = float(rows["Close"].iloc[-1])
	closing_range_pct = _closing_range_percent(close_price, high_price, low_price)
	adr_pct_10d = _adr_percent(baseline, TL_ADR_LOOKBACK)
	regular_session_minutes = 210 if is_early_close(latest_session_date) else 390

	result = {
		"symbol": symbol,
		"session_date": latest_session_date.isoformat(),
		"as_of": rows.index[-1].isoformat(),
		"session_status": session_status,
		"is_current_session": is_current_session,
		"cache_exempt": True,
		"regular_session_minutes": regular_session_minutes,
		"regular_session_elapsed_fraction": round(elapsed_fraction, 6),
		"cumulative_volume": int(current_volume),
		"projected_full_session_volume": int(round(projected_volume)),
		"average_volume_20d": int(round(avg_20)),
		"average_volume_50d": int(round(avg_50)),
		"run_rate_20d_pct": round(projected_volume / avg_20 * 100.0, 2) if avg_20 > 0 else None,
		"run_rate_50d_pct": round(projected_volume / avg_50 * 100.0, 2) if avg_50 > 0 else None,
		"volume_bands": {
			"20d": _volume_band(projected_volume, avg_20),
			"50d": _volume_band(projected_volume, avg_50),
		},
		"intraday_bar": {
			"open": round(open_price, 4),
			"high": round(high_price, 4),
			"low": round(low_price, 4),
			"close": round(close_price, 4),
			"closing_range_pct": closing_range_pct,
			"closing_range_buyers_control": (
				closing_range_pct is not None and closing_range_pct > TL_CLOSING_RANGE_GATE_PCT
			),
		},
		"adr_pct_10d": adr_pct_10d,
		"adr_pct_10d_formula": "mean((High-Low)/Low*100) over the prior 10 completed sessions",
		"adr_meets_tl_3pct_floor": adr_pct_10d is not None and adr_pct_10d >= TL_ADR_FLOOR_LOW_PCT,
		"adr_meets_tl_5pct_floor": adr_pct_10d is not None and adr_pct_10d >= TL_ADR_FLOOR_HIGH_PCT,
		"thresholds": {
			"run_rate": "[M] projected volume should exceed the stock's own 50d average; +50% is the strict variant",
			"volume_band": "[TL] 20d/50d average volume ±25%",
			"closing_range": "[TL] CR=(Close-Low)/(High-Low)*100; >50% means buyers won the bar",
			"adr_pct": "[TL] approximate 3-5% growth/momentum floor range; not a SEPA hard gate",
		},
		"doctrine": (
			"[M] Intraday cumulative volume is extrapolated by the fraction of the regular "
			"session elapsed so price can trigger the entry while volume confirms without "
			"waiting for the close. [TL] Run rate, CR, volume bands, and ADR% describe "
			"participation and bar character; they never replace the setup or risk gates."
		),
		"provenance": _VOLUME_PROVENANCE,
	}
	output_json(result)


def main():
	parser = JsonArgumentParser(description="Price/volume evidence and execution diagnostics")
	sub = parser.add_subparsers(dest="command", required=True)

	def add_no_cache(subparser):
		subparser.add_argument(
			"--no-cache",
			action="store_true",
			help="Bypass cache reads and writes for this command",
		)

	sp = sub.add_parser("analyze", help="Full volume analysis")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--period", default="6mo", help="Data period (default: 6mo)")
	sp.add_argument("--lookback", type=int, default=ACCDIST_LOOKBACK,
					help="primary up/down-volume ratio window (default %d). The institutional "
						 "supply/demand window scales with how much base history is relevant — "
						 "widen for a long base, tighten to read only the most recent leg."
						 % ACCDIST_LOOKBACK)
	sp.add_argument("--short-lookback", type=int, default=SHORT_LOOKBACK,
					help="secondary short-ratio window (default %d). Recent-pressure horizon; "
						 "shorten to catch a fresh shift, lengthen to smooth noise." % SHORT_LOOKBACK)
	sp.add_argument("--up-volume-window", type=int, default=UP_VOLUME_WINDOW,
					help="recent days scanned for [MM-Ryan] elevated up-volume evidence (default %d); "
							 "this observation does not establish a pivot breakout." % UP_VOLUME_WINDOW)
	sp.add_argument("--pullback-window", type=int, default=PULLBACK_WINDOW,
					help="pullback analysis lookback (default %d). Match to how long the pullback "
						 "being assessed has run." % PULLBACK_WINDOW)
	add_no_cache(sp)
	sp.set_defaults(func=cmd_analyze)

	sp = sub.add_parser("demand-days", help="Scan for institutional demand days inside the base")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--period", default="1y", help="Data period (default: 1y)")
	sp.add_argument("--down-vol-lookback", type=int, default=10,
					help="sessions of prior down-days the demand day must dwarf (default 10). "
						 "A tight 5-week handle and a 26-week base warrant different horizons.")
	sp.add_argument("--scan-days", type=int, default=60,
					help="how far back to surface demand days (default 60). Scales with base length.")
	sp.add_argument("--min-down-decline-pct", type=float, default=0.3,
					help="min %% decline for a day to count as a genuine down-day (default 0.3). "
						 "The noise floor scales with the stock's own volatility.")
	sp.add_argument("--stale-days", type=int, default=15,
					help="demand days older than this are flagged not-actionable (default 15)")
	add_no_cache(sp)
	sp.set_defaults(func=cmd_demand_days)

	sp = sub.add_parser(
		"runrate",
		help="Cache-exempt current regular-session volume extrapolation",
	)
	sp.add_argument("symbol", help="Ticker symbol")
	add_no_cache(sp)
	sp.set_defaults(func=cmd_runrate)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
