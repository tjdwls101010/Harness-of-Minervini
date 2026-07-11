#!/usr/bin/env python3
"""Tight Closes detection for Minervini SEPA methodology.

Detects heuristic clusters of consecutive trading days/weeks whose closing prices fall within a narrow range. The cluster itself has no canonical Minervini or TraderLion threshold; it is corroborative context that must remain subordinate to confirmed Stage 2, complete VCP structure, and breakout evidence.

Commands:
	daily: Detect tight closes on daily data
	weekly: Detect tight closes on weekly data

Args:
	symbol (str): Ticker symbol (e.g., "AAPL", "NVDA", "META")
	--period (str): Historical data period (default: "6mo" for daily, "1y" for weekly)
	--tolerance (float): Close range tolerance percentage (default: 1.0 for daily, 1.5 for weekly)
	--no-cache: Bypass the shared read-through cache for this invocation

Returns:
	dict: {
		"symbol": str,
		"date": str,
		"current_price": float,
		"interval": str,
		"tight_close_clusters": [
			{
				"start_date": str,
				"end_date": str,
				"duration_bars": int,
				"duration_unit": str,
				"min_close": float,
				"max_close": float,
				"spread_pct": float,
				"avg_close": float,
				"volume_trend": str,
				"volume_dryup_ratio": float,
				"location": str,
				"quality": str
			}
		],
		"cluster_count": int,
		"best_cluster": {
			"start_date": str,
			"end_date": str,
			"spread_pct": float,
			"quality": str
		},
		"signal_strength": str
	}

Example:
	>>> python tight_closes.py daily NVDA --period 6mo
	{
		"symbol": "NVDA",
		"date": "2025-12-01",
		"current_price": 142.30,
		"interval": "daily",
		"tight_close_clusters": [
			{
				"start_date": "2025-11-10",
				"end_date": "2025-11-18",
				"duration_bars": 7,
				"duration_unit": "trading_days",
				"min_close": 139.50,
				"max_close": 140.80,
				"spread_pct": 0.93,
				"avg_close": 140.15,
				"volume_trend": "declining",
				"volume_dryup_ratio": 0.62,
				"location": "pivot_area",
				"quality": "high"
			}
		],
		"cluster_count": 1,
		"best_cluster": {
			"start_date": "2025-11-10",
			"end_date": "2025-11-18",
			"spread_pct": 0.93,
			"quality": "high"
		},
		"signal_strength": "strong"
	}

	>>> python tight_closes.py weekly NVDA --period 1y
	{
		"symbol": "NVDA",
		"interval": "weekly",
		"tight_close_clusters": [...],
		"signal_strength": "strong"
	}

Use Cases:
	- Surface close-dispersion candidates for corroboration
	- Add price/volume context to a separately validated VCP
	- Compare low-volume tightness without claiming institutional accumulation from one signal
	- Compare daily vs weekly tight close signals for confluence

Notes:
	- Tight-close clusters are implementation heuristics; only the combined price/volume structure can support a supply-absorption interpretation
	- Sliding-window sizes and close-spread tolerances are implementation heuristics, not canonical doctrine
	- Overlapping clusters are merged, keeping the tightest spread (duration as tiebreaker)
	- [M] Final contraction volume below its 50-day average, including one or two exceptionally quiet days, is corroboration of supply exhaustion
	- [TL] Closing Range and the +/-25% volume bands quantify the latest bar; they do not turn a tight-close heuristic into a SEPA gate

See Also:
	- vcp.py: VCP detection with progressive contraction tightening
	- volume_analysis.py: Volume confirmation for breakout validation
	- base_count.py: Base-count maturity context (not sizing or a standalone risk score)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import yfinance as yf
from utils import cache_disabled, configure_cache, error_json, output_json, safe_run

# Flex-tier detector defaults. The maps define no canonical close-spread cluster, grade, or dry-up ratio, so these values remain explicit implementation heuristics.
DEFAULT_MAX_WINDOW_DAILY = 20
DEFAULT_MAX_WINDOW_WEEKLY = 20
DEFAULT_LOCATION_LOOKBACK = 50
DEFAULT_VOLUME_TREND_BAND = 0.15
DEFAULT_DRYUP_RATIO = 0.70
DEFAULT_PIVOT_ZONE_PCT = 3.0
DEFAULT_MIN_LIQUIDITY_THRESHOLD = 100000

# [TL] Locked chart-reading quantifiers: swing volume uses 20 days, position volume uses 50 days, and +/-25% from that baseline defines above/below average.
TL_SWING_VOLUME_BASELINE_DAYS = 20
TL_POSITION_VOLUME_BASELINE_DAYS = 50
TL_VOLUME_BAND_PCT = 25.0
TL_CR_CONTROL_PCT = 50.0


def _find_tight_clusters(closes, volumes, tolerance_pct, min_duration, max_window_ceiling=DEFAULT_MAX_WINDOW_DAILY):
	"""Scan for consecutive close clusters within tolerance using sliding windows.

	Uses multiple window sizes (min_duration to max_window) to find all
	possible tight close clusters. For each window position, checks if
	the spread between max and min close is within tolerance.
	"""
	close_arr = closes.values.astype(float)
	vol_arr = volumes.values.astype(float)
	dates = closes.index
	n = len(close_arr)
	max_window = min(max_window_ceiling, n)

	raw_clusters = []

	for window in range(min_duration, max_window + 1):
		for start in range(n - window + 1):
			end = start + window - 1
			segment = close_arr[start : end + 1]
			min_close = float(np.min(segment))
			max_close = float(np.max(segment))

			if min_close <= 0:
				continue

			spread_pct = (max_close - min_close) / min_close * 100

			if spread_pct <= tolerance_pct:
				avg_close = float(np.mean(segment))
				vol_segment = vol_arr[start : end + 1]
				avg_volume = float(np.mean(vol_segment))

				raw_clusters.append(
					{
						"start_idx": start,
						"end_idx": end,
						"start_date": str(dates[start].date()),
						"end_date": str(dates[end].date()),
						"duration": end - start + 1,
						"min_close": round(min_close, 2),
						"max_close": round(max_close, 2),
						"spread_pct": round(spread_pct, 2),
						"avg_close": round(avg_close, 2),
						"avg_volume": round(avg_volume),
					}
				)

	return raw_clusters


def _merge_overlapping_clusters(clusters):
	"""Merge overlapping clusters, keeping the tightest spread.

	Sorts clusters by start index then spread ascending. When two
	clusters overlap, the one with tighter spread (lower spread_pct)
	is kept. If spreads are equal, longer duration wins as tiebreaker.
	"""
	if not clusters:
		return []

	# Sort by start_idx ascending, then by spread_pct ascending (keep tightest)
	sorted_clusters = sorted(clusters, key=lambda c: (c["start_idx"], c["spread_pct"]))

	merged = []
	current = sorted_clusters[0]

	for cluster in sorted_clusters[1:]:
		# Check overlap: next cluster starts before current ends
		if cluster["start_idx"] <= current["end_idx"]:
			# Keep the one with tighter spread (lower spread_pct)
			if cluster["spread_pct"] < current["spread_pct"]:
				current = cluster
			# If same spread, keep the one with longer duration as tiebreaker
			elif cluster["spread_pct"] == current["spread_pct"] and cluster["duration"] > current["duration"]:
				current = cluster
		else:
			merged.append(current)
			current = cluster

	merged.append(current)
	return merged


def _classify_location(
	cluster,
	closes,
	highs,
	location_lookback=DEFAULT_LOCATION_LOOKBACK,
	pivot_zone_pct=DEFAULT_PIVOT_ZONE_PCT,
):
	"""Determine cluster location relative to recent price structure.

	pivot_area: cluster avg close within the configured heuristic zone of the recent high
	base_consolidation: below that zone but in the upper half of the range
	pullback: lower half of recent price range
	"""
	close_arr = closes.values.astype(float)
	high_arr = highs.values.astype(float)

	# Use data up to and including the cluster end
	end_idx = min(cluster["end_idx"] + 1, len(high_arr))
	lookback = min(location_lookback, end_idx)
	recent_highs = high_arr[end_idx - lookback : end_idx]
	recent_closes = close_arr[end_idx - lookback : end_idx]

	if len(recent_highs) == 0 or len(recent_closes) == 0:
		return "base_consolidation"

	recent_high = float(np.max(recent_highs))
	recent_low = float(np.min(recent_closes))
	avg_close = cluster["avg_close"]

	if recent_high <= 0:
		return "base_consolidation"

	pct_from_high = (recent_high - avg_close) / recent_high * 100

	if pct_from_high <= pivot_zone_pct:
		return "pivot_area"

	# Check if in upper or lower half of range
	price_range = recent_high - recent_low
	if price_range > 0:
		position_in_range = (avg_close - recent_low) / price_range
		if position_in_range >= 0.5:
			return "base_consolidation"

	return "pullback"


def _compute_volume_metrics(
	cluster,
	volumes,
	volume_baseline_avg,
	volume_trend_band=DEFAULT_VOLUME_TREND_BAND,
	min_liquidity_threshold=DEFAULT_MIN_LIQUIDITY_THRESHOLD,
):
	"""Compute volume trend, dryup ratio, and liquidity flag for a cluster.

	Volume trend compares average volume of first half vs second half.
	Dryup ratio compares cluster average volume to the caller's explicit baseline.
	The trend band and share-liquidity flag are implementation heuristics, not doctrine.
	"""
	vol_arr = volumes.values.astype(float)
	start = cluster["start_idx"]
	end = cluster["end_idx"]
	segment = vol_arr[start : end + 1]

	low_liquidity = volume_baseline_avg < min_liquidity_threshold

	if len(segment) < 2:
		return "flat", 1.0, low_liquidity

	mid = len(segment) // 2
	first_half_avg = float(np.mean(segment[:mid])) if mid > 0 else float(segment[0])
	second_half_avg = float(np.mean(segment[mid:])) if mid < len(segment) else float(segment[-1])

	if first_half_avg > 0:
		ratio = second_half_avg / first_half_avg
		if ratio < 1.0 - volume_trend_band:
			volume_trend = "declining"
		elif ratio > 1.0 + volume_trend_band:
			volume_trend = "increasing"
		else:
			volume_trend = "flat"
	else:
		volume_trend = "flat"

	cluster_avg_vol = float(np.mean(segment))
	if volume_baseline_avg > 0:
		dryup_ratio = round(cluster_avg_vol / volume_baseline_avg, 2)
	else:
		dryup_ratio = 1.0

	return volume_trend, dryup_ratio, low_liquidity


def _grade_cluster(cluster, interval, dryup_ratio_threshold=DEFAULT_DRYUP_RATIO):
	"""Assign quality grade to a tight close cluster.

	Daily grading:
	  high: spread < 1%, volume declining, location = pivot_area, duration >= 5
	  moderate: spread < 1.5%, (volume declining OR dryup < 0.7), duration >= 3
	  low: everything else meeting basic criteria

	Weekly grading:
	  high: spread < 1.5%, volume declining, duration >= 3
	  moderate: spread < 2%, duration >= 2
	  low: everything else
	"""
	spread = cluster["spread_pct"]
	vol_trend = cluster["volume_trend"]
	dryup = cluster["volume_dryup_ratio"]
	location = cluster["location"]
	duration = cluster["duration_bars"]

	if interval == "daily":
		if spread < 1.0 and vol_trend == "declining" and location == "pivot_area" and duration >= 5:
			return "high"
		if spread < 1.5 and (vol_trend == "declining" or dryup < dryup_ratio_threshold) and duration >= 3:
			return "moderate"
		return "low"
	else:
		# weekly
		if spread < 1.5 and vol_trend == "declining" and duration >= 3:
			return "high"
		if spread < 2.0 and duration >= 2:
			return "moderate"
		return "low"


def _determine_signal_strength(clusters):
	"""Determine overall signal strength from cluster qualities.

	strong: any high-quality cluster exists
	moderate: any moderate-quality cluster exists
	weak: only low-quality clusters
	none: no tight close clusters found
	"""
	if not clusters:
		return "none"

	qualities = [c["quality"] for c in clusters]

	if "high" in qualities:
		return "strong"
	if "moderate" in qualities:
		return "moderate"
	return "weak"


def _closing_range_pct(high, low, close):
	"""Return TraderLion Closing Range, or None for a zero-range bar."""
	if high <= low:
		return None
	return round((close - low) / (high - low) * 100, 2)


def _volume_band(volume, baseline):
	"""Classify volume against TraderLion's locked +/-25% baseline bands."""
	if baseline <= 0:
		return None, "unavailable"
	ratio_pct = round(volume / baseline * 100, 2)
	if ratio_pct >= 100 + TL_VOLUME_BAND_PCT:
		return ratio_pct, "above_average"
	if ratio_pct <= 100 - TL_VOLUME_BAND_PCT:
		return ratio_pct, "below_average"
	return ratio_pct, "within_average_band"


