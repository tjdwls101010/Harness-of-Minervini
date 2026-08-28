"""The eight criteria are stored in the order the source prints them."""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.eligibility import TREND_TEMPLATE_CRITERIA
from scripts.minervini.technical import build_eligibility_evidence


SOURCE_ORDER = (
    "trend_template.price_above_150_and_200",
    "trend_template.sma_150_above_sma_200",
    "trend_template.sma_200_rising",
    "trend_template.sma_50_above_150_and_200",
    "trend_template.price_above_sma_50",
    "trend_template.price_above_52_week_low",
    "trend_template.price_near_52_week_high",
    "trend_template.relative_strength_minimum",
)


class TrendTemplateOrderTests(unittest.TestCase):
    def test_the_criteria_tuple_matches_the_books_own_numbering(self) -> None:
        self.assertEqual(TREND_TEMPLATE_CRITERIA, SOURCE_ORDER)

    def test_the_builder_emits_them_in_that_same_order(self) -> None:
        index = pd.bdate_range(end="2026-08-21", periods=260)
        close = pd.Series([50.0 + value * 0.4 for value in range(260)], index=index, dtype=float)
        # The builder reads the year's extremes off High and Low, so a frame of closes alone is
        # no longer a price history. A zero-width bar keeps this fixture about the ordering.
        frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1_000_000.0}, index=index)

        evidence = build_eligibility_evidence(frame, rs_rating=85)

        self.assertEqual(tuple(signal["id"] for signal in evidence["trend_template"]), SOURCE_ORDER)


if __name__ == "__main__":
    unittest.main()
