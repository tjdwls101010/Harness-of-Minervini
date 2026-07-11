#!/usr/bin/env python3
"""Focused offline contracts for RS source ordering and pipeline truthfulness."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MODULES = SCRIPTS / "modules"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(MODULES))

import rs_ranking  # noqa: E402
import trend_template  # noqa: E402
from pipeline import _commands as pipeline_commands  # noqa: E402
from pipeline._gates import compute_hard_gates  # noqa: E402
import utils  # noqa: E402


class FakeRSClient:
	def __init__(self, record=None, error=None):
		self.record = record
		self.error = error
		self.calls = []

	def get(self, ticker):
		self.calls.append(("get", ticker))
		if self.error is not None:
			raise self.error
		return dict(self.record or {})


class RSOrderingTests(unittest.TestCase):
	def setUp(self):
		self.cache_dir = tempfile.TemporaryDirectory()
		self.addCleanup(self.cache_dir.cleanup)
		self.cache_env = mock.patch.dict(os.environ, {"MINERVINI_CACHE_DIR": self.cache_dir.name})
		self.cache_env.start()
		self.addCleanup(self.cache_env.stop)
		utils.configure_cache(False)
		utils.cache_metadata(reset=True)

	def test_valid_package_score_is_authoritative_and_never_calls_proxy(self):
		client = FakeRSClient({"ticker": "CRDO", "rs_rating": 95})
		with mock.patch.object(rs_ranking, "_proxy_result") as proxy:
			result = rs_ranking.resolve_rs_score("crdo", client=client)
		self.assertEqual(result["source"], rs_ranking.SOURCE_BACKEND)
		self.assertEqual(result["score"], 95)
		self.assertFalse(result["provisional"])
		self.assertTrue(result["passed"])
		proxy.assert_not_called()

	def test_missing_package_score_uses_only_labelled_provisional_proxy(self):
		client = FakeRSClient({"ticker": "AAPL", "rs_rating": None})
		proxy_result = {
			"status": "available",
			"score": 81.0,
			"source": rs_ranking.SOURCE_PROXY,
			"provisional": True,
			"passed": True,
			"threshold": rs_ranking.MIN_RS_ELIGIBILITY,
			"proxy": {"eligibility_measure": "12m historical percentile only"},
		}
		with mock.patch.object(rs_ranking, "_proxy_result", return_value=proxy_result):
			result = rs_ranking.resolve_rs_score("AAPL", client=client)
		self.assertEqual(result["source"], rs_ranking.SOURCE_PROXY)
		self.assertTrue(result["provisional"])
		self.assertIn("no backend rating", result["backend"]["reason"])

	def test_both_sources_unavailable_is_unknown_not_a_failed_gate(self):
		client = FakeRSClient(error=ConnectionError("backend offline"))
		with mock.patch.object(rs_ranking, "_proxy_result", side_effect=TimeoutError("prices offline")):
			result = rs_ranking.resolve_rs_score("TEST", client=client)
		self.assertEqual(result["status"], "unavailable")
		self.assertIsNone(result["score"])
		self.assertIsNone(result["passed"])
		self.assertIsNone(result["source"])

	def test_backend_adapter_is_read_through_cached(self):
		client = FakeRSClient({"ticker": "CRDO", "rs_rating": 95})
		with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
			os.environ, {"MINERVINI_CACHE_DIR": directory}
		):
			first = rs_ranking.call_backend(
				"get", symbol="CRDO", params={"ticker": "CRDO"}, client=client
			)
			second = rs_ranking.call_backend(
				"get", symbol="CRDO", params={"ticker": "CRDO"}, client=client
			)
		self.assertEqual(first, second)
		self.assertEqual(client.calls, [("get", "CRDO")])
		events = [event for event in utils.cache_metadata()["events"] if event["source"] == "ibd-rs-rating"]
		self.assertEqual([event["status"] for event in events[-2:]], ["miss", "hit"])

	def test_ca_bundle_selection_never_overrides_caller_choice(self):
		with mock.patch.dict(os.environ, {"SSL_CERT_FILE": "/caller/ca.pem"}):
			client = rs_ranking._get_rs_client()
			self.assertEqual(os.environ["SSL_CERT_FILE"], "/caller/ca.pem")
		self.assertEqual(type(client).__name__, "RS")

	def test_proxy_exposes_role_split_and_never_claims_cross_sectional_rank(self):
		index = pd.date_range("2023-01-02", periods=700, freq="B")
		spy = pd.Series(np.linspace(100.0, 170.0, len(index)), index=index)
		relative = 1.0 + np.linspace(0.0, 1.0, len(index)) + 0.02 * np.sin(np.arange(len(index)) / 17)
		stock = spy * relative
		result = rs_ranking._compute_proxy_metrics(stock, spy)
		self.assertTrue(result["not_cross_sectional_rank"])
		self.assertEqual(result["lookbacks"]["12m"]["role"], "eligibility")
		for label in ("1m", "3m", "6m"):
			self.assertEqual(result["lookbacks"][label]["role"], "timing_only")
		self.assertEqual(result["eligibility_measure"], "12m historical percentile only")


class PipelineTruthTests(unittest.TestCase):
	def setUp(self):
		utils.configure_cache(False)
		utils.cache_metadata(reset=True)

	def test_gate_is_incomplete_when_required_evidence_is_missing(self):
		results = {
			"stage_analysis": {"stage": 2},
			"trend_template": {
				"overall_status": "UNAVAILABLE",
				"overall_pass": None,
				"passed_count": 7,
				"total_count": 8,
				"rs": {"status": "unavailable"},
			},
		}
		hard_fail, gates, overall = compute_hard_gates(results)
		self.assertIsNone(hard_fail)
		self.assertIsNone(overall)
		self.assertEqual(gates[1]["status"], "UNAVAILABLE")

	def test_known_failure_takes_precedence_over_missing_evidence(self):
		results = {
			"stage_analysis": {"stage": 4},
			"trend_template": {"error": "RS source unavailable"},
		}
		hard_fail, _, overall = compute_hard_gates(results)
		self.assertTrue(hard_fail)
		self.assertFalse(overall)

	def test_qualify_emits_incomplete_not_avoid_for_missing_gate_data(self):
		called_scripts = []

		def child(script, _args):
			called_scripts.append(script)
			if "stage_analysis" in script:
				return {"stage": 2}
			if "trend_template" in script:
				return {
					"overall_status": "UNAVAILABLE",
					"overall_pass": None,
					"passed_count": 7,
					"total_count": 8,
					"rs": {"status": "unavailable"},
				}
			return {
				"error": "RS eligibility unavailable",
				"eligibility": {"status": "unavailable", "source": None},
			}

		buffer = io.StringIO()
		with mock.patch.object(pipeline_commands, "_run_script", side_effect=child), contextlib.redirect_stdout(buffer):
			pipeline_commands.cmd_qualify(SimpleNamespace(ticker="TEST", no_cache=False))
		payload = json.loads(buffer.getvalue())
		self.assertEqual(payload["verdict"], "INCOMPLETE")
		self.assertIsNone(payload["overall_pass"])
		self.assertEqual(payload["failed_gates"], [])
		self.assertEqual(payload["unavailable_gates"], ["trend_template"])
		self.assertCountEqual(called_scripts, ["modules/stage_analysis.py", "modules/trend_template.py"])
		self.assertFalse(any("rs_ranking" in script for script in called_scripts))

	def test_discover_isolates_breadth_and_rs_failures_by_section(self):
		def child(script, _args):
			if "market_breadth" in script:
				return {
					"new_high_low": {"unavailable": True, "reason": "finviz offline"},
					"qqq_21ema_switch": {"state": "ON"},
				}
			raise AssertionError(f"unexpected child script: {script}")

		buffer = io.StringIO()
		with (
			mock.patch.object(pipeline_commands, "_run_script", side_effect=child),
			mock.patch.object(pipeline_commands, "call_backend", side_effect=ConnectionError("RS offline")),
			contextlib.redirect_stdout(buffer),
		):
			pipeline_commands.cmd_discover(SimpleNamespace(no_cache=False))
		payload = json.loads(buffer.getvalue())
		self.assertEqual(payload["market_verdict"], "requires_bottom_up_judgment")
		self.assertEqual(payload["regime_status"], "partial")
		self.assertTrue(payload["verdict_evidence"]["axis_availability"]["qqq_information_switch"])
		self.assertFalse(payload["verdict_evidence"]["axis_availability"]["breadth"])
		self.assertNotIn("distribution_days_25d", payload["verdict_evidence"])
		self.assertEqual(payload["breadth"]["unavailable"], "finviz offline")
		self.assertIn("breadth", payload["unavailable"])
		self.assertIn("reference", payload["rs_leaders"]["unavailable"])
		self.assertIn("rs_leaders", payload["unavailable"])
		self.assertEqual(payload["sector_ranking"], [])


class TrendTemplateRSTests(unittest.TestCase):
	def test_missing_rs_is_an_unavailable_criterion_not_a_false_failure(self):
		index = pd.date_range("2024-01-02", periods=320, freq="B")
		close = np.linspace(100.0, 400.0, len(index))
		frame = pd.DataFrame(
			{
				"Open": close - 1.0,
				"High": close + 2.0,
				"Low": close - 2.0,
				"Close": close,
				"Volume": np.full(len(index), 1_000_000),
			},
			index=index,
		)
		ticker = mock.Mock()
		ticker.history.return_value = frame
		captured = []
		unavailable = {
			"status": "unavailable",
			"score": None,
			"source": None,
			"passed": None,
			"backend": {"status": "unavailable"},
			"proxy": {"status": "unavailable"},
		}
		with (
			mock.patch.object(trend_template.yf, "Ticker", return_value=ticker),
			mock.patch.object(trend_template, "resolve_rs_score", return_value=unavailable),
			mock.patch.object(trend_template, "output_json", side_effect=captured.append),
		):
			trend_template.cmd_check(SimpleNamespace(symbol="TEST", period="2y", no_cache=False))
		result = captured[0]
		criterion = next(item for item in result["criteria"] if item["id"] == 8)
		self.assertEqual(criterion["status"], "UNAVAILABLE")
		self.assertIsNone(criterion["passed"])
		self.assertEqual(result["overall_status"], "UNAVAILABLE")
		self.assertIsNone(result["overall_pass"])


if __name__ == "__main__":
	unittest.main()