def _analyze_tight_closes(
	data,
	interval,
	tolerance_pct,
	max_window=DEFAULT_MAX_WINDOW_DAILY,
	location_lookback=DEFAULT_LOCATION_LOOKBACK,
	pivot_zone_pct=DEFAULT_PIVOT_ZONE_PCT,
	volume_trend_band=DEFAULT_VOLUME_TREND_BAND,
	dryup_ratio_threshold=DEFAULT_DRYUP_RATIO,
	min_liquidity_threshold=DEFAULT_MIN_LIQUIDITY_THRESHOLD,
):
	"""Shared analysis logic for both daily and weekly tight close detection.

	Downloads data, scans for tight close clusters, merges overlapping,
	classifies location, grades quality, and determines signal strength.
	"""
	closes = data["Close"]
	highs = data["High"]
	volumes = data["Volume"]
	current_price = round(float(closes.iloc[-1]), 2)
	date_str = str(data.index[-1].date())

	vol_arr = volumes.values.astype(float)
	dryup_baseline_bars = TL_POSITION_VOLUME_BASELINE_DAYS if interval == "daily" else 10
	dryup_baseline_avg = float(np.mean(vol_arr[-dryup_baseline_bars:]))
	dryup_baseline_label = "50 daily bars [M]" if interval == "daily" else "10 weekly bars [heuristic 50-session approximation]"
	latest_cr = _closing_range_pct(float(data["High"].iloc[-1]), float(data["Low"].iloc[-1]), float(data["Close"].iloc[-1]))
	if latest_cr is None:
		latest_cr_read = "unavailable_zero_range"
	elif latest_cr > TL_CR_CONTROL_PCT:
		latest_cr_read = "buyer_advantage"
	elif latest_cr < TL_CR_CONTROL_PCT:
		latest_cr_read = "seller_advantage"
	else:
		latest_cr_read = "indecision"

	if interval == "daily":
		tl_volume_baseline = float(np.mean(vol_arr[-TL_SWING_VOLUME_BASELINE_DAYS:]))
		latest_volume_ratio_pct, latest_volume_band = _volume_band(float(vol_arr[-1]), tl_volume_baseline)
		latest_volume_basis = f"[TL] {TL_SWING_VOLUME_BASELINE_DAYS}-day swing baseline"
	else:
		latest_volume_ratio_pct, latest_volume_band = None, "unavailable_from_weekly_bars"
		latest_volume_basis = "[TL] +/-25% labels require a 20-day swing or 50-day position baseline; this command has weekly bars only"

	# Set min duration based on interval
	if interval == "daily":
		min_duration = 3
	else:
		min_duration = 2

	# Find all tight close clusters
	raw_clusters = _find_tight_clusters(closes, volumes, tolerance_pct, min_duration, max_window)

	# Merge overlapping clusters
	merged = _merge_overlapping_clusters(raw_clusters)

	# Enrich each cluster with volume metrics, location, and quality grade
	enriched_clusters = []
	for cluster in merged:
		location = _classify_location(cluster, closes, highs, location_lookback, pivot_zone_pct)
		volume_trend, dryup_ratio, low_liquidity = _compute_volume_metrics(
			cluster,
			volumes,
			dryup_baseline_avg,
			volume_trend_band,
			min_liquidity_threshold,
		)

		enriched = {
			"start_date": cluster["start_date"],
			"end_date": cluster["end_date"],
			"duration_bars": cluster["duration"],
			"duration_unit": "trading_days" if interval == "daily" else "weeks",
			"min_close": cluster["min_close"],
			"max_close": cluster["max_close"],
			"spread_pct": cluster["spread_pct"],
			"spread_pct_unit": "(max_close - min_close) / min_close * 100",
			"avg_close": cluster["avg_close"],
			"volume_trend": volume_trend,
			"volume_dryup_ratio": dryup_ratio,
			"volume_dryup_ratio_unit": f"cluster avg volume / {dryup_baseline_label}",
			"low_liquidity": low_liquidity if interval == "daily" else None,
			"location": location,
		}

		quality = _grade_cluster(enriched, interval, dryup_ratio_threshold)
		enriched["quality"] = quality
		enriched_clusters.append(enriched)

	# Determine best cluster (highest quality, then longest duration, then tightest spread)
	quality_order = {"high": 0, "moderate": 1, "low": 2}
	best_cluster = None
	if enriched_clusters:
		sorted_clusters = sorted(
			enriched_clusters,
			key=lambda c: (quality_order.get(c["quality"], 3), -c["duration_bars"], c["spread_pct"]),
		)
		best = sorted_clusters[0]
		best_cluster = {
			"start_date": best["start_date"],
			"end_date": best["end_date"],
			"spread_pct": best["spread_pct"],
			"quality": best["quality"],
		}

	signal_strength = _determine_signal_strength(enriched_clusters)
	thresholds = {
		"cluster_detector": f"[heuristic] close spread <= {tolerance_pct:.2f}% across 3+ daily or 2+ weekly bars; no canonical tight-close threshold exists in either knowledge map",
		"window": f"[heuristic] max {max_window} bars; location lookback {location_lookback} bars; pivot zone {pivot_zone_pct:.2f}%",
		"grading": "[heuristic] daily high <1%/declining-volume/pivot/5+ bars; daily moderate <1.5% and declining or dry-up/3+ bars; weekly high <1.5%/declining/3+ bars",
		"dryup": f"[heuristic] ratio < {dryup_ratio_threshold:.2f} affects the grade; [M] canonical corroboration is below the 50-day average plus one or two exceptionally quiet days, without a fixed ratio",
		"volume_trend": f"[heuristic] second-half volume differs by more than {volume_trend_band * 100:.1f}% from first-half volume",
		"liquidity": f"[heuristic] daily average share-volume flag below {min_liquidity_threshold:,}; unavailable on weekly bars and not a universal SEPA floor",
		"closing_range": "[TL] CR=(close-low)/(high-low)*100; >50 buyer advantage, <50 seller advantage, 50 indecision",
		"volume_band": f"[TL] >= {100 + TL_VOLUME_BAND_PCT:.0f}% of baseline = above average; <= {100 - TL_VOLUME_BAND_PCT:.0f}% = below average",
	}

	# Compressed view: keep only most recent 3 clusters + best + signal_strength
	total_count = len(enriched_clusters)
	_compressed = {}
	if total_count > 3:
		_compressed["tight_close_clusters"] = enriched_clusters[-3:]
	else:
		_compressed["tight_close_clusters"] = enriched_clusters
	_compressed["total_count"] = total_count
	if best_cluster:
		_compressed["best_cluster"] = best_cluster
	_compressed["signal_strength"] = signal_strength
	_compressed["thresholds"] = thresholds

	return {
		"symbol": None,  # filled by caller
		"date": date_str,
		"current_price": current_price,
		"interval": interval,
		"latest_bar_quantifiers": {
			"closing_range_pct": latest_cr,
			"closing_range_read": f"[TL] {latest_cr_read}",
			"volume_vs_baseline_pct": latest_volume_ratio_pct,
			"volume_band": f"[TL] {latest_volume_band}",
			"volume_baseline": latest_volume_basis,
		},
		"tight_close_clusters": enriched_clusters,
		"cluster_count": len(enriched_clusters),
		"best_cluster": best_cluster,
		"signal_strength": signal_strength,
		"thresholds": thresholds,
		"doctrine": {
			"supply": "[M] Contracting price ranges and drying volume can show supply absorption, but tightness is corroboration only; it never establishes Stage 2, a valid VCP, or a buy decision by itself.",
			"final_contraction": "[M] The source-backed volume test is below the stock's own 50-day average plus one or two exceptionally quiet days near the contraction low; this module's fixed dry-up ratio is only a tunable detector heuristic.",
			"quantifiers": "[TL] Closing Range locates the close within one bar, while the +/-25% volume bands label participation against 20-day swing or 50-day position baselines. They are practice-layer measurements, not immutable SEPA gates.",
			"timeframe": "[TL] Higher-timeframe evidence carries more context, but daily and weekly readings must retain their own units instead of silently mixing days and weeks.",
		},
		"compressed": _compressed,
	}


