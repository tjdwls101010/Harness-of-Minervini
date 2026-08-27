"""The company's own multi-year pace, and the part of reported EPS nobody here can strip out.

Acceleration is a comparison against the company's own history, so the annual series has to
reach back far enough to have a history. The figures the source used to illustrate it -- 12
percent, then 40, then 100 -- are registered as references, which are never compared with a
ticker's measurement, so they appear nowhere in what this publishes.

The one-time-income claim is the other kind: the source's method is exact and the input is
prose in a filing footnote. What is published is the boundary, so no reader mistakes a
reported EPS here for an adjusted one.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def annual(year: int, eps: float, revenue: float) -> dict:
    return {"period": str(year), "end": f"{year}-12-31", "eps": eps, "revenue": revenue}


def evidence(years: list[dict]) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": [], "annual": years}]}


class TheCompanysOwnPace(unittest.TestCase):
    def test_a_three_year_rate_needs_four_annual_periods(self) -> None:
        # 1.00 -> 1.331 over three years is exactly 10 percent compounded.
        result = evaluate_fundamentals(
            evidence([annual(2022, 1.00, 100.0), annual(2023, 1.10, 110.0), annual(2024, 1.21, 121.0), annual(2025, 1.331, 133.1)]),
            as_of="2026-05-08",
        )

        reading = result["growth"]["acceleration_vs_historical_growth_rate"]
        self.assertEqual(reading["trailing_3yr_eps_cagr_pct"], 10.0)
        self.assertIsNone(reading["trailing_5yr_eps_cagr_pct"])
        self.assertEqual(reading["periods"], ["2022", "2025"])

    def test_five_years_of_history_reports_both_rates(self) -> None:
        years = [annual(2019 + n, round(1.00 * 1.1**n, 6), 100.0) for n in range(7)]
        result = evaluate_fundamentals(evidence(years), as_of="2026-05-08")

        reading = result["growth"]["acceleration_vs_historical_growth_rate"]
        self.assertEqual(reading["trailing_3yr_eps_cagr_pct"], 10.0)
        self.assertEqual(reading["trailing_5yr_eps_cagr_pct"], 10.0)

    def test_too_little_annual_history_leaves_both_rates_unread(self) -> None:
        result = evaluate_fundamentals(evidence([annual(2024, 1.00, 100.0), annual(2025, 1.10, 110.0)]), as_of="2026-05-08")

        reading = result["growth"]["acceleration_vs_historical_growth_rate"]
        self.assertIsNone(reading["trailing_3yr_eps_cagr_pct"])
        self.assertIsNone(reading["trailing_5yr_eps_cagr_pct"])

    def test_a_loss_year_at_the_start_leaves_the_rate_unread(self) -> None:
        # A compound rate from a negative base is arithmetic without a meaning; the source's
        # method is a growth rate, and there was no growth to compound from.
        years = [annual(2022, -0.50, 100.0), annual(2023, 0.30, 110.0), annual(2024, 0.80, 121.0), annual(2025, 1.30, 133.0)]
        result = evaluate_fundamentals(evidence(years), as_of="2026-05-08")

        reading = result["growth"]["acceleration_vs_historical_growth_rate"]
        self.assertIsNone(reading["trailing_3yr_eps_cagr_pct"])
        self.assertEqual(reading["reason"], "compound_rate_requires_a_positive_starting_year")

    def test_nothing_is_compared_against_the_figures_the_source_only_illustrated(self) -> None:
        years = [annual(2022 + n, 1.00 + n, 100.0) for n in range(4)]
        result = evaluate_fundamentals(evidence(years), as_of="2026-05-08")

        reading = result["growth"]["acceleration_vs_historical_growth_rate"]
        self.assertEqual(
            sorted(reading),
            [
                "binds",
                "computability",
                "doctrine_id",
                "latest_quarterly_eps_yoy_pct",
                "periods",
                "trailing_3yr_diluted_shares_change_pct",
                "trailing_3yr_eps_cagr_pct",
                "trailing_3yr_net_income_cagr_pct",
                "trailing_5yr_diluted_shares_change_pct",
                "trailing_5yr_eps_cagr_pct",
                "trailing_5yr_net_income_cagr_pct",
            ],
        )


class WhatTheFootnotesWouldHaveSaid(unittest.TestCase):
    def test_reported_eps_is_published_as_unadjusted(self) -> None:
        result = evaluate_fundamentals(evidence([annual(2024, 1.00, 100.0)]), as_of="2026-05-08")

        reading = result["earnings_quality"]["one_time_income_exclusion"]
        self.assertEqual(reading["state"], "not_evaluated")
        self.assertEqual(reading["reason"], "filing_footnotes_not_read_by_this_harness")
        self.assertEqual(reading["missing_inputs"], ["nonrecurring_items_per_share", "filing_footnotes"])
        self.assertIs(reading["reported_eps_is_unadjusted"], True)

    def test_the_boundary_does_not_become_a_per_request_gap(self) -> None:
        result = evaluate_fundamentals(evidence([annual(2024, 1.00, 100.0)]), as_of="2026-05-08")

        self.assertNotIn("nonrecurring_items_per_share", result["missing"])


if __name__ == "__main__":
    unittest.main()
