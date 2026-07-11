#!/usr/bin/env python3
"""Focused deterministic tests for the Phase-1 module extensions."""

import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import pandas as pd


MODULES = Path(__file__).resolve().parents[1] / "modules"
sys.path.insert(0, str(MODULES))

import actions
import info
import market_breadth
import volume_analysis


class ActionsContractTests(unittest.TestCase):
	def test_days_until_uses_nearest_non_past_date(self):
		index = pd.DatetimeIndex(["2026-07-09", "2026-07-15", "2026-08-01"], tz="America/New_York")
		data = pd.DataFrame({"EPS Estimate": [1.0, 1.1, 1.2]}, index=index)
		result = actions._days_until_summary(data, today=dt.date(2026, 7, 10))
		self.assertEqual(result["next_earnings_date"], "2026-07-15")
		self.assertEqual(result["days_until"], 5)


class InfoContractTests(unittest.TestCase):
	def test_history_records_preserve_ohlcv_and_date(self):
		frame = pd.DataFrame(
			{"Open": [10.0], "High": [11.0], "Low": [9.0], "Close": [10.5], "Volume": [123]},
			index=pd.DatetimeIndex(["2026-07-09"], tz="America/New_York"),
		)
		records = info._history_records(frame)
		self.assertEqual(records[0]["Volume"], 123)
		self.assertIn("2026-07-09", records[0]["date"])

	def test_invalid_history_range_is_json_exit_one(self):
		args = type("Args", (), {"start": "2026-07-10", "end": "2026-07-10", "symbol": "AAPL", "interval": "1d"})()
		buffer = io.StringIO()
		with contextlib.redirect_stdout(buffer), self.assertRaises(SystemExit) as raised:
			info.cmd_get_history(args)
		self.assertEqual(raised.exception.code, 1)
		self.assertIn('"error"', buffer.getvalue())


class VolumeQuantifierTests(unittest.TestCase):
	def test_closing_range_is_percentage(self):
		self.assertEqual(volume_analysis._closing_range_percent(98.0, 100.0, 90.0), 80.0)
		self.assertEqual(volume_analysis._close_range_pct(98.0, 100.0, 90.0), 80.0)

	def test_volume_band_uses_plus_minus_25_percent(self):
		self.assertEqual(volume_analysis._volume_band(126.0, 100.0)["status"], "above_average")
		self.assertEqual(volume_analysis._volume_band(74.0, 100.0)["status"], "below_average")
		self.assertEqual(volume_analysis._volume_band(100.0, 100.0)["status"], "within_average_band")

	def test_adr_percent_formula(self):
		frame = pd.DataFrame({"High": [103.0] * 10, "Low": [100.0] * 10})
		self.assertEqual(volume_analysis._adr_percent(frame), 3.0)

	def test_regular_session_fraction_extrapolation(self):
		projected = volume_analysis._project_full_session_volume(175_000, 60 / 390)
		self.assertEqual(projected, 1_137_500)

	def test_analyze_uses_volume_evidence_without_distribution_day_counts(self):
		index = pd.date_range("2026-01-02", periods=60, freq="B", tz="America/New_York")
		closes = [100.0 + (offset * 0.2) + (0.6 if offset % 2 else 0.0) for offset in range(60)]
		frame = pd.DataFrame(
			{
				"Open": [value - 0.2 for value in closes],
				"High": [value + 1.0 for value in closes],
				"Low": [value - 1.0 for value in closes],
				"Close": closes,
				"Volume": [1_000_000 + (offset % 5) * 50_000 for offset in range(60)],
			},
			index=index,
		)
		args = type(
			"Args",
			(),
			{
				"no_cache": False,
				"symbol": "TEST",
				"period": "6mo",
				"lookback": 50,
				"short_lookback": 20,
					"up_volume_window": 5,
				"pullback_window": 20,
			},
		)()
		buffer = io.StringIO()
		with (
			mock.patch.object(volume_analysis.yf, "Ticker") as ticker,
			contextlib.redirect_stdout(buffer),
		):
			ticker.return_value.history.return_value = frame
			volume_analysis.cmd_analyze(args)
		result = json.loads(buffer.getvalue())
		for forbidden in (
			"accumulation_days_50d",
			"distribution_days_50d",
			"net_acc_dist",
			"recent_distribution_dates",
			"distribution_clusters",
			"count_based_ratio_50d",
			"count_based_ratio_20d",
		):
			self.assertNotIn(forbidden, result)
		self.assertNotIn("heavy_dist_days", result["volume_direction_summary_20d"])
		self.assertNotIn("heavy_acc_days", result["volume_direction_summary_20d"])
		self.assertIn("up_down_volume_ratio_primary", result)
		self.assertIn("up_down_volume_ratio_primary_lookback_days", result)
		# The window-named legacy key must NOT reappear: it mislabeled a tunable
		# window as canonical "50d" (a --lookback 120 value emitted as "over 50d").
		self.assertNotIn("up_down_volume_ratio_50d", result)
		self.assertIn("recent_up_volume_evidence", result)
		self.assertIsNone(result["breakout_volume_confirmation"])
		self.assertNotIn("climactic_volume", result)

	def test_zero_down_volume_is_explicitly_undefined_not_a_fabricated_ratio(self):
		volumes = pd.Series([100.0, 110.0, 120.0, 130.0])
		closes = pd.Series([10.0, 11.0, 12.0, 13.0])
		ratio, up_volume, down_volume = volume_analysis._calc_up_down_ratio(volumes, closes, 4)
		self.assertIsNone(ratio)
		self.assertGreater(up_volume, 0)
		self.assertEqual(down_volume, 0)
		self.assertEqual(volume_analysis._grade_accumulation(ratio), "unavailable")
		summary = volume_analysis._volume_direction_summary(volumes, closes, 4)
		self.assertIsNone(summary["up_down_volume_ratio_by_total"])
		self.assertEqual(summary["ratio_status"], "no_down_volume")


