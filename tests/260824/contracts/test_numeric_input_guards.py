"""A number that is not a number must produce one envelope, never a traceback."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / ".venv" / "bin" / "python"
PIPELINE = ROOT / "scripts" / "pipeline"
POSITION = ("ticker", "risk", "TEST", "--mode", "active", "--entry-price", "100", "--entry-date", "2026-08-10")


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON), str(PIPELINE), *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT / "scripts")},
    )


class NumericInputGuardTests(unittest.TestCase):
    def test_an_infinite_price_is_a_request_error_envelope(self) -> None:
        completed = run(*POSITION, "--invalidation-price", "inf")

        self.assertEqual(completed.returncode, 2, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["data"]["error"]["code"], "invalid_request")

    def test_a_negative_stop_is_a_request_error_envelope(self) -> None:
        completed = run(*POSITION, "--stop-price", "-5")

        self.assertEqual(completed.returncode, 2, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "needs_input")

    def test_a_nan_price_is_a_request_error_envelope(self) -> None:
        completed = run(*POSITION, "--stop-price", "nan")

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "needs_input")


if __name__ == "__main__":
    unittest.main()
