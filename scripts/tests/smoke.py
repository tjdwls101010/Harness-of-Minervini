#!/usr/bin/env python3
"""Phase-1 standalone smoke suite for the Minervini code substrate.

The suite intentionally asserts contracts, not market opinions or current values:

* every CLI help path is offline and documents its live flags;
* representative AAPL/SPY commands emit parseable JSON with stable key/types;
* read-through caching demonstrates miss -> hit and ``--no-cache`` bypass;
* fragile discovery sources degrade inside their own sections; and
* a deterministic invalid request emits ``{"error": ...}`` with exit code 1.

Run from any working directory after bootstrap:

    scripts/.venv/bin/python scripts/tests/smoke.py
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES_DIR = REPO_ROOT / "scripts" / "modules"
PIPELINE_PATH = "scripts/pipeline"
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("MINERVINI_SMOKE_TIMEOUT", "150"))


# Every public parser is exercised without network access. Keeping this inventory
# explicit makes addition/removal of a public command a deliberate contract change.
HELP_CASES = {
	"scripts/modules/actions.py": (
		"get-dividends",
		"get-splits",
		"get-capital-gains",
		"get-actions",
		"get-earnings",
		"get-earnings-dates",
		"get-calendar",
		"get-news",
	),
	"scripts/modules/base_count.py": ("count",),
	"scripts/modules/chart_render.py": ("daily", "weekly"),
	"scripts/modules/earnings_acceleration.py": (
		"code33",
		"acceleration",
		"surprise",
		"revisions",
		"valuation",
		"margin",
	),
	"scripts/modules/entry_patterns.py": ("scan", "screen"),
	"scripts/modules/info.py": (
		"get-info",
		"get-fast-info",
		"get-info-fields",
		"get-isin",
		"get-shares",
		"get-shares-full",
		"get-history-metadata",
		"get-history",
		"get-sec-filings",
	),
	"scripts/modules/market_breadth.py": ("breadth",),
	"scripts/modules/market_clock.py": (),
	"scripts/modules/rs_ranking.py": ("score", "screen", "compare"),
	"scripts/modules/sell_signals.py": ("reversal", "extension", "trail", "cascade"),
	"scripts/modules/stage_analysis.py": ("classify", "transitions", "risk"),
	"scripts/modules/tight_closes.py": ("daily", "weekly"),
	"scripts/modules/trend_template.py": ("check",),
	"scripts/modules/vcp.py": ("detect",),
	"scripts/modules/volume_analysis.py": ("analyze", "demand-days", "runrate"),
}


def _command(path: str, *arguments: str) -> list[str]:
	return [sys.executable, str(REPO_ROOT / path), *arguments]


def _base_environment(cache_dir: Path) -> dict[str, str]:
	environment = os.environ.copy()
	environment["MINERVINI_CACHE_DIR"] = str(cache_dir)
	environment["MPLCONFIGDIR"] = str(cache_dir / "mpl")
	environment["PYTHONUTF8"] = "1"
	return environment


def _run(
	path: str,
	*arguments: str,
	cache_dir: Path,
	timeout: int = DEFAULT_TIMEOUT_SECONDS,
	environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
	env = _base_environment(cache_dir)
	if environment:
		env.update(environment)
	return subprocess.run(
		_command(path, *arguments),
		cwd=REPO_ROOT,
		env=env,
		text=True,
		capture_output=True,
		check=False,
		timeout=timeout,
	)


def _json_result(
	test: unittest.TestCase,
	path: str,
	*arguments: str,
	cache_dir: Path,
	timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[subprocess.CompletedProcess[str], dict]:
	result = _run(path, *arguments, cache_dir=cache_dir, timeout=timeout)
	try:
		payload = json.loads(result.stdout)
	except json.JSONDecodeError as exc:
		test.fail(
			f"{path} {' '.join(arguments)} did not emit one JSON document "
			f"(exit={result.returncode}, stderr={result.stderr!r}, stdout={result.stdout!r}): {exc}"
		)
	if not isinstance(payload, dict):
		test.fail(f"{path} {' '.join(arguments)} emitted {type(payload).__name__}; expected a JSON object")
	return result, payload


def _is_number(value: object) -> bool:
	return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require(test: unittest.TestCase, payload: dict, key: str, expected_type) -> object:
	test.assertIn(key, payload, f"missing required key {key!r}; keys={sorted(payload)}")
	value = payload[key]
	if expected_type == "number":
		test.assertTrue(_is_number(value), f"{key} must be numeric, got {type(value).__name__}")
	elif expected_type == "optional_number":
		test.assertTrue(value is None or _is_number(value), f"{key} must be numeric/null, got {type(value).__name__}")
	elif expected_type == "optional_bool":
		test.assertTrue(value is None or isinstance(value, bool), f"{key} must be boolean/null")
	elif isinstance(expected_type, tuple):
		test.assertIsInstance(value, expected_type, f"{key} has wrong type")
	else:
		test.assertIsInstance(value, expected_type, f"{key} has wrong type")
	return value


def _require_success(test: unittest.TestCase, result: subprocess.CompletedProcess[str], payload: dict) -> None:
	test.assertEqual(
		result.returncode,
		0,
		f"structured command failed: payload={payload!r}, stderr={result.stderr!r}",
	)
	test.assertNotIn("error", payload, f"success response unexpectedly contains error: {payload!r}")


def _validate_actions(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "as_of_date_et", str)
	_require(test, payload, "next_earnings_date", (str, type(None)))
	_require(test, payload, "days_until", (int, type(None)))
	_require(test, payload, "doctrine", str)
	_require(test, payload, "provenance", dict)


def _validate_base_count(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "current_base_number", int)
	_require(test, payload, "base_history", list)
	_require(test, payload, "base_stage_assessment", str)
	_require(test, payload, "doctrine", dict)


def _validate_chart(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "timeframe", str)
	output = _require(test, payload, "output", str)
	png_bytes = _require(test, payload, "png_bytes", int)
	_require(test, payload, "moving_averages", list)
	_require(test, payload, "doctrine", str)
	path = Path(output)
	test.assertTrue(path.is_file(), f"chart output does not exist: {path}")
	test.assertGreater(png_bytes, 0, f"chart output is empty: {path}")
	test.assertEqual(path.stat().st_size, png_bytes, "reported PNG byte count does not match the file")
	with path.open("rb") as handle:
		test.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n", "chart output is not a PNG")


def _validate_earnings(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "code33_status", str)
	_require(test, payload, "code33_data_complete", bool)
	_require(test, payload, "aligned_code33", dict)
	_require(test, payload, "compressed", dict)
	_require(test, payload, "doctrine", str)


def _validate_entry(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "active_patterns", list)
	_require(test, payload, "pattern_count", int)
	_require(test, payload, "setup_readiness", dict)
	_require(test, payload, "latest_bar_quantifiers", dict)
	_require(test, payload, "doctrine", str)


def _validate_history(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "row_count", int)
	history = _require(test, payload, "history", list)
	test.assertGreater(len(history), 0, "fixed historical window returned no rows")
	test.assertIsInstance(history[0], dict)
	for key in ("date", "Open", "High", "Low", "Close", "Volume"):
		test.assertIn(key, history[0])
	_require(test, payload, "doctrine", str)
	_require(test, payload, "provenance", dict)


def _validate_breadth(test: unittest.TestCase, payload: dict) -> None:
	for key in ("new_high_low", "advancing_declining", "sma50", "sma200", "qqq_21ema_switch"):
		_require(test, payload, key, dict)
	_require(test, payload, "doctrine", str)
	_require(test, payload, "provenance", dict)


def _validate_clock(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "now_local", str)
	_require(test, payload, "now_et", str)
	_require(test, payload, "market_open", bool)
	_require(test, payload, "session", str)
	_require(test, payload, "last_completed_session", str)
	_require(test, payload, "cache_entries", int)


def _validate_rs(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "status", str)
	_require(test, payload, "rs_rating", "optional_number")
	_require(test, payload, "eligibility", dict)
	_require(test, payload, "doctrine", str)
	_require(test, payload, "provenance", dict)


def _validate_sell(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "command", str)
	_require(test, payload, "items", list)
	_require(test, payload, "summary", dict)
	_require(test, payload, "extension_context", dict)
	_require(test, payload, "doctrine", str)
	_require(test, payload, "provenance", dict)


def _validate_stage(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "stage", int)
	_require(test, payload, "stage_name", str)
	_require(test, payload, "structural_reads", dict)
	_require(test, payload, "doctrine", str)


def _validate_tight(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "interval", str)
	_require(test, payload, "tight_close_clusters", list)
	_require(test, payload, "latest_bar_quantifiers", dict)
	_require(test, payload, "compressed", dict)
	_require(test, payload, "doctrine", dict)


def _validate_trend(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "criteria", list)
	_require(test, payload, "passed_count", int)
	_require(test, payload, "evaluated_count", int)
	_require(test, payload, "total_count", int)
	_require(test, payload, "overall_pass", "optional_bool")
	_require(test, payload, "rs", dict)
	_require(test, payload, "doctrine", str)


def _validate_vcp(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "vcp_detected", bool)
	_require(test, payload, "contractions_count", int)
	_require(test, payload, "setup_readiness", dict)
	_require(test, payload, "doctrine", dict)
	_require(test, payload, "provenance", dict)


def _validate_volume(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "symbol", str)
	_require(test, payload, "accumulation_distribution_rating", str)
	_require(test, payload, "up_down_volume_ratio_50d", "optional_number")
	_require(test, payload, "up_down_volume_ratio_50d_status", str)
	_require(test, payload, "recent_up_volume_evidence", bool)
	_require(test, payload, "breakout_volume_confirmation", "optional_bool")
	test.assertNotIn("climactic_volume", payload)
	_require(test, payload, "volume_bands", dict)
	_require(test, payload, "closing_range_pct", "optional_number")
	_require(test, payload, "adr_pct_10d", "optional_number")
	_require(test, payload, "doctrine", str)
	_require(test, payload, "provenance", dict)


def _validate_qualify(test: unittest.TestCase, payload: dict) -> None:
	_require(test, payload, "ticker", str)
	_require(test, payload, "verdict", str)
	_require(test, payload, "overall_pass", "optional_bool")
	_require(test, payload, "failed_gates", list)
	_require(test, payload, "hard_gates", list)
	_require(test, payload, "rs_rating", "optional_number")
	_require(test, payload, "metadata", dict)


class OfflineContractSmoke(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls._temporary = tempfile.TemporaryDirectory(prefix="minervini-help-smoke-")
		cls.cache_dir = Path(cls._temporary.name) / "cache"

	@classmethod
	def tearDownClass(cls):
		cls._temporary.cleanup()

	def test_all_help_paths_are_offline(self):
		blocked_network = {
			"MINERVINI_NO_CACHE": "1",
			"HTTP_PROXY": "http://127.0.0.1:9",
			"HTTPS_PROXY": "http://127.0.0.1:9",
			"ALL_PROXY": "http://127.0.0.1:9",
			"NO_PROXY": "",
		}
		for path, subcommands in HELP_CASES.items():
			with self.subTest(path=path, command="top-level"):
				result = _run(path, "--help", cache_dir=self.cache_dir, timeout=30, environment=blocked_network)
				self.assertEqual(result.returncode, 0, result.stderr)
				self.assertIn("usage:", result.stdout.lower())
				self.assertEqual(
					result.stderr.replace("Matplotlib is building the font cache; this may take a moment.\n", ""),
					"",
				)
			for subcommand in subcommands:
				with self.subTest(path=path, command=subcommand):
					result = _run(
						path,
						subcommand,
						"--help",
						cache_dir=self.cache_dir,
						timeout=30,
						environment=blocked_network,
					)
					self.assertEqual(result.returncode, 0, result.stderr)
					self.assertIn("usage:", result.stdout.lower())
					self.assertIn("--no-cache", result.stdout)
					self.assertEqual(result.stderr, "")

		# market_clock has no subparser, so its cache escape hatch is top-level.
		clock_help = _run(
			"scripts/modules/market_clock.py",
			"--help",
			cache_dir=self.cache_dir,
			timeout=30,
			environment=blocked_network,
		)
		self.assertIn("--no-cache", clock_help.stdout)

		for subcommand in ("qualify", "discover"):
			with self.subTest(path=PIPELINE_PATH, command=subcommand):
				result = _run(
					PIPELINE_PATH,
					subcommand,
					"--help",
					cache_dir=self.cache_dir,
					timeout=30,
					environment=blocked_network,
				)
				self.assertEqual(result.returncode, 0, result.stderr)
				self.assertIn("usage:", result.stdout.lower())
				self.assertEqual(result.stderr, "")

		pipeline_help = _run(
			PIPELINE_PATH,
			"--help",
			cache_dir=self.cache_dir,
			timeout=30,
			environment=blocked_network,
		)
		self.assertNotIn("analyze-everything", pipeline_help.stdout.lower())

	def test_every_declared_argument_has_live_help_text(self):
		for relative_path in HELP_CASES:
			path = REPO_ROOT / relative_path
			tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
			for node in ast.walk(tree):
				if not (
					isinstance(node, ast.Call)
					and isinstance(node.func, ast.Attribute)
					and node.func.attr == "add_argument"
				):
					continue
				with self.subTest(path=relative_path, line=node.lineno):
					help_values = [keyword.value for keyword in node.keywords if keyword.arg == "help"]
					self.assertEqual(len(help_values), 1, "every positional and flag needs one help description")
					self.assertFalse(
						isinstance(help_values[0], ast.Constant) and not str(help_values[0].value).strip(),
						"help description must not be empty",
					)

	def test_error_is_json_and_exit_one(self):
		# Usage errors are part of the same public contract; stock argparse would
		# otherwise leak text to stderr and exit 2 before a command handler runs.
		usage_error_cases = [
			("scripts/modules/actions.py", ("not-a-command",)),
			("scripts/modules/info.py", ("not-a-command",)),
			("scripts/modules/market_breadth.py", ("not-a-command",)),
			("scripts/modules/market_clock.py", ("--not-a-flag",)),
			("scripts/modules/rs_ranking.py", ("not-a-command",)),
			("scripts/modules/trend_template.py", ("not-a-command",)),
			("scripts/modules/volume_analysis.py", ("not-a-command",)),
			(PIPELINE_PATH, ("not-a-command",)),
		]
		for path, arguments in usage_error_cases:
			with self.subTest(path=path, arguments=arguments):
				usage_result, usage_payload = _json_result(
					self, path, *arguments, cache_dir=self.cache_dir, timeout=30
				)
				self.assertEqual(usage_result.returncode, 1)
				self.assertEqual(usage_result.stderr, "")
				self.assertEqual(set(usage_payload), {"error"})
				self.assertIsInstance(usage_payload["error"], str)

		result, payload = _json_result(
			self,
			"scripts/modules/info.py",
			"get-history",
			"AAPL",
			"--start",
			"2026-07-10",
			"--end",
			"2026-07-10",
			"--no-cache",
			cache_dir=self.cache_dir,
		)
		self.assertEqual(result.returncode, 1)
		self.assertEqual(result.stderr, "")
		self.assertEqual(set(payload), {"error"})
		self.assertIsInstance(payload["error"], str)


class LiveSchemaSmoke(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls._temporary = tempfile.TemporaryDirectory(prefix="minervini-live-smoke-")
		cls.root = Path(cls._temporary.name)
		cls.cache_dir = cls.root / "cache"
		cls.chart_path = cls.root / "AAPL-daily.png"

	@classmethod
	def tearDownClass(cls):
		cls._temporary.cleanup()

	def test_live_aapl_spy_schema_matrix(self):
		cases = [
			(
				"actions earnings proximity",
				"scripts/modules/actions.py",
				("get-earnings-dates", "AAPL", "--limit", "12", "--days-until"),
				_validate_actions,
			),
			("base count", "scripts/modules/base_count.py", ("count", "AAPL"), _validate_base_count),
			(
				"daily chart",
				"scripts/modules/chart_render.py",
				("daily", "AAPL", "--period", "3mo", "--out", str(self.chart_path)),
				_validate_chart,
			),
			("Code 33", "scripts/modules/earnings_acceleration.py", ("code33", "AAPL"), _validate_earnings),
			("entry scan", "scripts/modules/entry_patterns.py", ("scan", "AAPL"), _validate_entry),
			(
				"fixed-window history",
				"scripts/modules/info.py",
				("get-history", "SPY", "--start", "2025-01-02", "--end", "2025-02-01"),
				_validate_history,
			),
			("market breadth", "scripts/modules/market_breadth.py", ("breadth",), _validate_breadth),
			("market clock", "scripts/modules/market_clock.py", (), _validate_clock),
			("RS score", "scripts/modules/rs_ranking.py", ("score", "AAPL"), _validate_rs),
			("sell reversal", "scripts/modules/sell_signals.py", ("reversal", "AAPL"), _validate_sell),
			("stage classification", "scripts/modules/stage_analysis.py", ("classify", "AAPL"), _validate_stage),
			("tight closes", "scripts/modules/tight_closes.py", ("daily", "AAPL"), _validate_tight),
			("trend template", "scripts/modules/trend_template.py", ("check", "AAPL"), _validate_trend),
			("VCP", "scripts/modules/vcp.py", ("detect", "AAPL"), _validate_vcp),
			("volume", "scripts/modules/volume_analysis.py", ("analyze", "SPY"), _validate_volume),
			("canonical qualify", PIPELINE_PATH, ("qualify", "AAPL"), _validate_qualify),
		]

		for name, path, arguments, validator in cases:
			with self.subTest(case=name):
				result, payload = _json_result(self, path, *arguments, cache_dir=self.cache_dir)
				_require_success(self, result, payload)
				validator(self, payload)

	def test_yfinance_cache_miss_hit_and_bypass(self):
		with tempfile.TemporaryDirectory(prefix="minervini-cache-contract-") as temporary:
			cache_dir = Path(temporary)
			arguments = ("get-history", "SPY", "--start", "2025-01-02", "--end", "2025-02-01")
			first_result, first = _json_result(
				self, "scripts/modules/info.py", *arguments, cache_dir=cache_dir
			)
			second_result, second = _json_result(
				self, "scripts/modules/info.py", *arguments, cache_dir=cache_dir
			)
			bypass_result, bypass = _json_result(
				self, "scripts/modules/info.py", *arguments, "--no-cache", cache_dir=cache_dir
			)
			for result, payload in ((first_result, first), (second_result, second), (bypass_result, bypass)):
				_require_success(self, result, payload)
				_validate_history(self, payload)

			first_cache = _require(self, first, "_cache", dict)
			second_cache = _require(self, second, "_cache", dict)
			bypass_cache = _require(self, bypass, "_cache", dict)
			self.assertGreaterEqual(first_cache["counts"]["miss"], 1)
			self.assertTrue(
				any(event.get("source") == "yfinance" and event.get("status") == "hit" for event in second_cache["events"]),
				f"second invocation did not hit yfinance cache: {second_cache!r}",
			)
			self.assertFalse(bypass_cache["enabled"])
			self.assertTrue(
				any(event.get("source") == "yfinance" and event.get("status") == "bypass" for event in bypass_cache["events"]),
				f"--no-cache did not bypass yfinance cache: {bypass_cache!r}",
			)

	def test_authoritative_rs_package_miss_hit_and_bypass(self):
		with tempfile.TemporaryDirectory(prefix="minervini-rs-cache-") as temporary:
			cache_dir = Path(temporary)
			first_result, first = _json_result(
				self, "scripts/modules/rs_ranking.py", "score", "AAPL", cache_dir=cache_dir
			)
			second_result, second = _json_result(
				self, "scripts/modules/rs_ranking.py", "score", "AAPL", cache_dir=cache_dir
			)
			bypass_result, bypass = _json_result(
				self,
				"scripts/modules/rs_ranking.py",
				"score",
				"AAPL",
				"--no-cache",
				cache_dir=cache_dir,
			)
			_require_success(self, first_result, first)
			_require_success(self, second_result, second)
			_require_success(self, bypass_result, bypass)
			_validate_rs(self, first)
			_validate_rs(self, second)
			_validate_rs(self, bypass)
			for payload in (first, second, bypass):
				self.assertEqual(
					payload["eligibility"].get("source"),
					"ibd_rs_rating_backend",
					"Phase-1 acceptance requires a valid score from the user's package; the labelled proxy is tested separately but cannot substitute for this live gate",
				)
				self.assertFalse(payload["eligibility"].get("provisional"))

			first_cache = _require(self, first, "_cache", dict)
			second_cache = _require(self, second, "_cache", dict)
			bypass_cache = _require(self, bypass, "_cache", dict)
			self.assertTrue(any(
				event.get("source") == "ibd-rs-rating" and event.get("status") == "miss"
				for event in first_cache["events"]
			))
			self.assertTrue(any(
				event.get("source") == "ibd-rs-rating" and event.get("status") == "hit"
				for event in second_cache["events"]
			))
			self.assertFalse(bypass_cache["enabled"])
			self.assertTrue(any(
				event.get("source") == "ibd-rs-rating" and event.get("status") == "bypass"
				for event in bypass_cache["events"]
			))


class FragileSourceIsolationSmoke(unittest.TestCase):
	def test_discover_keeps_failures_inside_sections(self):
		# Import through the public package layout used by the pipeline executable.
		sys.path.insert(0, str(REPO_ROOT / "scripts"))
		sys.path.insert(0, str(MODULES_DIR))
		from pipeline import _commands  # noqa: E402

		def fake_script(path, _arguments):
			if path.endswith("market_breadth.py"):
				return {
					"new_high_low": {"unavailable": True, "reason": "simulated Finviz outage"},
					"advancing_declining": {"unavailable": True, "reason": "simulated Finviz outage"},
					"sma50": {"unavailable": True, "reason": "simulated Finviz outage"},
					"sma200": {"unavailable": True, "reason": "simulated Finviz outage"},
					"qqq_21ema_switch": {"state": "ON"},
				}
			raise AssertionError(f"unexpected child script: {path}")

		def failing_backend(_function, **_kwargs):
			raise TimeoutError("simulated RS outage")

		stdout = io.StringIO()
		with (
			mock.patch.object(_commands, "_run_script", side_effect=fake_script),
			mock.patch.object(_commands, "call_backend", side_effect=failing_backend),
			contextlib.redirect_stdout(stdout),
		):
			_commands.cmd_discover(types.SimpleNamespace())

		payload = json.loads(stdout.getvalue())
		self.assertNotIn("error", payload)
		breadth = _require(self, payload, "breadth", dict)
		rs_leaders = _require(self, payload, "rs_leaders", dict)
		self.assertTrue(_contains_unavailable(breadth), f"Finviz outage vanished from breadth: {breadth!r}")
		self.assertTrue(_contains_unavailable(rs_leaders), f"RS outage vanished from leaders: {rs_leaders!r}")


def _contains_unavailable(value: object) -> bool:
	if isinstance(value, dict):
		if "unavailable" in value:
			return True
		return any(_contains_unavailable(item) for item in value.values())
	if isinstance(value, list):
		return any(_contains_unavailable(item) for item in value)
	return False


if __name__ == "__main__":
	unittest.main(verbosity=2)