class MarketBreadthTests(unittest.TestCase):
	def _document(self, block_count=4):
		blocks = []
		for index in range(block_count):
			blocks.append(
				f"""
				<div class="market-stats extra-{index}">
				  <div class="market-stats_labels_left"><p>Label</p><p>{45.0 + index}% ({100 + index})</p></div>
				  <div class="market-stats_labels_right"><p>Label</p><p>({90 + index}) {40.0 + index}%</p></div>
				</div>
				"""
			)
		return "<html><body>" + "".join(blocks) + "</body></html>"

	def test_xpath_parser_reads_all_sections(self):
		result = market_breadth._parse_finviz_sections(self._document())
		self.assertEqual(result["advancing_declining"]["advancing"]["count"], 100)
		self.assertEqual(result["sma200"]["below"]["pct"], 43.0)

	def test_missing_dom_block_degrades_only_that_section(self):
		result = market_breadth._parse_finviz_sections(self._document(block_count=3))
		self.assertFalse(result["sma50"].get("unavailable", False))
		self.assertTrue(result["sma200"]["unavailable"])

	def test_source_failure_degrades_sections_without_failing_composite(self):
		args = type("Args", (), {"no_cache": False})()
		buffer = io.StringIO()
		with (
			mock.patch.object(market_breadth, "get_market_breadth", side_effect=TimeoutError("finviz timeout")),
			mock.patch.object(market_breadth, "get_qqq_switch", return_value={"state": "ON"}),
			contextlib.redirect_stdout(buffer),
		):
			market_breadth.cmd_breadth(args)
		result = json.loads(buffer.getvalue())
		self.assertTrue(result["new_high_low"]["unavailable"])
		self.assertEqual(result["qqq_21ema_switch"]["state"], "ON")

	def test_qqq_switch_is_asymmetric(self):
		closes = [100.0] * 21 + [99.0, 98.0, 110.0]
		frame = pd.DataFrame(
			{
				"Close": closes,
				"High": [value + 1.0 for value in closes],
				"Low": [value - 0.5 for value in closes],
			},
			index=pd.date_range("2026-01-02", periods=len(closes), freq="B"),
		)
		result = market_breadth._evaluate_qqq_switch(frame)
		self.assertEqual(result["state"], "ON")
		self.assertEqual([event["state"] for event in result["recent_transitions"]][-2:], ["OFF", "ON"])
		self.assertIn("second close below the prior day's low", result["rules"]["OFF"])


if __name__ == "__main__":
	unittest.main()
