"""Discovery must work on a machine that cannot import the plotting stack."""

from __future__ import annotations

from tests.paths import ROOT

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PYTHON = ROOT / "scripts" / ".venv" / "bin" / "python"
PIPELINE = ROOT / "scripts" / "pipeline"
BLOCKED = ("matplotlib", "mplfinance")


def _run_shadowed(command: list[str]) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as shadow:
        for name in BLOCKED:
            # A stub module earlier on sys.path reproduces a machine where the
            # plotting stack is absent or refuses to import.
            (Path(shadow) / f"{name}.py").write_text(f'raise ImportError("{name} is unavailable here")\n')
        environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([shadow, str(ROOT / "scripts")]),
            "MPLCONFIGDIR": shadow,
        }
        return subprocess.run(command, capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=environment)


def run_without_plotting(*arguments: str) -> subprocess.CompletedProcess[str]:
    return _run_shadowed([str(PYTHON), str(PIPELINE), *arguments])


def run_without_plotting_python(source: str) -> subprocess.CompletedProcess[str]:
    return _run_shadowed([str(PYTHON), "-c", source])


class OfflineEntrypointTests(unittest.TestCase):
    def test_the_plotting_stack_really_is_blocked_for_these_runs(self) -> None:
        # Asserting the real install exists would fail on the very machine this
        # feature is for, so the probe checks the shadow instead.
        probe = run_without_plotting_python("import matplotlib")

        self.assertNotEqual(probe.returncode, 0)
        self.assertIn("is unavailable here", probe.stderr)

    def test_capabilities_discovery_survives_a_missing_plotting_stack(self) -> None:
        completed = run_without_plotting("capabilities")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("ticker.chart", [item["name"] for item in payload["data"]["capabilities"]])

    def test_help_survives_a_missing_plotting_stack(self) -> None:
        completed = run_without_plotting("ticker", "chart", "--help")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--output-dir", completed.stdout)

    def test_a_chart_request_reports_the_missing_renderer_instead_of_crashing(self) -> None:
        completed = run_without_plotting("ticker", "chart", "AAPL", "--format", "compact")

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "unavailable")
        self.assertIn("chart_renderer", [item["id"] for item in payload["missing"]])


if __name__ == "__main__":
    unittest.main()
