"""What each remaining category's claim can read here, and what it plainly cannot.

Only one of these five is measurable from filed numbers: a market leader's annual pace, which
the source gave as a marker and a band. The other four ask for peer groups, dividend histories,
industry classifications and price-earnings series that this evaluator does not hold, so each
publishes the claim, what it needed, and what was missing -- rather than a reading computed
from whatever happened to be available.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def annual(year: int, eps: float) -> dict:
    return {"period": str(year), "end": f"{year}-12-31", "eps": eps, "revenue": 100.0}


def quarter(period: str, end: str, eps: float) -> dict:
    return {"period": period, "end": end, "eps": eps, "revenue": 100.0, "net_income": eps * 10, "diluted_shares": 100.0}


def evidence(years: list[dict], quarters: list[dict] | None = None) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": quarters or [], "annual": years}]}


def read(category: str, years: list[dict], quarters: list[dict] | None = None) -> dict:
    return evaluate_fundamentals(evidence(years, quarters), as_of="2026-05-08", leader_category=category)["category_reading"]["readings"]


class AMarketLeadersAnnualPace(unittest.TestCase):
    def test_the_marker_reports_the_distance_to_the_twenty_percent_the_source_named(self) -> None:
        years = [annual(2022, 1.00), annual(2023, 1.24), annual(2024, 1.60), annual(2025, 2.00)]
        pace = read("market_leader", years)["market_leader_earnings_growth_pace"]

        self.assertEqual(pace["latest_annual_growth"]["measured"], 25.0)
        self.assertEqual(pace["latest_annual_growth"]["source_value"], 20)
        self.assertEqual(pace["latest_annual_growth"]["distance"], 5.0)
        self.assertEqual(pace["latest_annual_growth"]["state"], "reported")

    def test_the_best_stretch_band_needs_the_five_to_ten_years_it_averages_over(self) -> None:
        years = [annual(2022, 1.00), annual(2023, 1.24), annual(2024, 1.60), annual(2025, 2.00)]
        pace = read("market_leader", years)["market_leader_earnings_growth_pace"]

        self.assertEqual(pace["best_stretch"]["state"], "unavailable")
        self.assertEqual(pace["best_stretch_years"], [5, 10])

    def test_a_forty_percent_stretch_sits_inside_the_range(self) -> None:
        # Six annual figures compounding at forty percent: a five-year stretch at 40.
        years = [annual(2020 + n, round(1.00 * 1.4**n, 6)) for n in range(6)]
        pace = read("market_leader", years)["market_leader_earnings_growth_pace"]

        self.assertEqual(pace["best_stretch"]["measured"], 40.0)
        self.assertEqual(pace["best_stretch"]["state"], "within_source_range")
        self.assertEqual(pace["best_stretch"]["source_range"], [35, 45])
        self.assertEqual(pace["best_stretch_span_years"], 5)

    def test_the_market_share_and_industry_inputs_are_named_as_unread(self) -> None:
        pace = read("market_leader", [annual(2024, 1.00), annual(2025, 1.25)])["market_leader_earnings_growth_pace"]

        self.assertEqual(pace["missing_inputs"], ["market_share_trend", "industry_classification"])


class TheFourThatCannotBeMeasuredHere(unittest.TestCase):
    def test_an_institutional_favorite_gets_its_growth_but_not_its_dividends(self) -> None:
        reading = read("institutional_favorite", [annual(2024, 1.00), annual(2025, 1.14)])["institutional_favorite_growth_pace"]

        self.assertEqual(reading["latest_annual_eps_growth_pct"], 14.0)
        self.assertEqual(reading["missing_inputs"], ["dividend_growth_history"])
        self.assertEqual(reading["unquantified"], ["low_to_middle_teens_is_a_descriptor_not_a_range"])

    def test_a_top_competitor_reading_names_the_peers_it_never_saw(self) -> None:
        reading = read("top_competitor", [annual(2025, 1.00)])["top_competitor_reading"]

        self.assertEqual(reading["state"], "not_evaluated")
        self.assertEqual(reading["competitors_to_track"], [2, 3])
        self.assertEqual(
            reading["missing_inputs"],
            ["peer_group_eps_growth", "peer_group_revenue_growth", "peer_group_margins", "peer_group_relative_strength"],
        )

    def test_a_laggard_reading_is_relative_and_this_evaluator_holds_one_company(self) -> None:
        reading = read("past_leader_or_laggard", [annual(2025, 1.00)])["laggard_fundamentals_reading"]

        self.assertEqual(reading["state"], "not_evaluated")
        self.assertEqual(reading["missing_inputs"], ["peer_group_eps_growth", "peer_group_revenue_growth", "relative_price_performance"])

    def test_a_cyclicals_four_signals_report_the_one_that_is_filed(self) -> None:
        quarters = [quarter("2024-Q4", "2024-12-30", 1.00), quarter("2025-Q4", "2025-12-30", 1.20)]
        reading = read("cyclical", [annual(2024, 1.00), annual(2025, 1.20)], quarters)["cyclical_inverse_pe_and_signals"]

        self.assertEqual(reading["earnings_direction"], "rising")
        self.assertEqual(reading["missing_inputs"], ["pe_ratio_series", "dividend_history", "industry_classification"])
        self.assertNotIn("cycle_position", reading)


class TheFootnotesNobodyHereReads(unittest.TestCase):
    def test_the_repeated_charge_and_tax_claims_publish_their_boundary(self) -> None:
        quality = evaluate_fundamentals(evidence([annual(2025, 1.00)]), as_of="2026-05-08")["earnings_quality"]

        self.assertEqual(quality["repeated_one_time_charge_red_flag"]["state"], "not_evaluated")
        self.assertEqual(quality["tax_disclosure_red_flag"]["state"], "not_evaluated")
        self.assertEqual(quality["tax_disclosure_red_flag"]["missing_inputs"], ["filing_footnotes_tax_disclosure", "effective_tax_rate", "reported_pretax_income"])

    def test_those_boundaries_are_not_counted_as_gaps_in_the_filings(self) -> None:
        result = evaluate_fundamentals(evidence([annual(2025, 1.00)]), as_of="2026-05-08")

        self.assertNotIn("filing_footnotes_tax_disclosure", result["missing"])


if __name__ == "__main__":
    unittest.main()