@safe_run
def cmd_daily(args):
	"""Detect tight closes on daily price data."""
	configure_cache(args.no_cache or cache_disabled())
	_validate_args(args, min_duration=3)
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1d")
	# yfinance appends a partial in-session bar whose OHLC can be NaN; that NaN
	# poisons closes.iloc[-1] and every comparison downstream. Drop it first.
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 20:
		error_json(f"Insufficient data for {symbol}. Need at least 20 trading days; received {len(data)}.")

	result = _analyze_tight_closes(
		data,
		"daily",
		args.tolerance,
		args.max_window,
		args.location_lookback,
		args.pivot_zone_pct,
		args.volume_trend_band_pct / 100,
		args.dryup_ratio,
		args.min_liquidity,
	)
	result["symbol"] = symbol

	output_json(result)


@safe_run
def cmd_weekly(args):
	"""Detect tight closes on weekly price data."""
	configure_cache(args.no_cache or cache_disabled())
	_validate_args(args, min_duration=2)
	symbol = args.symbol.upper()
	ticker = yf.Ticker(symbol)
	data = ticker.history(period=args.period, interval="1wk")
	# yfinance appends a partial in-session bar whose OHLC can be NaN; that NaN
	# poisons closes.iloc[-1] and every comparison downstream. Drop it first.
	data = data.dropna(subset=["Open", "High", "Low", "Close"])

	if data.empty or len(data) < 20:
		error_json(f"Insufficient data for {symbol}. Need at least 20 weekly bars; received {len(data)}.")

	result = _analyze_tight_closes(
		data,
		"weekly",
		args.tolerance,
		args.max_window,
		args.location_lookback,
		args.pivot_zone_pct,
		args.volume_trend_band_pct / 100,
		args.dryup_ratio,
		args.min_liquidity,
	)
	result["symbol"] = symbol

	output_json(result)


