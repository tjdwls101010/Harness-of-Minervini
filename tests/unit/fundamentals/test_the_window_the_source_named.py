"""The source's ranges come with a window of quarters, and reading one quarter throws it away.

"A minimum of 20 to 25 percent year-over-year increases in the most recent one, two, or three
quarters" names two things: a range, and how far back to look for it. The range was already
read. The window was not, so a stock whose latest quarter came in soft after two strong ones
was published as though the two strong ones had not been filed.

The window is registered as a reference -- chosen rather than measured -- so nothing is
compared against it. It decides how many quarters get reported, and no more.
"""

from __future__ import annotations

from tests.filings import evidence as shared_evidence, quarter as shared_quarter

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float, revenue: float) -> dict:
    return shared_quarter(period, end, eps, revenue=revenue)


def evidence(quarters: list[dict]) -> dict:
    annual = [{"period": "2024", "end": "2024-12-31", "eps": 4.00, "revenue": 400.0}, {"period": "2025", "end": "2025-12-31", "eps": 4.80, "revenue": 440.0}]
    return shared_evidence(quarters=quarters, years=annual)


def eight_quarters(growth_pct: list[float]) -> list[dict]:
    base = [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", 1.00, 100.0) for n in range(4)]
    later = [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", 1.00 * (1 + growth_pct[n] / 100), 100.0) for n in range(4)]
    return base + later


class TheMinimumIsRequiredOverAWindow(unittest.TestCase):
    def test_the_two_strong_quarters_behind_a_soft_one_are_reported(self) -> None:
        result = evaluate_fundamentals(evidence(eight_quarters([10.0, 30.0, 40.0, 18.0])), as_of="2026-05-08")

        minimum = result["growth"]["minimum_quarterly_earnings_growth"]
        self.assertEqual(minimum["state"], "below_source_range")
        self.assertEqual(minimum["window_quarters"], [1, 3])
        self.assertEqual(
            [(q["period"], q["yoy_pct"], q["state"]) for q in minimum["window"]],
            [("2025-Q2", 30.0, "above_source_range"), ("2025-Q3", 40.0, "above_source_range"), ("2025-Q4", 18.0, "below_source_range")],
        )
        self.assertEqual(minimum["window_quarters_within_or_above"], 2)

    def test_the_headline_reading_still_belongs_to_the_latest_quarter(self) -> None:
        result = evaluate_fundamentals(evidence(eight_quarters([10.0, 30.0, 40.0, 18.0])), as_of="2026-05-08")

        self.assertEqual(result["growth"]["minimum_quarterly_earnings_growth"]["measured"], 18.0)
        self.assertEqual(result["quality"]["measured_yoy_pct"], 18.0)
        self.assertEqual(result["quality"]["state"], "review")
        self.assertIn("quarterly_earnings_growth_below_source_range", result["quality"]["review_reasons"])

    def test_a_shorter_history_reports_the_quarters_it_has(self) -> None:
        rows = eight_quarters([10.0, 30.0, 40.0, 18.0])[:6]
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-08")

        minimum = result["growth"]["minimum_quarterly_earnings_growth"]
        self.assertEqual([q["period"] for q in minimum["window"]], ["2025-Q1", "2025-Q2"])
        self.assertEqual(minimum["window_quarters_within_or_above"], 1)

    def test_the_bull_market_band_carries_its_own_window(self) -> None:
        result = evaluate_fundamentals(evidence(eight_quarters([10.0, 30.0, 45.0, 60.0])), as_of="2026-05-08", market_regime="bull")

        bull = result["growth"]["bull_market_quarterly_earnings_growth"]
        self.assertEqual(bull["window_quarters"], [2, 3])
        self.assertEqual([q["period"] for q in bull["window"]], ["2025-Q2", "2025-Q3", "2025-Q4"])
        self.assertEqual(bull["window_quarters_within_or_above"], 2)


class SomeFormOfAcceleration(unittest.TestCase):
    def test_the_lookback_names_the_quarters_it_examined(self) -> None:
        result = evaluate_fundamentals(evidence(eight_quarters([10.0, 30.0, 40.0, 18.0])), as_of="2026-05-08")

        lookback = result["growth"]["earnings_history_lookback"]
        self.assertEqual(lookback["lookback_years"], [1, 2])
        self.assertEqual(lookback["periods_examined"], ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"])

    def test_a_quarter_where_both_accelerated_is_named(self) -> None:
        # EPS growth 10 -> 30 accelerates into 2025-Q2; revenue is flat, so neither quarter
        # is a both-cylinder one, and the source asked about earnings and sales together.
        result = evaluate_fundamentals(evidence(eight_quarters([10.0, 30.0, 40.0, 18.0])), as_of="2026-05-08")

        lookback = result["growth"]["earnings_history_lookback"]
        self.assertEqual(lookback["quarters_accelerating_in_both"], [])
        self.assertIs(lookback["some_form_of_acceleration"], False)


if __name__ == "__main__":
    unittest.main()
