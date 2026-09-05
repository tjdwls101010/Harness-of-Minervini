"""The half-average-gain cap is a hard gate, so its input cannot go missing quietly."""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk
from tests.attestations import planes


CONVERGED = {
    "mode": "prospective",
    **planes(),
    "risk": {"state": "pass", "entry_price": 100.0, "stop_price": 94.0, "upside_price": 112.0},
}


def evidence(**risk_overrides: float) -> dict:
    payload = {key: dict(value) if isinstance(value, dict) else value for key, value in CONVERGED.items()}
    payload["risk"] = {**payload["risk"], **risk_overrides}
    return payload


class HalfAverageGainCapTests(unittest.TestCase):
    def test_absent_realized_average_gain_is_missing_evidence_not_a_silent_pass(self) -> None:
        result = reduce_risk(evidence())

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("average_gain_pct", result["missing"])
        self.assertIsNone(result["risk_controls"]["half_average_gain_cap_pct"])

    def test_supplied_average_gain_within_the_cap_reaches_buy_ready(self) -> None:
        result = reduce_risk(evidence(average_gain_pct=20.0))

        self.assertEqual(result["verdict"], "BUY-READY")
        self.assertEqual(result["risk_controls"]["half_average_gain_cap_pct"], 10.0)

    def test_supplied_average_gain_below_the_stop_still_rejects(self) -> None:
        result = reduce_risk(evidence(average_gain_pct=10.0))

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("half_average_gain_cap", result["failed"])


if __name__ == "__main__":
    unittest.main()
