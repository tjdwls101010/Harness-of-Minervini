"""A compound per-share rate is two ratios at once, and only one of them is about the business.

Apple's filed annual EPS falls from 9.21 to 2.98 between fiscal 2017 and 2018 -- not because the
company earned a third as much, but because the four-for-one split of 2020 restated every later
vintage of the earlier years onto a share base four times larger. Compounding across that point
reports a company that shrank.

The split itself is a price-history fact and this evaluator holds filings, so it cannot be
detected here and nothing is adjusted. What can be done is to publish the two rates the
per-share rate is made of: the total earnings, which no split touches, and the share count,
which a split is. A reader seeing earnings compound at twenty percent while the per-share figure
compounds at minus ten has been told exactly what happened.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers.sec import normalize_filed_facts


def annual(year: int, eps: float, net_income: float, diluted_shares: float) -> dict:
    return {"period": str(year), "end": f"{year}-12-31", "eps": eps, "revenue": 100.0, "net_income": net_income, "diluted_shares": diluted_shares}


def evidence(years: list[dict]) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": [], "annual": years}]}


def reading(years: list[dict]) -> dict:
    return evaluate_fundamentals(evidence(years), as_of="2026-05-08")["growth"]["acceleration_vs_historical_growth_rate"]


class TheTwoRatesBehindThePerShareOne(unittest.TestCase):
    def test_a_four_for_one_split_shows_up_as_earnings_rising_while_the_per_share_falls(self) -> None:
        # Earnings compound at ten percent; the share count quadruples in the last year.
        years = [
            annual(2022, 1.00, 100.0, 100.0),
            annual(2023, 1.10, 110.0, 100.0),
            annual(2024, 1.21, 121.0, 100.0),
            annual(2025, 0.33275, 133.1, 400.0),
        ]
        result = reading(years)

        self.assertLess(result["trailing_3yr_eps_cagr_pct"], 0)
        self.assertEqual(result["trailing_3yr_net_income_cagr_pct"], 10.0)
        self.assertEqual(result["trailing_3yr_diluted_shares_change_pct"], 300.0)

    def test_a_steady_share_base_leaves_the_two_rates_agreeing(self) -> None:
        years = [annual(2022 + n, round(1.00 * 1.1**n, 6), round(100.0 * 1.1**n, 6), 100.0) for n in range(4)]
        result = reading(years)

        self.assertEqual(result["trailing_3yr_eps_cagr_pct"], 10.0)
        self.assertEqual(result["trailing_3yr_net_income_cagr_pct"], 10.0)
        self.assertEqual(result["trailing_3yr_diluted_shares_change_pct"], 0.0)

    def test_a_buyback_lifts_the_per_share_rate_above_the_total_and_says_so(self) -> None:
        years = [
            annual(2022, 1.00, 100.0, 100.0),
            annual(2023, 1.05, 100.0, 95.238095),
            annual(2024, 1.11, 100.0, 90.09009),
            annual(2025, 1.18, 100.0, 84.745763),
        ]
        result = reading(years)

        self.assertGreater(result["trailing_3yr_eps_cagr_pct"], 0)
        self.assertEqual(result["trailing_3yr_net_income_cagr_pct"], 0.0)
        self.assertLess(result["trailing_3yr_diluted_shares_change_pct"], 0)

    def test_without_a_filed_share_count_the_context_is_unread_rather_than_guessed(self) -> None:
        years = [{"period": str(2022 + n), "end": f"{2022 + n}-12-31", "eps": round(1.1**n, 6), "revenue": 100.0} for n in range(4)]
        result = reading(years)

        self.assertEqual(result["trailing_3yr_eps_cagr_pct"], 10.0)
        self.assertIsNone(result["trailing_3yr_net_income_cagr_pct"])
        self.assertIsNone(result["trailing_3yr_diluted_shares_change_pct"])


class TheBestStretchCarriesItToo(unittest.TestCase):
    def test_the_winning_stretch_publishes_what_the_share_count_did(self) -> None:
        years = [annual(2018 + n, round(1.00 * 1.4**n, 6), round(100.0 * 1.4**n, 6), 100.0) for n in range(8)]
        pace = evaluate_fundamentals(evidence(years), as_of="2026-05-08", leader_category="market_leader")["category_reading"]["readings"]["market_leader_earnings_growth_pace"]

        self.assertEqual(pace["best_stretch"]["measured"], 40.0)
        self.assertEqual(pace["best_stretch_diluted_shares_change_pct"], 0.0)


class TheProviderSendsTheShareCount(unittest.TestCase):
    def test_annual_diluted_shares_reach_the_evaluator(self) -> None:
        facts = {"us-gaap": {
            "EarningsPerShareDiluted": {"label": "e", "units": {"USD/shares": [
                {"start": "2025-01-01", "end": "2025-12-31", "val": 1.00, "accn": "a-1", "filed": "2026-02-19", "form": "10-K", "fy": 2025, "fp": "FY", "frame": "CY2025"},
            ]}},
            "WeightedAverageNumberOfDilutedSharesOutstanding": {"label": "s", "units": {"shares": [
                {"start": "2025-01-01", "end": "2025-12-31", "val": 100.0, "accn": "a-1", "filed": "2026-02-19", "form": "10-K", "fy": 2025, "fp": "FY", "frame": "CY2025"},
            ]}},
        }}
        submissions = {"cik": 42, "filings": {"recent": {"accessionNumber": ["a-1"], "filingDate": ["2026-02-19"], "reportDate": ["2025-12-31"], "form": ["10-K"]}}}
        normalized = normalize_filed_facts({"cik": 42, "entityName": "T", "facts": facts}, submissions, as_of="2026-05-08")

        self.assertEqual(normalized["filings"][0]["annual"][0]["diluted_shares"], 100.0)


if __name__ == "__main__":
    unittest.main()
