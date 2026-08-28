from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.minervini.technical import build_eligibility_evidence


def history(closes: list[float]) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-02", periods=len(closes))
    close = pd.Series(closes, index=index)
    return pd.DataFrame(
        {
            "Open": close * 0.995,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000),
        },
        index=index,
    )


class TechnicalEvidenceTests(unittest.TestCase):
    def test_rising_leader_produces_the_canonical_eight_standard_passes(self) -> None:
        prices = history(np.linspace(50, 150, 270).tolist())

        evidence = build_eligibility_evidence(prices, rs_rating=92)

        self.assertEqual(evidence["history_state"], "sufficient")
        self.assertEqual(evidence["stage_2"]["state"], "pass")
        self.assertEqual(len(evidence["trend_template"]), 8)
        self.assertTrue(all(signal["state"] == "pass" for signal in evidence["trend_template"]))
        self.assertEqual(evidence["as_of"], prices.index[-1].date().isoformat())

    def test_missing_rs_is_unavailable_without_changing_price_gate_results(self) -> None:
        prices = history(np.linspace(50, 150, 270).tolist())

        evidence = build_eligibility_evidence(prices, rs_rating=None)

        by_id = {signal["id"]: signal for signal in evidence["trend_template"]}
        self.assertEqual(by_id["trend_template.relative_strength_minimum"]["state"], "unavailable")
        self.assertEqual(by_id["trend_template.price_above_sma_50"]["state"], "pass")

    def test_falling_200_day_structure_is_a_known_failure(self) -> None:
        prices = history(np.linspace(180, 80, 270).tolist())

        evidence = build_eligibility_evidence(prices, rs_rating=95)

        by_id = {signal["id"]: signal for signal in evidence["trend_template"]}
        self.assertEqual(by_id["trend_template.sma_200_rising"]["state"], "fail")
        self.assertEqual(evidence["stage_2"]["state"], "fail")

    def test_recent_ipo_quantifies_primary_base_but_leaves_visual_quality_for_chart_review(self) -> None:
        first_advance = np.linspace(20, 45, 25)
        base = np.concatenate([np.linspace(45, 36, 12), np.linspace(36, 44, 17)])
        breakout = np.array([46.0])
        prices = history(np.concatenate([first_advance, base, breakout]).tolist())

        evidence = build_eligibility_evidence(prices, rs_rating=88)

        self.assertEqual(evidence["history_state"], "insufficient")
        self.assertTrue(evidence["primary_base"]["quantitative_claims"])
        self.assertEqual(evidence["primary_base"]["quality"]["state"], "needs_chart")


if __name__ == "__main__":
    unittest.main()