def _validate_args(args, min_duration):
	"""Validate flex-tier detector inputs through the JSON error contract."""
	if args.tolerance <= 0:
		error_json("--tolerance must be positive.")
	if args.max_window < min_duration:
		error_json(f"--max-window must be at least {min_duration} bars for this subcommand.")
	if args.location_lookback < 1:
		error_json("--location-lookback must be positive.")
	if args.pivot_zone_pct < 0:
		error_json("--pivot-zone-pct cannot be negative.")
	if not 0 <= args.volume_trend_band_pct <= 100:
		error_json("--volume-trend-band-pct must be between 0 and 100.")
	if args.dryup_ratio <= 0:
		error_json("--dryup-ratio must be positive.")
	if args.min_liquidity < 0:
		error_json("--min-liquidity cannot be negative.")


def _add_detector_flags(parser, max_window_default):
	"""Add shared flex-tier flags to a real subcommand parser."""
	parser.add_argument(
		"--max-window",
		type=int,
		default=max_window_default,
		help="[heuristic] Longest bar-run scanned for a tight-close cluster (default: %(default)s); no canonical close-cluster window exists.",
	)
	parser.add_argument(
		"--location-lookback",
		type=int,
		default=DEFAULT_LOCATION_LOOKBACK,
		help="[heuristic] Bars used to locate a cluster within recent structure (default: %(default)s).",
	)
	parser.add_argument(
		"--pivot-zone-pct",
		type=float,
		default=DEFAULT_PIVOT_ZONE_PCT,
		help="[heuristic] Distance from the recent high labeled pivot_area (default: %(default)s%%; not doctrine).",
	)
	parser.add_argument(
		"--volume-trend-band-pct",
		type=float,
		default=DEFAULT_VOLUME_TREND_BAND * 100,
		help="[heuristic] Half-band around a flat first-half/second-half volume ratio (default: %(default)s%%; not doctrine).",
	)
	parser.add_argument(
		"--dryup-ratio",
		type=float,
		default=DEFAULT_DRYUP_RATIO,
		help="[heuristic] Cluster-average/baseline volume ratio used only for grading (default: %(default)s; [M] supplies no fixed dry-up ratio).",
	)
	parser.add_argument(
		"--min-liquidity",
		type=int,
		default=DEFAULT_MIN_LIQUIDITY_THRESHOLD,
		help="[heuristic] Daily average share-volume warning floor (default: %(default)s; unavailable for weekly bars).",
	)
	parser.add_argument("--no-cache", action="store_true", help="Bypass the shared read-through cache for this invocation")


