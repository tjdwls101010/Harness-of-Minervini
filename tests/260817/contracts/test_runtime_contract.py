from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class RuntimeDependencyContractTests(unittest.TestCase):
    def test_first_party_rs_provider_and_runtime_pin_are_both_version_050(self) -> None:
        requirements = (ROOT / "scripts" / "requirements.txt").read_text(encoding="utf-8").splitlines()

        self.assertIn("ibd-rs-rating==0.5.0", requirements)
        self.assertEqual(version("ibd-rs-rating"), "0.5.0")


if __name__ == "__main__":
    unittest.main()
