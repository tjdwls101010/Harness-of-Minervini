"""Discovering the contract cannot depend on a provider cache neither command opens.

`capabilities` and `describe` answer from the registry. They read no market data, take no
runtime, and are the two commands an analyst runs first -- often precisely because something
else is broken and they need to see what the interface offers.

They were routed only in `cli.dispatch`, which returned them before a runtime existed. Moving
them into `execute` so both public seams agree put them behind `Runtime(cache=ProviderCache())`,
and a cache directory the process cannot resolve then turned offline contract discovery into
an `internal_error`. The fix is not to stop building the cache; it is that these two answer
before anything is built for them, because nothing is.
"""

from __future__ import annotations

from tests.paths import ROOT

import json
import os

import subprocess
import unittest


PYTHON = ROOT / "scripts" / ".venv" / "bin" / "python"
PIPELINE = ROOT / "scripts" / "pipeline"
# A path whose user does not exist, so expanding it raises rather than returning a directory
# that could be created. This is the shape a stale exported setting takes on a new machine.
UNRESOLVABLE = "~minervini-no-such-user/cache"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON), str(PIPELINE), *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
        env={**os.environ, "MINERVINI_CACHE_DIR": UNRESOLVABLE},
    )


class TheRegistryAnswersWhateverTheCacheSettingSays(unittest.TestCase):
    def test_capabilities_lists_the_surface(self) -> None:
        completed = run("capabilities")

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("ticker.risk", {item["name"] for item in payload["data"]["capabilities"]})

    def test_describe_returns_the_contract(self) -> None:
        completed = run("describe", "ticker.risk")

        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["name"], "ticker.risk")

    def test_a_capability_that_does_read_providers_still_reports_the_setting(self) -> None:
        """The cache is not being made optional -- only moved behind the two that never use it."""

        completed = run("ticker", "qualify", "NVDA")

        self.assertEqual(completed.returncode, 3, completed.stdout)
        self.assertEqual(json.loads(completed.stdout)["data"]["error"]["code"], "internal_error")


if __name__ == "__main__":
    unittest.main()