def main():
	class JsonArgumentParser(argparse.ArgumentParser):
		def error(self, message):
			error_json(message)

	parser = JsonArgumentParser(description="Tight-close detector: heuristic close clusters with [M]/[TL] corroboration, not an analyze-everything command")
	sub = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)

	# daily
	sp = sub.add_parser("daily", help="Detect tight closes on daily data")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--period", default="6mo", help="Data period (default: 6mo)")
	sp.add_argument("--tolerance", type=float, default=1.0, help="[heuristic] Maximum inter-close spread %% (default: %(default)s; not [M]/[TL] doctrine)")
	_add_detector_flags(sp, DEFAULT_MAX_WINDOW_DAILY)
	sp.set_defaults(func=cmd_daily)

	# weekly
	sp = sub.add_parser("weekly", help="Detect tight closes on weekly data")
	sp.add_argument("symbol", help="Ticker symbol")
	sp.add_argument("--period", default="1y", help="Data period (default: 1y)")
	sp.add_argument("--tolerance", type=float, default=1.5, help="[heuristic] Maximum inter-close spread %% (default: %(default)s; not [M]/[TL] doctrine)")
	_add_detector_flags(sp, DEFAULT_MAX_WINDOW_WEEKLY)
	sp.set_defaults(func=cmd_weekly)

	args = parser.parse_args()
	args.func(args)


if __name__ == "__main__":
	main()
