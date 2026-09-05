"""Acceleration on all three cylinders, and whether the growth had anywhere to come from.

Code 33 is the source's own name for three quarters of acceleration in earnings, sales and
profit margins at once. It is the one fundamentals claim with a gate -- three quarters,
exactly -- and all three series are filed, so it is measured rather than described.

Beside it sits the constitution-level warning that earnings improvement from cost cutting
walks on short legs. That one the source declined to quantify, so what is published is the
pattern it points at: profits rising while sales do not.
"""

from __future__ import annotations

from tests.filings import evidence as shared_evidence, quarter as shared_quarter

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float, revenue: float, net_income: float) -> dict:
    return shared_quarter(period, end, eps, revenue=revenue, net_income=net_income)


def evidence(quarters: list[dict]) -> dict:
    return shared_evidence(quarters=quarters, years=[])


def two_years(eps: list[float], revenue: list[float], net_income: list[float]) -> list[dict]:
    """Four flat base quarters, then four whose growth rates the test chooses."""

    rows = [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", 1.00, 100.0, 10.0) for n in range(4)]
    rows += [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", eps[n], revenue[n], net_income[n]) for n in range(4)]
    return rows


class ThreeQuartersOnAllThreeCylinders(unittest.TestCase):
    def test_earnings_sales_and_margin_all_accelerating_is_the_code(self) -> None:
        # EPS growth 10 -> 20 -> 30 -> 40, sales growth 5 -> 10 -> 15 -> 20, and the margin
        # widening every quarter: three consecutive quarters where all three improved.
        rows = two_years(
            eps=[1.10, 1.20, 1.30, 1.40],
            revenue=[105.0, 110.0, 115.0, 120.0],
            net_income=[11.0, 13.2, 16.1, 19.8],
        )
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        code = result["growth"]["code_33_triple_acceleration"]
        self.assertEqual(code["consecutive_quarters"], 3)
        self.assertEqual(code["gate"]["state"], "pass")
        self.assertEqual(code["gate"]["required"], ">= 3")
        self.assertEqual(code["quarters"], ["2025-Q2", "2025-Q3", "2025-Q4"])

    def test_one_cylinder_missing_breaks_the_run(self) -> None:
        # Sales growth flat at 5% throughout: never accelerating, so no quarter qualifies.
        rows = two_years(
            eps=[1.10, 1.20, 1.30, 1.40],
            revenue=[105.0, 105.0, 105.0, 105.0],
            net_income=[11.0, 13.2, 16.1, 19.8],
        )
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        code = result["growth"]["code_33_triple_acceleration"]
        self.assertEqual(code["consecutive_quarters"], 0)
        self.assertEqual(code["gate"]["state"], "fail")

    def test_a_run_that_ended_before_the_latest_quarter_is_not_the_code_now(self) -> None:
        # Three good quarters then a fourth where the margin narrowed. The source's phrase is
        # a situation the stock is in, so the run has to reach the latest filed quarter.
        rows = two_years(
            eps=[1.10, 1.20, 1.30, 1.35],
            revenue=[105.0, 110.0, 115.0, 125.0],
            net_income=[11.0, 13.2, 16.1, 15.0],
        )
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        self.assertEqual(result["growth"]["code_33_triple_acceleration"]["gate"]["state"], "fail")

    def test_too_little_history_is_unavailable_rather_than_a_failure(self) -> None:
        rows = two_years(eps=[1.10, 1.20, 1.30, 1.40], revenue=[105.0, 110.0, 115.0, 120.0], net_income=[11.0, 13.2, 16.1, 19.8])[:6]
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        code = result["growth"]["code_33_triple_acceleration"]
        self.assertEqual(code["state"], "unavailable")
        self.assertEqual(code["reason"], "insufficient_quarters_for_triple_acceleration")


class GrowthHasToComeFromSomewhere(unittest.TestCase):
    def test_profits_rising_while_sales_do_not_is_the_pattern_the_source_warns_about(self) -> None:
        rows = two_years(eps=[1.10, 1.20, 1.30, 1.40], revenue=[100.0, 100.0, 100.0, 100.0], net_income=[11.0, 12.0, 13.0, 14.0])
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        reading = result["growth"]["earnings_without_sales_growth"]
        self.assertIs(reading["earnings_grew_without_sales"], True)
        self.assertEqual(reading["eps_yoy_pct"], 40.0)
        self.assertEqual(reading["revenue_yoy_pct"], 0.0)
        self.assertEqual(reading["computability"], "judgment_only")
        self.assertNotIn("gate", reading)

    def test_sales_growing_with_earnings_is_not_that_pattern(self) -> None:
        rows = two_years(eps=[1.10, 1.20, 1.30, 1.40], revenue=[105.0, 110.0, 115.0, 120.0], net_income=[11.0, 13.2, 16.1, 19.8])
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        self.assertIs(result["growth"]["earnings_without_sales_growth"]["earnings_grew_without_sales"], False)


if __name__ == "__main__":
    unittest.main()
