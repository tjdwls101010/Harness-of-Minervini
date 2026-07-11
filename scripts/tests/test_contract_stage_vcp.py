#!/usr/bin/env python3
"""Deterministic contract tests for stage_analysis and vcp."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "scripts" / "modules"
sys.path.insert(0, str(MODULE_DIR))

import stage_analysis as stage  # noqa: E402
import vcp  # noqa: E402


def _daily_frame(close, volume=None, start="2025-01-02"):
	close = np.asarray(close, dtype=float)
	index = pd.bdate_range(start, periods=len(close))
	volume = np.full(len(close), 100.0) if volume is None else np.asarray(volume, dtype=float)
	return pd.DataFrame(
		{
			"Open": close,
			"High": close * 1.005,
			"Low": close * 0.995,
			"Close": close,
			"Volume": volume,
		},
		index=index,
	)


class StageContractTests(unittest.TestCase):
	def test_pure_snapshot_owns_climax_and_source_defined_max_decline(self):
		close = np.linspace(50.0, 100.0, 260)
		close[230] = close[229] * 0.88
		frame = _daily_frame(close)
		result = stage.compute_risk_snapshot(frame)
		self.assertIn("climax_extension", result)
		decline = result["largest_decline_since_stage2"]
		self.assertAlmostEqual(decline["daily"]["pct"], -12.0, places=2)
		self.assertEqual(decline["provenance"].split()[0], "[M]")
		self.assertNotIn("band", decline)
		self.assertIn("peak_to_trough_context", decline)

	def test_partial_week_is_not_counted_as_completed_week(self):
		index = pd.date_range("2026-06-01", periods=10, freq="D")  # ends Wednesday
		frame = pd.DataFrame({"Close": np.arange(10) + 10.0, "Volume": 100}, index=index)
		weekly = stage._completed_weekly_closes(frame)
		self.assertTrue(weekly.empty or weekly.index[-1].date() <= index[-1].date())

	def test_invalid_stage_tuning_is_json_exit_one(self):
		proc = subprocess.run(
			[sys.executable, str(MODULE_DIR / "stage_analysis.py"), "classify", "TEST", "--swing-bars", "0"],
			cwd=ROOT,
			text=True,
			capture_output=True,
			check=False,
		)
		self.assertEqual(proc.returncode, 1)
		self.assertIn("swing-bars", json.loads(proc.stdout)["error"])


class VcpContractTests(unittest.TestCase):
	def test_breakout_requires_five_cent_price_confirmation(self):
		index = pd.bdate_range("2026-01-02", periods=60)
		volume = pd.Series(np.r_[np.full(59, 100.0), 200.0], index=index)
		below = pd.Series(np.r_[np.full(59, 99.0), 99.99], index=index)
		above = pd.Series(np.r_[np.full(59, 99.0), 100.06], index=index)
		self.assertFalse(vcp._assess_breakout_volume(volume, below, 100.0)["breakout_volume_confirmed"])
		self.assertTrue(vcp._assess_breakout_volume(volume, above, 100.0)["breakout_volume_confirmed"])

	def test_vcp_duration_is_a_locked_gate(self):
		checks, detected = vcp._vcp_gate_checks([24.0, 12.0], 2, 60.0, 2)
		self.assertFalse(detected)
		self.assertFalse(checks["duration_3_to_65_weeks"])
		self.assertTrue(vcp._vcp_gate_checks([24.0, 12.0], 2, 60.0, 3)[1])
		self.assertFalse(vcp._vcp_gate_checks([60.0, 30.0], 2, 60.0, 8)[1])

	def test_contraction_detection_has_no_invented_two_percent_floor(self):
		contractions = vcp._detect_contractions([(0, 100.0)], [(1, 99.0)], pd.Series([100.0, 99.0]))
		self.assertEqual(len(contractions), 1)
		self.assertEqual(contractions[0]["depth_pct"], 1.0)

	def test_hostile_market_flag_exposes_the_mapped_3c_depth_exception(self):
		self.assertEqual(vcp._three_c_depth_ceiling(False), 40.0)
		self.assertEqual(vcp._three_c_depth_ceiling(True), 50.0)
		help_result = subprocess.run(
			[sys.executable, str(MODULE_DIR / "vcp.py"), "detect", "--help"],
			cwd=ROOT,
			text=True,
			capture_output=True,
			check=False,
		)
		self.assertEqual(help_result.returncode, 0)
		self.assertIn("--hostile-market", help_result.stdout)

	def test_power_play_accepts_shorter_than_max_advance_without_relaxing_100pct(self):
		close = np.full(80, 50.0)
		close[50:65] = np.linspace(50.0, 105.0, 15)
		close[65:] = np.linspace(101.0, 104.0, 15)
		volume = np.full(80, 100.0)
		volume[60] = 300.0
		volume[65:] = np.linspace(90.0, 60.0, 15)
		frame = _daily_frame(close, volume)
		result = vcp._detect_power_play(
			frame["Open"], frame["High"], frame["Close"], frame["Volume"],
			100.0, advance_bars=39, lows=frame["Low"], interval="1d",
		)
		self.assertTrue(result["detected"], result)
		self.assertGreaterEqual(result["advance_pct"], 100.0)
		self.assertLess(result["advance_bars"], 39)
		self.assertIn("price/volume structure", result["fundamentals_exception"]["never_waives"])

	def test_weekly_power_play_uses_week_units_and_three_to_six_week_flag(self):
		close = np.full(20, 50.0)
		close[7:14] = np.linspace(50.0, 105.0, 7)
		close[14:] = np.linspace(101.0, 104.0, 6)
		volume = np.full(20, 100.0)
		volume[12] = 250.0
		volume[14:] = np.linspace(90.0, 60.0, 6)
		index = pd.date_range("2025-01-03", periods=20, freq="W-FRI")
		frame = pd.DataFrame(
			{"Open": close, "High": close * 1.005, "Low": close * 0.995, "Close": close, "Volume": volume},
			index=index,
		)
		result = vcp._detect_power_play(
			frame["Open"], frame["High"], frame["Close"], frame["Volume"],
			100.0, advance_bars=39, lows=frame["Low"], interval="1wk",
		)
		self.assertTrue(result["detected"], result)
		self.assertEqual(result["advance_bar_unit"], "week")
		self.assertEqual(result["flag_bar_unit"], "week")
		self.assertGreaterEqual(result["flag_bars"], 3)
		self.assertLessEqual(result["flag_bars"], 6)

	def test_setup_score_never_uses_actionable_label(self):
		result = vcp._calculate_setup_readiness(
			[0.5, 0.5], "confirmed", {"is_tight": True},
			{"shakeout_quality_score": 10}, {"right_side_quality": "constructive"},
			{"demand_dominance": True, "post_shakeout_demand": True},
			{"detected": False},
		)
		self.assertNotIn("actionable", result["classification"])

	def test_pattern_classifier_keeps_flat_base_within_map_scope(self):
		contractions = [{"depth_pct": 12.0}, {"depth_pct": 6.0}]
		self.assertEqual(vcp._classify_pattern(contractions, 4), "Flat Base")
		self.assertEqual(vcp._classify_pattern(contractions, 7), "Flat Base")
		self.assertEqual(vcp._classify_pattern(contractions, 8), "Standard VCP")

	def test_cup_and_handle_is_not_a_public_detector(self):
		self.assertFalse(hasattr(vcp, "_detect_cup_and_handle"))


if __name__ == "__main__":
	unittest.main()
