import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
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
    "doctrine.show",
    "market.snapshot",
    "market.candidates",
    "ticker.qualify",
    "ticker.setup",
    "ticker.fundamentals",
    "ticker.peers",
    "ticker.risk",
    "ticker.chart",
    "watchlist.show",
    "watchlist.history",
    "watchlist.record",
    "watchlist.annotate",
    "watchlist.export",
}


def run_pipeline(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PIPELINE), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class PublicCliContractTests(unittest.TestCase):
    def test_capabilities_exposes_the_complete_composable_surface(self) -> None:
        completed = run_pipeline("capabilities")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(set(payload), ENVELOPE_KEYS)
        self.assertEqual(payload["schema_version"], "2.0.0")
        self.assertEqual(payload["operation"], "capabilities")
        self.assertEqual(payload["status"], "ok")
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


if __name__ == "__main__":
    unittest.main()
