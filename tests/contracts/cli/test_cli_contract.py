from tests.paths import ROOT

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from scripts.minervini.capabilities import CAPABILITIES
from scripts.minervini.cli import build_parser, format_payload
from scripts.minervini.clock import resolve_as_of
from tests.attestations import envelopes


PIPELINE = ROOT / "scripts" / "pipeline"
ENVELOPE_KEYS = {
    "schema_version",
    "operation",
    "request",
    "as_of",
    "status",
    "data",
    "signals",
    "missing",
    "sources",
    "doctrine_ids",
    "next_capabilities",
    "side_effects",
}
EXPECTED_CAPABILITIES = {
    "capabilities",
    "describe",
    "health",
    "clock",
    "doctrine.list",
    "doctrine.show",
    "market.snapshot",
    "market.candidates",
    "ticker.qualify",
    "ticker.swings",
    "ticker.power-play",
    "ticker.setup",
    "ticker.fundamentals",
    "ticker.cik",
    "ticker.peers",
    "ticker.risk",
    "ticker.chart",
    "watchlist.show",
    "watchlist.history",
    "watchlist.record",
    "watchlist.annotate",
    "watchlist.export",
}
# Every capability needs a path here, or the parity sweeps below silently skip it: ticker.swings
# was in EXPECTED_CAPABILITIES and not here, so its help and its parser were never checked. The
# first test in the class below is what makes that a failure rather than a quiet omission.
COMMAND_PATHS = {
    "capabilities": ("capabilities",),
    "describe": ("describe",),
    "health": ("health",),
    "clock": ("clock",),
    "doctrine.list": ("doctrine", "list"),
    "doctrine.show": ("doctrine", "show"),
    "market.snapshot": ("market", "snapshot"),
    "market.candidates": ("market", "candidates"),
    "ticker.qualify": ("ticker", "qualify"),
    "ticker.swings": ("ticker", "swings"),
    "ticker.power-play": ("ticker", "power-play"),
    "ticker.setup": ("ticker", "setup"),
    "ticker.fundamentals": ("ticker", "fundamentals"),
    "ticker.cik": ("ticker", "cik"),
    "ticker.peers": ("ticker", "peers"),
    "ticker.risk": ("ticker", "risk"),
    "ticker.chart": ("ticker", "chart"),
    "watchlist.show": ("watchlist", "show"),
    "watchlist.history": ("watchlist", "history"),
    "watchlist.record": ("watchlist", "record"),
    "watchlist.annotate": ("watchlist", "annotate"),
    "watchlist.export": ("watchlist", "export"),
}


def run_pipeline(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PIPELINE), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def command_parser(*tokens: str) -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = build_parser()
    for token in tokens:
        subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        parser = subparsers.choices[token]
    return parser


