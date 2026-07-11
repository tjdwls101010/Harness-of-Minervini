#!/usr/bin/env python3
"""Stage analysis — where in the four-stage lifecycle a stock sits, decided
structurally, not scored.

A stock is in exactly ONE of Weinstein's four stages at a time, and which one is
a question of structure, not degree: price's position relative to a 200-day MA,
and whether that MA is actually turning up. So this module does NOT compute a
0-100 "stage score" and take an argmax. It used to, and that was a bug of the
same family the pipeline already killed: a weighted point-blend invents a
continuum where the reality is a switch. The old version handed Ford a higher
"Stage 2 advancing" number (60) than NVDA (35) and flipped Intel into a buyable
Stage 2 on a one-bucket plurality — because unanchored point-weights, summed and
argmax'd, drift toward whatever factor the stock happens to have, not toward the
lifecycle truth. A boolean cascade can't drift: it asks the structural questions
in the order that resolves the lifecycle, and the first matching signature wins.

The signatures, straight from the method (book Ch. 5; the Trend-Template
climax lines):

- Stage 4 (Declining): price BELOW a 200-day MA that is itself in a definite
  downtrend. Checked first — a broken stock must never be mistaken for a base.
- Stage 2 (Advancing): price ABOVE a 200-day MA that is RISING (same 1-month test
  trend_template.py uses for its criterion 3, so stage and gate cannot disagree
  on "rising"), with the trend confirmed by a bullish MA stack OR an intact
  higher-high/higher-low structure. The only buyable stage.
- Stage 3 (Topping): still above the 200-day MA, but it has stopped rising (or the
  stack has rolled) AND the uptrend structure is gone — price whipsawing across a
  flattening MA after an advance.
- Stage 1 (Basing): the residual. Below a non-declining MA, or oscillating near a
  flat one. Not actionable; the safe default when nothing else matches.

The classifier decides the lifecycle phase ONLY. It is deliberately NOT a quality
filter — a sleepy value name can be structurally in a Stage-2 uptrend. That is
correct and not a contradiction: the qualify gate ANDs this with the full Trend
Template (RS >=70, >=30% off the low, within 25% of the high), and THAT is where
quality-poor uptrends are rejected. Asking the stage classifier to also judge
quality is how you get the old score's incoherence back.

Commands:
    classify     Deterministic Stage 1-4 + the structural reads that decided it.
    transitions  Stage 1 -> Stage 2 early-turn signals.
    risk         Diagnostic sell-tells for a name already in an advance
                 (largest daily/weekly loss since Stage 2 began, climax extension,
                 tennis-ball vs egg character). Key reversal is not duplicated
                 here: it is a [TL] practice-layer checklist owned by
                 sell_signals reversal, outside canonical SEPA stage analysis.

Args:
    symbol (str): Ticker (e.g. "AAPL", "NVDA").
    --period (str): History to pull (default "2y").
    --swing-bars (int): N-bar confirmation for swing-point detection (default 5).
        Flexible: a 7-week power-play and an 18-month cup swing on different
        scales, so this is yours to widen for longer bases.
    --ma-uptrend-days (int): Lookback for the "200-day MA rising" test
        (default 22 = ~1 month, matching trend_template). The method prefers
        4-5 months of rise; widen to demand a longer-confirmed turn.

Returns (classify):
    {"symbol", "date", "current_price", "stage", "stage_name",
     "structural_reads": {price_vs_200ma, sma200_trend, ma_stack, trend_structure,
                          pct_above_52w_low, pct_below_52w_high}}
    No "scores", no "max_scores" — the stage is the structure, read it directly.

See Also:
    - trend_template.py: the 8-criteria gate; Stage 2 is its lifecycle twin.
    - rs_ranking.py: relative strength — the scarcity the stack can't show.
    - volume_analysis.py: accumulation/distribution footprint behind the structure.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import yfinance as yf
from utils import cache_disabled, calculate_sma, configure_cache, error_json, output_json, safe_run


class JsonArgumentParser(argparse.ArgumentParser):
	"""Keep usage failures on the same JSON/exit-1 contract as runtime failures."""

	def error(self, message):
		error_json(message)

STAGE_NAMES = {
	1: "Basing / Neglect (Consolidation)",
	2: "Advancing (Accumulation)",
	3: "Topping (Distribution)",
	4: "Declining (Capitulation)",
}

# --- Diagnostic windows & conviction floors (transitions / risk) -----------
# These drive the early-turn and sell-tell DIAGNOSTICS, never the classify gate
# path (that path is fully governed by --ma-uptrend-days and --swing-bars; the
# 50/150/200 MA periods and the 252-day year are definitional, not tunable).
# They are named here, with their reason, rather than buried as bare literals so
# the number — and why it is what it is — is visible where a reader would
# question it. The conviction multipliers encode what a signal MEANS (what counts
# as ranges "widening", volatility "expanding"), which is canonical to the method
# and constant across stocks; the lookbacks are short diagnostic windows that
# rarely need per-run tuning. The one number an analyst genuinely re-defines per
# stock — how long an advance must run before a parabolic move reads as a climax —
# is a CLI arg (--min-advance-weeks) below.
_ADR_FAST = 5                   # Implementation window for the [TL] ADR% diagnostic.
_ADR_SLOW = 60                  # Implementation baseline for the [TL] ADR% diagnostic.
_RANGE_EXPANSION_MULT = 1.3     # Implementation heuristic for widening ranges, not canon.
_ATR_RECENT = 15                # recent volatility window (tennis-ball vs egg)
_ATR_BASE = 60                  # baseline volatility window
_ATR_EXPANSION_MULT = 1.15      # Implementation character proxy, not canon.
_RECENT_HIGH_WINDOW = 40        # window defining "the recent high" price must snap back to
_NEAR_HIGH_BAND = 0.95          # Implementation character proxy, not canon.
_DEFAULT_MIN_ADVANCE_WEEKS = 8  # Flex heuristic: the maps define a long advance but no numeric floor.
_DEFAULT_CLIMAX_EXTENSION_PCT = 25.0  # Flex heuristic: the maps do not define a % above the 50 SMA.


def _ma_slope(series, lookback=20):
	"""Normalized slope (percent per day) of a moving average over `lookback`."""
	if len(series) < lookback:
		return 0.0
	recent = series.dropna().tail(lookback)
	if len(recent) < 2:
		return 0.0
	x = np.arange(len(recent))
	y = recent.values.astype(float)
	slope = np.polyfit(x, y, 1)[0]
	mean_val = np.mean(y)
	if mean_val == 0:
		return 0.0
	return (slope / mean_val) * 100


def _sma200_trend_pct(sma200, lookback_days):
	"""Percent change of the 200-day MA over `lookback_days` (the rising test).

	Returns the percent change of SMA200 now vs `lookback_days` ago. Positive ==
	rising (== trend_template criterion 3). Falls back to the earliest available
	SMA200 value when history is short, mirroring trend_template.
	"""
	s = sma200.dropna()
	if len(s) < 2:
		return 0.0
	now = float(s.iloc[-1])
	ago = float(s.iloc[-1 - lookback_days]) if len(s) > lookback_days else float(s.iloc[0])
	if ago == 0:
		return 0.0
	return (now / ago - 1) * 100


def _find_swing_points(series, confirmation_bars=5):
	"""Swing highs/lows by N-bar confirmation.

	A swing high is a local max with `confirmation_bars` lower bars on each side
	(swing low symmetric). Returns (swing_highs, swing_lows) as lists of
	(index, value), chronological.
	"""
	values = series.values.astype(float)
	n = len(values)
	swing_highs = []
	swing_lows = []

	for i in range(confirmation_bars, n - confirmation_bars):
		is_high = True
		for j in range(1, confirmation_bars + 1):
			if values[i] < values[i - j] or values[i] < values[i + j]:
				is_high = False
				break
		if is_high:
			swing_highs.append((i, float(values[i])))

		is_low = True
		for j in range(1, confirmation_bars + 1):
			if values[i] > values[i - j] or values[i] > values[i + j]:
				is_low = False
				break
		if is_low:
			swing_lows.append((i, float(values[i])))

	return swing_highs, swing_lows


def _trend_structure(highs, lows, confirmation_bars=5):
	"""Read the swing structure into four booleans.

	HH/HL = last two swing highs/lows ascending (uptrend intact).
	LH/LL = last two descending (downtrend). Needs enough bars to find two of
	each; returns all-False when it can't (structure unknown, not absent).
	"""
	min_bars = confirmation_bars * 2 * 3  # room for >=2 confirmed swings each side
	if len(highs) < min_bars:
		return False, False, False, False

	swing_highs, _ = _find_swing_points(highs, confirmation_bars)
	_, swing_lows = _find_swing_points(lows, confirmation_bars)

	hh = lh = hl = ll = False
	if len(swing_highs) >= 2:
		a, b = swing_highs[-2][1], swing_highs[-1][1]
		hh = b > a
		lh = b < a
	if len(swing_lows) >= 2:
		a, b = swing_lows[-2][1], swing_lows[-1][1]
		hl = b > a
		ll = b < a
	return hh, hl, lh, ll


def _stage2_segment(closes, sma200):
	"""Return prices after the first observable 200-SMA reclaim.

	A confirmed Stage-2 start is an 8-of-8 gate event that this module cannot
	reconstruct. The first close above an available 200 SMA is therefore an
	explicitly labelled approximation, never a fabricated confirmed gate date.
	"""
	valid = closes.notna() & sma200.notna()
	above = valid & (closes > sma200)
	reclaims = above.astype(int).diff()
	reclaims = reclaims[reclaims == 1]
	if not reclaims.empty:
		start = reclaims.index[0]
		basis = "first_observable_200sma_reclaim"
	else:
		valid_indices = closes.index[valid]
		start = valid_indices[0] if len(valid_indices) else closes.index[0]
		basis = "first_available_bar_no_reclaim_observed"
	return closes.loc[start:], start, basis


def _completed_weekly_closes(data):
	"""Aggregate daily data into completed Friday-labelled weeks only."""
	weekly = data.resample("W-FRI").agg({"Close": "last", "Volume": "sum"}).dropna(subset=["Close"])
	if not weekly.empty and weekly.index[-1].date() > data.index[-1].date():
		weekly = weekly.iloc[:-1]
	return weekly


def _worst_return(series):
	"""Return the worst close-to-close percentage change and its date."""
	returns = series.pct_change().dropna() * 100
	if returns.empty:
		return {"pct": None, "date": None, "latest_pct": None, "latest_is_record": False}
	latest_pct = float(returns.iloc[-1])
	declines = returns[returns < 0]
	if declines.empty:
		return {"pct": None, "date": None, "latest_pct": round(latest_pct, 2), "latest_is_record": False}
	worst_date = declines.idxmin()
	worst_pct = float(declines.loc[worst_date])
	return {
		"pct": round(worst_pct, 2),
		"date": str(worst_date.date()),
		"latest_pct": round(latest_pct, 2),
		"latest_is_record": bool(worst_pct < 0 and np.isclose(latest_pct, worst_pct)),
	}


def _largest_decline_since_stage2(data, sma200):
	"""Measure the map's largest daily/weekly loss since the Stage-2 proxy start.

	Peak-to-trough drawdown remains separately labelled context. It must not
	replace the source-defined one-session/one-completed-week signal.
	"""
	segment, start, start_basis = _stage2_segment(data["Close"], sma200)
	segment_data = data.loc[segment.index]
	daily = _worst_return(segment)
	weekly_frame = _completed_weekly_closes(segment_data)
	weekly_series = weekly_frame["Close"] if not weekly_frame.empty else segment.iloc[0:0]
	weekly = _worst_return(weekly_series)

	running_max = segment.cummax()
	drawdowns = (segment / running_max - 1) * 100
	peak_to_trough = float(drawdowns.min()) if not drawdowns.empty else 0.0
	trough_date = drawdowns.idxmin() if not drawdowns.empty else None

	available = [("daily", daily["pct"]), ("weekly", weekly["pct"])]
	available = [(timeframe, pct) for timeframe, pct in available if pct is not None]
	worst_timeframe, worst_pct = min(available, key=lambda item: item[1]) if available else (None, None)
	return {
		"pct": worst_pct,
		"timeframe": worst_timeframe,
		"daily": daily,
		"weekly": weekly,
		"latest_is_new_record_decline": bool(daily["latest_is_record"] or weekly["latest_is_record"]),
		"stage2_start_approx": str(start.date()),
		"stage2_start_basis": start_basis,
		"peak_to_trough_context": {
			"pct": round(peak_to_trough, 2),
			"trough_date": str(trough_date.date()) if trough_date is not None else None,
			"status": "context_only_not_the_[M]_daily_or_weekly_max-decline_signal",
		},
		"provenance": "[M] largest daily or completed-week decline since the Stage-2 advance began",
	}


def _atr(highs, lows, closes, window):
	"""Average true range over the last `window` bars."""
	tr = np.maximum(
		highs.values - lows.values,
		np.maximum(
			np.abs(highs.values - np.roll(closes.values, 1)),
			np.abs(lows.values - np.roll(closes.values, 1)),
		),
	)
	if len(tr) < window:
		return float(np.mean(tr[1:])) if len(tr) > 1 else 0.0
	return float(np.mean(tr[-window:]))


# ---------------------------------------------------------------------------
# The classifier — a boolean cascade, no points
# ---------------------------------------------------------------------------

def _classify_stage(price, s50, s150, s200, sma200_trend_pct, hh, hl, lh, ll):
	"""Place the lifecycle stage by structural signature, first match wins.

	Order is the point: Stage 4 (the broken case) is ruled out first so it can
	never be mistaken for a base; Stage 2 (the only buyable case) is then the
	clean above-a-rising-MA structure; Stage 3 is what's left above the MA once
	the rise has stalled; Stage 1 absorbs the rest.
	"""
	above_200 = price > s200
	s200_rising = sma200_trend_pct > 0       # == trend_template criterion 3
	s200_declining = sma200_trend_pct < 0
	bull_stack = s50 > s150 > s200
	bear_stack = s50 < s150
	uptrend_structure = hh and hl

	# Stage 4 — price below a definitively declining 200-day MA.
	if (not above_200) and s200_declining:
		return 4
	# Stage 2 — above a rising 200-day MA, trend confirmed by the stack or by an
	# intact higher-high/higher-low structure.
	if above_200 and s200_rising and (bull_stack or uptrend_structure):
		return 2
	# Stage 3 — still above the MA, but the rise has stalled (or the stack rolled)
	# and the uptrend structure is gone: distribution after an advance.
	if above_200 and (not s200_rising or bear_stack) and (not uptrend_structure):
		return 3
	# Stage 1 — basing / neglect / unconfirmed. The safe residual.
	return 1


@safe_run
def cmd_classify(args):
	"""Classify a stock into Stage 1-4 by structure."""
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1d")
	# Drop incomplete bars: yfinance appends a partial current-session row mid-day
	# whose OHLC can be NaN, which would poison every downstream comparison.
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 200:
		error_json(f"Insufficient data for {symbol}. Need at least 200 trading days (received {len(data)}).")

	closes = data["Close"]
	highs = data["High"]
	lows = data["Low"]
	current_price = float(closes.iloc[-1])
	date_str = str(data.index[-1].date())

	sma50 = calculate_sma(closes, 50)
	sma150 = calculate_sma(closes, 150)
	sma200 = calculate_sma(closes, 200)
	c_sma50 = float(sma50.iloc[-1])
	c_sma150 = float(sma150.iloc[-1])
	c_sma200 = float(sma200.iloc[-1])

	sma200_trend_pct = _sma200_trend_pct(sma200, args.ma_uptrend_days)
	hh, hl, lh, ll = _trend_structure(highs, lows, args.swing_bars)

	week52_low = float(lows.tail(252).min()) if len(lows) >= 252 else float(lows.min())
	week52_high = float(highs.tail(252).max()) if len(highs) >= 252 else float(highs.max())
	pct_above_52w_low = (current_price / week52_low - 1) * 100 if week52_low > 0 else 0.0
	pct_below_52w_high = (current_price / week52_high - 1) * 100 if week52_high > 0 else 0.0

	stage = _classify_stage(
		current_price, c_sma50, c_sma150, c_sma200, sma200_trend_pct, hh, hl, lh, ll
	)

	if sma200_trend_pct > 0:
		trend_label = "rising"
	elif sma200_trend_pct < 0:
		trend_label = "declining"
	else:
		trend_label = "flat"

	if c_sma50 > c_sma150 > c_sma200:
		stack_label = "bullish (50>150>200)"
	elif c_sma50 < c_sma150:
		stack_label = "bearish (50<150)"
	else:
		stack_label = "mixed"

	output_json({
		"symbol": symbol,
		"date": date_str,
		"current_price": round(current_price, 2),
		"stage": stage,
		"stage_name": STAGE_NAMES[stage],
		"structural_reads": {
			"price_vs_200ma": "above" if current_price > c_sma200 else "below",
			"sma200_trend": {
				"label": trend_label,
				"pct_change": round(sma200_trend_pct, 2),
				"lookback_days": args.ma_uptrend_days,
			},
			"ma_stack": stack_label,
			"trend_structure": {
				"higher_highs": hh, "higher_lows": hl,
				"lower_highs": lh, "lower_lows": ll,
				"swing_bars": args.swing_bars,
			},
			"pct_above_52w_low": round(pct_above_52w_low, 1),
			"pct_below_52w_high": round(pct_below_52w_high, 1),
		},
		"doctrine": (
			"[M] A stock is in exactly ONE stage at a time — a question of structure, not degree. "
			"The classification is a boolean cascade, not a weighted score, precisely because a "
			"point-blend would invent a continuum where the reality is a switch, and would let a "
			"strong factor paper over a disqualifying one. Read the stage as a gate, not a grade."
		),
	})


@safe_run
def cmd_transitions(args):
	"""Detect Stage 1 -> Stage 2 early-turn signals.

	[M] Emits the six canonical transition checks from the knowledge map. It does not score partial evidence into a synthetic verdict; the 8-of-8 Trend Template remains the separate eligibility gate.
	"""
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1d")
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 200:
		error_json(f"Insufficient data for {symbol}. Need at least 200 trading days (received {len(data)}).")

	closes = data["Close"]
	highs = data["High"]
	lows = data["Low"]
	volumes = data["Volume"]
	current_price = float(closes.iloc[-1])

	sma50 = calculate_sma(closes, 50)
	sma150 = calculate_sma(closes, 150)
	sma200 = calculate_sma(closes, 200)
	c_sma150 = float(sma150.iloc[-1])
	c_sma200 = float(sma200.iloc[-1])
	sma200_trend_pct = _sma200_trend_pct(sma200, args.ma_uptrend_days)

	signals = []

	# [M] 1. Price above both the 150-day and 200-day moving averages.
	price_above_long_mas = current_price > c_sma150 and current_price > c_sma200
	signals.append({
		"signal": "Price above 150-day and 200-day MAs",
		"detected": price_above_long_mas,
		"detail": f"price={current_price:.2f}, SMA150={c_sma150:.2f}, SMA200={c_sma200:.2f}",
		"provenance": "[M]",
	})

	# [M] 2. The 150-day MA is above the 200-day MA.
	signals.append({
		"signal": "150-day MA above 200-day MA",
		"detected": c_sma150 > c_sma200,
		"detail": f"SMA150={c_sma150:.2f}, SMA200={c_sma200:.2f}",
		"provenance": "[M]",
	})

	# [M] 3. The 200-day MA has turned upward over the canonical one-month default.
	signals.append({
		"signal": "200-day MA turning upward",
		"detected": sma200_trend_pct > 0,
		"detail": f"SMA200 {args.ma_uptrend_days}d change: {sma200_trend_pct:+.2f}%",
		"provenance": "[M]",
	})

	# [M] 4. Higher highs and higher lows are forming.
	hh, hl, _, _ = _trend_structure(highs, lows, args.swing_bars)
	signals.append({
		"signal": "Higher highs and higher lows forming",
		"detected": hh and hl,
		"detail": f"HH: {hh}, HL: {hl}",
		"provenance": "[M]",
	})

	# [M] 5-6. Read completed weekly demand/supply directly; daily noise and
	# a partial current week must not substitute for the canonical evidence.
	weekly = _completed_weekly_closes(data).tail(10)
	weekly_returns = weekly["Close"].pct_change()
	up_weeks = weekly.loc[weekly_returns > 0, "Volume"]
	down_weeks = weekly.loc[weekly_returns < 0, "Volume"]
	volume_comparison_available = not up_weeks.empty and not down_weeks.empty
	up_volume_dominates = bool(up_weeks.mean() > down_weeks.mean()) if volume_comparison_available else None
	signals.append({
		"signal": "Higher-volume up weeks than pullback weeks",
		"detected": up_volume_dominates,
		"detail": f"mean up-week volume={up_weeks.mean():.0f}, mean down-week volume={down_weeks.mean():.0f}" if volume_comparison_available else "unavailable: need both an up week and a down week",
		"provenance": "[M]",
	})

	weekly_volume_median = float(weekly["Volume"].median()) if not weekly.empty else 0.0
	high_volume_up_count = int(((weekly_returns > 0) & (weekly["Volume"] >= weekly_volume_median)).sum())
	high_volume_down_count = int(((weekly_returns < 0) & (weekly["Volume"] >= weekly_volume_median)).sum())
	signals.append({
		"signal": "More high-volume up weeks than down weeks",
		"detected": high_volume_up_count > high_volume_down_count,
		"detail": f"high-volume up weeks={high_volume_up_count}, down weeks={high_volume_down_count}; median-volume reference={weekly_volume_median:.0f}",
		"provenance": "[M]",
	})

	detected = sum(1 for s in signals if s["detected"] is True)
	output_json({
		"symbol": symbol,
		"date": str(data.index[-1].date()),
		"current_price": round(current_price, 2),
		"transition_type": "Stage 1 -> Stage 2",
		"signals": signals,
		"detected_count": detected,
		"total_signals": len(signals),
		"canonical_checklist_complete": all(s["detected"] is True for s in signals),
		"doctrine": (
			"[M] A Stage 1-to-2 transition is structural evidence, not permission to buy. "
			"The full Trend Template remains a separate 8-of-8 hard gate, because a partial turn can still be an unqualified base."
		),
	})


def compute_risk_snapshot(
	data,
	*,
	climax_extension_pct=_DEFAULT_CLIMAX_EXTENSION_PCT,
	min_advance_weeks=_DEFAULT_MIN_ADVANCE_WEEKS,
):
	"""Compute the risk quantities owned by stage analysis from daily OHLCV.

	This pure helper is the single implementation owner for the Stage-2
	max-decline and climax-extension quantities. ``sell_signals`` imports it
	instead of reimplementing either measure.
	"""
	required = {"Open", "High", "Low", "Close", "Volume"}
	missing = sorted(required.difference(getattr(data, "columns", [])))
	if missing:
		raise ValueError(f"History is missing required columns: {', '.join(missing)}")
	data = data.dropna(subset=["Open", "High", "Low", "Close"]).copy()
	if len(data) < 200:
		raise ValueError(f"Insufficient history: need at least 200 daily bars, received {len(data)}")
	if climax_extension_pct < 0:
		raise ValueError("climax_extension_pct must be non-negative")
	if min_advance_weeks < 1:
		raise ValueError("min_advance_weeks must be at least 1")

	closes = data["Close"]
	highs = data["High"]
	lows = data["Low"]
	current_price = float(closes.iloc[-1])
	sma50 = calculate_sma(closes, 50)
	sma200 = calculate_sma(closes, 200)
	c_sma50 = float(sma50.iloc[-1])

	# [M] Record daily/weekly loss since the observable Stage-2 proxy start.
	largest_decline = _largest_decline_since_stage2(data, sma200)

	# [M] Climax concept, measured with explicitly heuristic magnitude/windows.
	extension_pct = (current_price / c_sma50 - 1) * 100 if c_sma50 > 0 else 0.0
	adr = ((highs - lows) / closes * 100).astype(float)
	adr_5d = float(adr.iloc[-_ADR_FAST:].mean())
	adr_60d = float(adr.iloc[-_ADR_SLOW:].mean()) if len(adr) >= _ADR_SLOW else adr_5d
	range_expanding = adr_5d > _RANGE_EXPANSION_MULT * adr_60d if adr_60d > 0 else False
	days_since_50ma = 0
	for i in range(len(closes) - 1, -1, -1):
		if np.isnan(float(sma50.iloc[i])) or float(closes.iloc[i]) <= float(sma50.iloc[i]):
			break
		days_since_50ma += 1
	weeks_of_advance = days_since_50ma // 5
	climactic = (
		extension_pct > climax_extension_pct
		and range_expanding
		and weeks_of_advance >= min_advance_weeks
	)

	# [M] Tennis-ball/egg character, with all numeric cutoffs labelled proxy.
	atr_recent = _atr(highs, lows, closes, _ATR_RECENT)
	atr_base = _atr(highs, lows, closes, _ATR_BASE)
	vol_expanding = atr_recent > atr_base * _ATR_EXPANSION_MULT if atr_base > 0 else False
	recent_high = float(highs.tail(_RECENT_HIGH_WINDOW).max())
	near_recent_high = current_price >= recent_high * _NEAR_HIGH_BAND
	if near_recent_high and not vol_expanding:
		character = "tennis_ball"
	elif vol_expanding and not near_recent_high:
		character = "egg"
	else:
		character = "mixed"

	return {
		"current_price": round(current_price, 2),
		"largest_decline_since_stage2": largest_decline,
		"climax_extension": {
			"pct_above_50ma": round(extension_pct, 1),
			"range_expanding": bool(range_expanding),
			"weeks_of_advance": weeks_of_advance,
			"heuristic_climactic": bool(climactic),
			"threshold_pct": climax_extension_pct,
			"min_advance_weeks": min_advance_weeks,
			"status": "[M] concept measured with flex implementation heuristics; not a canonical sell threshold",
		},
		"adr_pct": {
			"recent_5d": round(adr_5d, 2),
			"baseline_60d": round(adr_60d, 2),
			"formula": "mean((High - Low) / Close * 100) over the stated window",
			"provenance": "[TL] diagnostic quantifier; the 3-5% screen context is not an eligibility gate here",
		},
		"character": {
			"read": character,
			"volatility_expanding": bool(vol_expanding),
			"near_recent_high": bool(near_recent_high),
			"note": "implementation proxy: chart-confirm recovery speed and volume; no deterministic sell verdict",
		},
	}


@safe_run
def cmd_risk(args):
	"""Diagnostic sell-tells for a name already in an advance.

	Reads the three Minervini lifecycle-risk diagnostics owned by this command.
	It does not duplicate the [TL] key-reversal checklist, which belongs to
	``sell_signals reversal`` as a tunable practice-layer instrument outside
	canonical SEPA stage analysis. Diagnostic only: no stop, no size, no verdict.

	1. Largest daily or completed-week decline since Stage 2 began — the
	   source-defined headline tell. Peak-to-trough drawdown is context only.
	2. Climax extension — price stretched far above the 50-day MA with ranges
	   expanding after a long advance: a parabolic move ENDS a trend.
	3. Tennis ball vs egg — healthy pullbacks snap back to new highs with volume
	   contracting on the dip and expanding on the recovery; widening two-way
	   swings are an egg, not a ball.
	"""
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1d")
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 200:
		error_json(f"Insufficient data for {symbol}. Need at least 200 trading days (received {len(data)}).")

	snapshot = compute_risk_snapshot(
		data,
		climax_extension_pct=args.climax_extension_pct,
		min_advance_weeks=args.min_advance_weeks,
	)

	output_json({
		"symbol": symbol,
		"date": str(data.index[-1].date()),
		**snapshot,
		"interpretation": "diagnostic only — no stop, no size, no verdict",
		"ownership": {
			"owned_here": ["largest_decline_since_stage2", "climax_extension"],
			"key_reversal": "[TL] sell_signals reversal; practice layer, not SEPA canon",
		},
		"provenance": {
			"largest_decline_since_stage2": "[M] largest daily or completed-week loss; Stage-2 start is approximated by the first 200-SMA reclaim in the requested history, not a confirmed 8-of-8 gate date",
			"climax_extension": "[M] climax concept; 25% extension, 8 weeks, and range-expansion parameters are implementation heuristics",
			"character": "implementation proxy for the [M] tennis-ball/egg read; corroborate recovery and volume on the chart",
		},
		"doctrine": (
			"[M] These are lifecycle character reads, not stops or position-size instructions. The largest decline since the Stage-2 advance began matters because abnormal weakness can reveal institutional exit before public fundamentals explain it; respect that price evidence even after apparently good news. Climax and character fields are diagnostics whose heuristic thresholds require chart corroboration."
		),
	})


def main():
	parser = JsonArgumentParser(description="Stage analysis (Weinstein/Minervini Stage 1-4)")
	sub = parser.add_subparsers(dest="command", required=True)

	def add_common(sp):
		sp.add_argument("symbol", help="Ticker symbol")
		sp.add_argument("--period", default="2y", help="Data period (default: 2y)")
		sp.add_argument("--swing-bars", type=int, default=5, dest="swing_bars",
						help="N-bar swing confirmation (default 5; widen for longer bases)")
		sp.add_argument("--ma-uptrend-days", type=int, default=22, dest="ma_uptrend_days",
						help="Lookback for the 200-day MA rising test (default 22 = ~1mo)")
		sp.add_argument("--no-cache", action="store_true", help="Bypass the shared read-through cache for this command")

	sp = sub.add_parser("classify", help="Classify stock into Stage 1-4 (structural, no score)")
	add_common(sp)
	sp.set_defaults(func=cmd_classify)

	sp = sub.add_parser("transitions", help="Detect Stage 1->2 early-turn signals")
	add_common(sp)
	sp.set_defaults(func=cmd_transitions)

	sp = sub.add_parser("risk", help="Diagnostic sell-tells (decline-since-S2, climax, character)")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--period", default="2y", help="Data period (default: 2y)")
	sp.add_argument("--climax-extension-pct", type=float, default=_DEFAULT_CLIMAX_EXTENSION_PCT, dest="climax_extension_pct",
					help="Flex heuristic: extension above 50-day MA (default 25%%); [M] defines climax but no canonical percentage")
	sp.add_argument("--min-advance-weeks", type=int, default=_DEFAULT_MIN_ADVANCE_WEEKS,
					dest="min_advance_weeks",
					help="Flex heuristic: weeks of advance before a stretched move reads as climax (default 8); the maps define no numeric floor")
	sp.add_argument("--no-cache", action="store_true", help="Bypass the shared read-through cache for this command")
	sp.set_defaults(func=cmd_risk)

	args = parser.parse_args()
	if args.command in {"classify", "transitions"}:
		if args.swing_bars < 1:
			error_json("--swing-bars must be at least 1")
		if args.ma_uptrend_days < 1:
			error_json("--ma-uptrend-days must be at least 1")
	if args.command == "risk":
		if args.climax_extension_pct < 0:
			error_json("--climax-extension-pct must be non-negative")
		if args.min_advance_weeks < 1:
			error_json("--min-advance-weeks must be at least 1")
	configure_cache(args.no_cache or cache_disabled())
	args.func(args)


if __name__ == "__main__":
	main()
