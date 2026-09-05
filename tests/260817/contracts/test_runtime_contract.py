from __future__ import annotations

from tests.paths import ROOT

from importlib.metadata import version

import unittest


class RuntimeDependencyContractTests(unittest.TestCase):
    def test_first_party_rs_provider_and_runtime_pin_are_both_version_050(self) -> None:
        requirements = (ROOT / "scripts" / "requirements.txt").read_text(encoding="utf-8").splitlines()

        self.assertIn("ibd-rs-rating==0.5.0", requirements)
        self.assertEqual(version("ibd-rs-rating"), "0.5.0")


if __name__ == "__main__":
    unittest.main()
