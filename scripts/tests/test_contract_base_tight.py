#!/usr/bin/env python3
"""Focused offline contract tests for base_count and tight_closes."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = REPO_ROOT / "scripts" / "modules"
sys.path.insert(0, str(MODULE_DIR))

import base_count  # noqa: E402
import tight_closes  # noqa: E402


def _bars(periods=60, freq="B"):
	index = pd.date_range("2025-01-02", periods=periods, freq=freq)
	closes = [100.0 + (i % 3) * 0.1 for i in range(periods)]
	return pd.DataFrame(
		{
			"Open": [value - 0.2 for value in closes],
			"High": [value + 1.0 for value in closes],
			"Low": [value - 1.0 for value in closes],
			"Close": closes,
			"Volume": [100_000.0] * periods,
		},
		index=index,
	)


class CliContractTests(unittest.TestCase):
	def _run(self, *parts):
		return subprocess.run(
			[sys.executable, *parts],
			cwd=REPO_ROOT,
			text=True,
			capture_output=True,
			check=False,
		)

	def test_help_paths_are_offline_and_document_live_flags(self):
		cases = [
			("scripts/modules/base_count.py", "--help"),
			("scripts/modules/base_count.py", "count", "--help"),
			("scripts/modules/tight_closes.py", "--help"),
			("scripts/modules/tight_closes.py", "daily", "--help"),
			("scripts/modules/tight_closes.py", "weekly", "--help"),
		]
		for case in cases:
			with self.subTest(case=case):
				result = self._run(*case)
				self.assertEqual(result.returncode, 0, result.stderr)
				self.assertEqual(result.stderr, "")
		self.assertIn("--no-cache", self._run("scripts/modules/base_count.py", "count", "--help").stdout)
		self.assertIn("[M]", self._run("scripts/modules/base_count.py", "count", "--help").stdout)
		tight_help = self._run("scripts/modules/tight_closes.py", "daily", "--help").stdout
		self.assertIn("--no-cache", tight_help)
		self.assertIn("[heuristic]", tight_help)

	def test_no_cache_is_accepted_after_subcommand_and_errors_are_json_exit_one(self):
		cases = [
			("scripts/modules/base_count.py", "count", "AAPL", "--min-base-weeks", "2", "--no-cache"),
			("scripts/modules/tight_closes.py", "daily", "AAPL", "--tolerance", "0", "--no-cache"),
			("scripts/modules/tight_closes.py", "weekly", "AAPL", "--max-window", "1", "--no-cache"),
		]
		for case in cases:
			with self.subTest(case=case):
				result = self._run(*case)
				self.assertEqual(result.returncode, 1)
				self.assertEqual(result.stderr, "")
				payload = json.loads(result.stdout)
				self.assertEqual(set(payload), {"error"})


class DoctrineBoundaryTests(unittest.TestCase):
	def _forming_base_at_depth(self, depth_pct):
		index = pd.date_range("2025-01-02", periods=10, freq="B")
		base_low = 100 * (1 - depth_pct / 100)
		closes = pd.Series([99.0] + [base_low + 0.5] * 9, index=index)
		highs = pd.Series([100.0] + [base_low + 1.0] * 9, index=index)
		lows = pd.Series([99.0] + [base_low] * 9, index=index)
		sma200 = pd.Series([50.0] * 10, index=index)
		_, forming = base_count._find_bases(
			closes,
			highs,
			lows,
			sma200,
			min_base_weeks=1,
			swing_window=1,
			max_base_days=10,
			forming_recency_days=10,
		)
		return forming

	def test_base_locked_boundaries_and_neutral_pattern_labels(self):
		self.assertEqual(base_count.MIN_CORRECTION_PCT, 10.0)
		self.assertEqual(base_count.REDLINE_DEPTH_PCT, 60.0)
		self.assertIsNone(self._forming_base_at_depth(9.99))
		self.assertIsNotNone(self._forming_base_at_depth(10.0))
		self.assertIsNotNone(self._forming_base_at_depth(59.99))
		self.assertIsNone(self._forming_base_at_depth(60.0))
		self.assertEqual(base_count._classify_base_pattern(10, 4), "flat_base_candidate_[M]")
		self.assertEqual(base_count._classify_base_pattern(15, 7), "flat_base_candidate_[M]")
		self.assertEqual(base_count._classify_base_pattern(20, 3), "base_candidate")
		self.assertNotIn("Power", base_count._classify_base_pattern(20, 3))

	def test_traderlion_quantifier_boundaries(self):
		self.assertEqual(tight_closes._closing_range_pct(100, 90, 98), 80.0)
		self.assertIsNone(tight_closes._closing_range_pct(100, 100, 100))
		self.assertEqual(tight_closes._volume_band(75, 100), (75.0, "below_average"))
		self.assertEqual(tight_closes._volume_band(125, 100), (125.0, "above_average"))
		self.assertEqual(tight_closes._volume_band(100, 100), (100.0, "within_average_band"))

	def test_daily_output_has_doctrine_provenance_and_explicit_units(self):
		result = tight_closes._analyze_tight_closes(_bars(), "daily", 1.0)
		self.assertIn("doctrine", result)
		self.assertIn("[M]", result["doctrine"]["supply"])
		self.assertIn("[TL]", result["doctrine"]["quantifiers"])
		self.assertIn("[heuristic]", result["thresholds"]["cluster_detector"])
		self.assertIn("closing_range_pct", result["latest_bar_quantifiers"])
		for cluster in result["tight_close_clusters"]:
			self.assertEqual(cluster["duration_unit"], "trading_days")
			self.assertIn("duration_bars", cluster)

	def test_weekly_output_does_not_mislabel_weekly_volume_as_daily(self):
		result = tight_closes._analyze_tight_closes(_bars(freq="W-FRI"), "weekly", 1.5)
		self.assertEqual(result["latest_bar_quantifiers"]["volume_vs_baseline_pct"], None)
		self.assertIn("weekly", result["latest_bar_quantifiers"]["volume_band"])
		for cluster in result["tight_close_clusters"]:
			self.assertEqual(cluster["duration_unit"], "weeks")
			self.assertIsNone(cluster["low_liquidity"])
			self.assertNotIn("50d avg", cluster["volume_dryup_ratio_unit"])


if __name__ == "__main__":
	unittest.main()
