"""Three places where a source's own words were read as something narrower than they are.

A population statistic is not a range this ticker sits inside. Two spans a source named are
not every span between them. And a finding the source qualified with "without explanation" is
not a finding from the numbers alone, when the explanation lives in prose this harness does
not read.
"""

from __future__ import annotations

from tests.filings import annual, evidence as shared_evidence

import unittest

from scripts.minervini import doctrine
from scripts.minervini.fundamentals import _PE_EXPANSION, evaluate_fundamentals


def evidence(years: list[dict], quarterly: list[dict] | None = None, basis: str = "US-GAAP", filed_at: str = "2026-02-20") -> dict:
    return shared_evidence(filed_at=filed_at, basis=basis, quarters=quarterly or [], years=years)


class AStudysAverageIsNotThisTickersRange(unittest.TestCase):
    """"Historical study of superperformance stocks shows... on average" describes a population.

    The same passage's other half is conditional on this stock -- "if the P/E expands by 100 to
    200 percent" -- and that half stays a band. The study's average does not: comparing a
    ticker against it publishes a positional state about a number that was never a standard.
    """

    def test_the_historical_multiple_is_registered_as_a_reference(self) -> None:
        role = doctrine.get_claim(_PE_EXPANSION)["claim"]["thresholds"]["pe_expansion_historical_average_multiple"]["role"]

        self.assertEqual(role, "reference")

    def test_the_multiple_is_published_without_a_positional_state(self) -> None:
        from .test_the_multiple_and_what_it_is_worth import valuation

        reading = valuation(last_close=70.0, breakout_close=17.50, breakout_date="2025-03-14")["pe_expansion"]

        self.assertEqual(reading["multiple_measured"], 2.0)
        self.assertEqual(reading["historical_average_multiple"], [2, 3])
        self.assertNotIn("multiple", reading)


class FiveOrTenIsTwoSpansNotSix(unittest.TestCase):
    """"During their best 5- or 10-year stretch" names two lengths and no lengths between them.

    Reading it as a range lets a six-year window win, and the rate that goes out under the
    source's 35-to-45 band was then measured over a span the source never mentioned.
    """

    def test_a_six_year_window_is_not_a_stretch_the_source_named(self) -> None:
        values = [1, 3, 4, 6, 10, 20, 64]
        years = [annual(year, float(value)) for year, value in zip(range(2019, 2026), values)]
        reading = evaluate_fundamentals(evidence(years), as_of="2026-05-10", leader_category="market_leader")["category_reading"]["readings"]["market_leader_earnings_growth_pace"]

        self.assertEqual(reading["best_stretch_span_years"], 5)
        self.assertEqual(reading["best_stretch_periods"], ["2020", "2025"])
        self.assertEqual(reading["best_stretch"]["measured"], 84.4215822963)


class DoubleTroubleNeedsThePremiseTheSourceAttached(unittest.TestCase):
    """"Twice or more without explanation" -- and the explanation is prose nobody here reads.

    The ratios are filed numbers and belong in front of a reader. What they cannot do is carry
    the source's conclusion, because half of its condition was never measured. The unread half
    is named the way the other footnote claims in this evaluator are.
    """

    @staticmethod
    def reading() -> dict:
        years = [
            annual(2024, 2.30, revenue=100.0, inventory=40.0, accounts_receivable=20.0),
            annual(2025, 3.70, revenue=110.0, inventory=50.0, accounts_receivable=26.0),
        ]
        return evaluate_fundamentals(evidence(years), as_of="2026-05-10")["earnings_quality"]["inventory_receivables_vs_sales"]

    def test_the_ratios_are_published(self) -> None:
        reading = self.reading()

        self.assertEqual(reading["inventory_vs_sales_ratio"], 2.5)
        self.assertEqual(reading["accounts_receivable_vs_sales_ratio"], 3.0)

    def test_the_unread_half_of_the_condition_is_named(self) -> None:
        reading = self.reading()

        self.assertEqual(reading["state"], "both_grew_at_least_twice_as_fast_as_sales")
        self.assertIn("management_explanation_for_the_increase", reading["missing_inputs"])


class ACompoundRateNeedsOneAccountingRegime(unittest.TestCase):
    """The rule decision 281 settled reached four readings and not the two below it.

    A compound rate whose endpoints were measured under different regimes is the same defect as
    a margin built from two of them, one step further from the filings. So is a balance-sheet
    ratio whose two years came from different books.
    """

    @staticmethod
    def two_regimes(rows: list[tuple[str, str, dict]]) -> dict:
        return {"source": "sec_filed_facts", "filings": [
            {"filed_at": filed_at, "form": "10-K", "accounting_basis": basis, "quarterly": [], "annual": [year]}
            for filed_at, basis, year in rows
        ]}

    def test_a_compound_rate_across_two_regimes_is_not_computed(self) -> None:
        evidence = self.two_regimes([
            ("2023-02-20", "US-GAAP", annual(2022, 1.0, net_income=100.0)),
            ("2026-02-20", "IFRS", annual(2025, 8.0, net_income=800.0)),
        ])
        reading = evaluate_fundamentals(evidence, as_of="2026-05-10")["growth"]["acceleration_vs_historical_growth_rate"]

        self.assertIsNone(reading["trailing_3yr_eps_cagr_pct"])
        self.assertEqual(reading["reason"], "measured_under_different_accounting_bases")

    def test_a_balance_sheet_ratio_across_two_regimes_is_not_computed(self) -> None:
        evidence = self.two_regimes([
            ("2025-02-20", "US-GAAP", annual(2024, 4.0, revenue=100.0, inventory=40.0, accounts_receivable=20.0)),
            ("2026-02-20", "IFRS", annual(2025, 5.2, revenue=110.0, inventory=50.0, accounts_receivable=26.0)),
        ])
        reading = evaluate_fundamentals(evidence, as_of="2026-05-10")["earnings_quality"]["inventory_receivables_vs_sales"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "annual_periods_measured_under_different_accounting_bases")


if __name__ == "__main__":
    unittest.main()