class PublicCliContractTests(unittest.TestCase):
    def test_every_capability_has_a_command_path_so_none_can_skip_the_sweeps(self) -> None:
        """The sweeps below iterate COMMAND_PATHS, so anything missing from it is not checked.

        ticker.swings was added to the capability set and not here, and every contract test kept
        passing while its help and its parser went unexamined.
        """

        self.assertEqual(set(COMMAND_PATHS), EXPECTED_CAPABILITIES)
        self.assertEqual(set(COMMAND_PATHS), set(CAPABILITIES))

    def test_every_leaf_help_is_a_complete_just_in_time_contract(self) -> None:
        for capability, path in COMMAND_PATHS.items():
            with self.subTest(capability=capability):
                help_text = command_parser(*path).format_help()
                self.assertIn(CAPABILITIES[capability].summary, help_text)
                self.assertIn("Output", help_text)
                self.assertIn("Time and data limits", help_text)
                self.assertIn("Envelope status", help_text)
                self.assertIn("Exit codes", help_text)
                self.assertIn("Side effects", help_text)
                self.assertIn("Examples (run from the repository root)", help_text)
                self.assertIn("scripts/.venv/bin/python scripts/pipeline", help_text)

    def test_help_actions_and_describe_inputs_share_one_capability_contract(self) -> None:
        for capability, path in COMMAND_PATHS.items():
            with self.subTest(capability=capability):
                parser = command_parser(*path)
                actions = {action.dest: action for action in parser._actions if action.dest != "help"}
                self.assertEqual(set(actions), set(CAPABILITIES[capability].inputs))
                for name, specification in CAPABILITIES[capability].inputs.items():
                    self.assertEqual(actions[name].help, specification["description"])
                    if "choices" in specification:
                        self.assertEqual(list(actions[name].choices), specification["choices"])
                    if "default" in specification:
                        self.assertEqual(actions[name].default, specification["default"])

    def test_compact_format_removes_only_verbose_detail_not_decision_meaning(self) -> None:
        payload = {
            "data": {"verdict": "WAIT", "basis": {"detail": "verbose"}, "nested": {"source_row": {"raw": 1}, "keep": 2}},
            "signals": [{"id": "setup", "state": "wait"}],
            "missing": [{"id": "chart", "required": True}],
            "sources": [{"provider": "fixture", "as_of": "2026-08-14", "stale": False, "coverage": {"verbose": True}}],
        }

        full = format_payload(payload, "full")
        compact = format_payload(payload, "compact")

        self.assertEqual(full, payload)
        self.assertEqual(compact["data"]["verdict"], full["data"]["verdict"])
        self.assertEqual(compact["signals"], full["signals"])
        self.assertEqual(compact["missing"], full["missing"])
        self.assertNotIn("basis", compact["data"])
        self.assertNotIn("source_row", compact["data"]["nested"])
        self.assertNotIn("coverage", compact["sources"][0])

    def test_capabilities_exposes_the_complete_composable_surface(self) -> None:
        completed = run_pipeline("capabilities")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(set(payload), ENVELOPE_KEYS)
        self.assertEqual(payload["schema_version"], "2.0.0")
        self.assertEqual(payload["operation"], "capabilities")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["as_of"]["date"], resolve_as_of().date.isoformat())
        self.assertEqual(
            {item["name"] for item in payload["data"]["capabilities"]},
            EXPECTED_CAPABILITIES,
        )
        for item in payload["data"]["capabilities"]:
            self.assertIsInstance(item["summary"], str)
            self.assertIsInstance(item["side_effecting"], bool)

    def test_describe_is_the_machine_readable_source_for_one_capability(self) -> None:
        completed = run_pipeline("describe", "ticker.risk")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(set(payload), ENVELOPE_KEYS)
        self.assertEqual(payload["operation"], "describe")
        self.assertEqual(payload["request"]["capability"], "ticker.risk")
        self.assertEqual(payload["data"]["name"], "ticker.risk")
        self.assertIn("inputs", payload["data"])
        self.assertIn("output", payload["data"])
        self.assertIn("prerequisites", payload["data"])
        self.assertIn("side_effects", payload["data"])
        self.assertIn("errors", payload["data"])
        self.assertEqual(set(payload["data"]["exit_codes"]), {"0", "2", "3"})

    def test_explicit_completed_current_price_can_trigger_the_active_hard_stop(self) -> None:
        completed = run_pipeline(
            "ticker",
            "risk",
            "TEST",
            "--mode",
            "active",
            "--entry-price",
            "200",
            "--entry-date",
            "2026-08-10",
            "--stop-price",
            "188",
            "--current-price",
            "187",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertIn("completed_stop_breach", payload["data"]["failed"])

    def test_active_risk_help_documents_the_full_stop_path_contract(self) -> None:
        help_text = command_parser("ticker", "risk").format_help()

        self.assertIn("--stop-effective-date", help_text)
        self.assertIn("completed daily Low", help_text)
        self.assertIn("cannot establish HOLD", help_text)
        self.assertIn("defaults to --entry-date", help_text)

    def test_market_candidates_help_documents_bounded_exclusion_evidence(self) -> None:
        help_text = command_parser("market", "candidates").format_help()

        self.assertIn("bounded exclusion summary", help_text)
        self.assertIn("at most min(limit, 20) representative records", help_text)

    def test_help_is_plain_text_and_does_not_emit_json(self) -> None:
        completed = run_pipeline("ticker", "risk", "--help")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--as-of", completed.stdout)
        self.assertIn("--mode", completed.stdout)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(completed.stdout)

    def test_invalid_capability_is_a_json_error_with_exit_two(self) -> None:
        completed = run_pipeline("describe", "ticker.everything")

        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(set(payload), ENVELOPE_KEYS)
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["data"]["error"]["code"], "invalid_request")
        self.assertEqual(payload["data"]["error"]["field"], "capability")
        self.assertFalse(payload["data"]["error"]["retryable"])
        self.assertEqual(completed.stderr, "")

    def test_clock_is_a_real_operation_with_an_explicit_completed_cutoff(self) -> None:
        completed = run_pipeline("clock", "--as-of", "2025-12-31")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["as_of"]["mode"], "explicit")
        self.assertEqual(payload["as_of"]["date"], "2025-12-31")

    def test_incomplete_active_risk_is_valid_json_with_exit_zero(self) -> None:
        completed = run_pipeline("ticker", "risk", "TEST", "--mode", "active", "--entry-price", "100")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertEqual({item["id"] for item in payload["missing"]}, {"entry_date", "stop_or_invalidation", "current_price"})

    def test_prospective_risk_derives_its_component_from_complete_price_inputs(self) -> None:
        as_of = resolve_as_of().date.isoformat()
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, item in enumerate(envelopes(ticker="TEST", as_of=as_of)):
                path = pathlib.Path(directory) / f"{index}.json"
                path.write_text(json.dumps(item), encoding="utf-8")
                paths.append(str(path))
            completed = run_pipeline(
                "ticker",
                "risk",
                "TEST",
                *(argument for path in paths for argument in ("--evidence", path)),
                "--entry-price",
                "100",
                "--stop-price",
                "94",
                "--upside-price",
                "112",
                "--average-gain-pct",
                "20",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["data"]["verdict"], "BUY-READY")
        self.assertEqual(payload["data"]["components"]["risk"], "pass")

    def test_the_component_words_alone_do_not_reach_buy_ready_from_the_command_line(self) -> None:
        """The whole defect, at the surface a person actually types it at."""

        completed = run_pipeline(
            "ticker",
            "risk",
            "TEST",
            "--market-state",
            "favorable",
            "--eligibility-state",
            "eligible",
            "--setup-state",
            "ready",
            "--fundamentals-state",
            "supports_convergence",
            "--entry-price",
            "100",
            "--stop-price",
            "94",
            "--upside-price",
            "112",
            "--average-gain-pct",
            "20",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertEqual(
            {item["id"]: item["reason"] for item in payload["missing"]},
            {plane: "unattested_state_word" for plane in ("market", "eligibility", "setup", "fundamentals")},
        )

    def test_evidence_that_is_not_a_capability_envelope_is_a_request_error(self) -> None:
        completed = run_pipeline("ticker", "risk", "TEST", "--evidence", "no-such-file.json")

        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["data"]["error"]["field"], "evidence")

    def test_invalid_as_of_is_a_request_error_not_an_internal_error(self) -> None:
        completed = run_pipeline("clock", "--as-of", "not-a-date")

        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["data"]["error"]["field"], "as_of")


if __name__ == "__main__":
    unittest.main()
