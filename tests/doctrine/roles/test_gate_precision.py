"""A gate compares what was measured, not a tidied version of it.

Rounding before a comparison is a proximity tolerance wearing a display concern's
clothes: it lets a value past a limit it did not actually meet, and then reports the
rounded number so the pass looks correct.
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.risk import reduce_risk
from tests.attestations import planes


def converged(**risk: float) -> dict:
    return {
        "mode": "prospective",
        **planes(),
        "risk": {"average_gain_pct": 40.0, **risk},
    }


class GatePrecisionTests(unittest.TestCase):
    def test_a_stop_a_hair_over_the_ceiling_fails(self) -> None:
        # 10.00004% wide: past the ten percent line in the fourth decimal place.
        result = reduce_risk(converged(entry_price=100000.0, stop_price=89999.96, upside_price=140000.0))

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("initial_stop_pct", result["failed"])

    def test_a_stop_exactly_at_the_ceiling_passes(self) -> None:
        result = reduce_risk(converged(entry_price=100.0, stop_price=90.0, upside_price=130.0))

        self.assertEqual(result["verdict"], "BUY-READY")

    def test_a_reward_to_risk_a_hair_under_the_minimum_fails(self) -> None:
        result = reduce_risk(converged(entry_price=100.0, stop_price=95.0, upside_price=109.9998))

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("reward_to_risk", result["failed"])

    def test_the_gate_evaluates_the_value_it_was_given(self) -> None:
        self.assertEqual(doctrine.evaluate_gate("risk.initial_stop_and_reward", "initial_stop_ceiling_pct", 10.00004)["state"], "fail")
        self.assertEqual(doctrine.evaluate_gate("risk.initial_stop_and_reward", "initial_stop_ceiling_pct", 10.0)["state"], "pass")


if __name__ == "__main__":
    unittest.main()
