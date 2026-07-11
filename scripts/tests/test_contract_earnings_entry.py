#!/usr/bin/env python3
"""Offline contract tests for earnings_acceleration and entry_patterns."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "scripts" / "modules"
sys.path.insert(0, str(MODULE_DIR))

import earnings_acceleration as earnings  # noqa: E402
import entry_patterns as entry  # noqa: E402


class CliContractTests(unittest.TestCase):
	def run_cli(self, module, *args):
		return subprocess.run(
			[sys.executable, str(MODULE_DIR / module), *args],
			cwd=ROOT,
			text=True,
			capture_output=True,
			check=False,
			timeout=10,
		)

	def test_help_is_offline_and_no_cache_is_after_every_subcommand(self):
		commands = {
			"earnings_acceleration.py": ("code33", "acceleration", "surprise", "revisions", "valuation", "margin"),
			"entry_patterns.py": ("scan", "screen"),
		}
		for module, subcommands in commands.items():
			root_help = self.run_cli(module, "--help")
			self.assertEqual(root_help.returncode, 0, root_help.stderr)
			for command in subcommands:
				result = self.run_cli(module, command, "--help")
				self.assertEqual(result.returncode, 0, result.stderr)
				self.assertIn("--no-cache", result.stdout)

	def test_argparse_and_validation_errors_are_json_exit_one(self):
		missing = self.run_cli("earnings_acceleration.py")
		self.assertEqual(missing.returncode, 1)
		self.assertIn("error", json.loads(missing.stdout))

		locked_floor = self.run_cli("earnings_acceleration.py", "code33", "TEST", "--eps-min-pct", "19")
		self.assertEqual(locked_floor.returncode, 1)
		self.assertIn("[M] locked floor", json.loads(locked_floor.stdout)["error"])

		invalid_entry = self.run_cli("entry_patterns.py", "scan", "TEST", "--pivot-min-days", "30", "--pivot-max-days", "10")
		self.assertEqual(invalid_entry.returncode, 1)
		self.assertIn("cannot exceed", json.loads(invalid_entry.stdout)["error"])


class EarningsSemanticsTests(unittest.TestCase):
	def test_code33_requires_four_observations_for_three_transitions(self):
		three = [("q3", 30.0), ("q2", 20.0), ("q1", 10.0)]
		four = three + [("q0", 5.0)]
		self.assertFalse(earnings._is_accelerating(three)[0])
		self.assertTrue(earnings._is_accelerating(four)[0])

	def test_revisions_accept_yfinance_dataframe_shape(self):
		fake = Mock()
		fake.get_eps_revisions.return_value = pd.DataFrame(
			{"upLast30days": [4, 2], "downLast30days": [0, 1]}, index=["0q", "+1q"]
		)
		fake.get_eps_trend.return_value = pd.DataFrame(
			{"current": [2.0], "7daysAgo": [1.9], "30daysAgo": [1.8], "90daysAgo": [1.7]}, index=["0q"]
		)
		fake.get_growth_estimates.return_value = pd.DataFrame(
			{"stockTrend": [0.25, 0.30]}, index=["0y", "+1y"]
		)
		with patch.object(earnings.yf, "Ticker", return_value=fake), patch.object(earnings, "output_json") as emit:
			earnings.cmd_revisions(SimpleNamespace(symbol="test", no_cache=False))
		result = emit.call_args.args[0]
		self.assertEqual(result["compressed"]["direction"], "up")
		self.assertEqual(result["compressed"]["current_quarter_estimate"], 2.0)
		self.assertIn("[M]", result["doctrine"])


class EntrySemanticsTests(unittest.TestCase):
	def test_tl_quantifiers_use_exact_cr_and_volume_bands(self):
		high = np.array([101.0] * 49 + [110.0])
		low = np.array([99.0] * 49 + [100.0])
		close = np.array([100.0] * 49 + [108.0])
		volume = np.array([100.0] * 49 + [130.0])
		result = entry._chart_quantifiers(high, low, close, volume, 25.0)
		self.assertEqual(result["closing_range_pct"], 80.0)
		self.assertEqual(result["volume_vs_20d"]["classification"], "above_average")
		self.assertEqual(result["volume_vs_50d"]["classification"], "above_average")
		self.assertIsNone(result["adr_pct"])
		self.assertEqual(result["provenance"], "[TL]")

	def test_tl_nonideal_but_allowed_stop_is_not_invalidated(self):
		allowed = {"pattern": "SUPPORT_RECLAIM", "stop_pct": 4.0}
		entry._add_risk_contract(allowed)
		self.assertTrue(allowed["risk_contract"]["tradable"])
		self.assertIn("valid_above", allowed["risk_contract"]["status"])

		too_wide = {"pattern": "SUPPORT_RECLAIM", "stop_pct": 5.0}
		entry._add_risk_contract(too_wide)
		self.assertFalse(too_wide["risk_contract"]["tradable"])

	def test_pattern_readiness_never_bypasses_upstream_gate(self):
		pattern = {"pattern": "MA_PULLBACK", "quality": "high", "stop_pct": 2.0}
		entry._add_risk_contract(pattern)
		readiness = entry._determine_readiness([pattern])
		self.assertEqual(readiness["classification"], "candidate_requires_upstream_qualification")
		self.assertEqual(readiness["stage2_trend_template"], "required_not_evaluated")
		self.assertNotEqual(readiness["classification"], "actionable")


if __name__ == "__main__":
	unittest.main()
