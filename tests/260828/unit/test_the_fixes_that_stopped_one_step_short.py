"""Seven places a repair reached part of the way and no further.

Each of these was closed in the round before this one, and each was closed at one call site
while the same question was still being asked somewhere else the old way. A rule with two
readers is a rule that will disagree with itself, so what these assert is not the rule -- that
already has its tests -- but that the rule now has one reader.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

import pandas as pd

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.sec import normalize_filed_facts
from scripts.minervini.providers.yfinance import completed_daily_bars


_ENDS = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def quarter(year: int, index: int, eps: float, *, revenue: float = 100.0, unit: str = "USD/shares") -> dict:
    return {"period": f"{year}-Q{index}", "end": f"{year}-{_ENDS[index]}", "eps": eps, "revenue": revenue, "net_income": eps * 10, "diluted_shares": 100.0, "_units": {"eps": unit, "revenue": "USD", "net_income": "USD", "diluted_shares": "shares"}}


def filing(quarterly: list[dict] | None = None, years: list[dict] | None = None, *, filed_at: str = "2026-05-01", basis: str = "US-GAAP") -> dict:
    return {"filed_at": filed_at, "form": "10-Q", "accounting_basis": basis, "quarterly": quarterly or [], "annual": years or []}


class TheUnitReachesTheComparisonAndNotJustTheProvenance(unittest.TestCase):
    """`_sources` carried the unit and the measured point did not, so nothing read it.

    A reporting-currency change is the case: same registrant, same regime, same concept, and a
    thirty percent rise that is an exchange rate. The twelve-month sum did worse -- it added two
    currencies together and divided a price by the total.
    """

    @staticmethod
    def payload() -> dict:
        quarters = [quarter(2025, index, 1.0) for index in (1, 2, 3)]
        quarters += [quarter(2025, 4, 1.3, unit="CAD/shares"), quarter(2026, 1, 1.3, unit="CAD/shares")]
        return evaluate_fundamentals({"source": "sec_filed_facts", "filings": [filing(quarters)]}, as_of="2026-05-08", last_close=26.0)

    def test_growth_across_two_currencies_is_not_published(self) -> None:
        self.assertEqual(self.payload()["quarterly"]["eps_yoy_growth"], [])

    def test_a_trailing_year_is_not_summed_across_two_currencies(self) -> None:
        reading = self.payload()["valuation"]["price_earnings_ratio"]

        self.assertIsNone(reading["trailing_12m_eps"])
        self.assertEqual(reading["state"], "unavailable")

    def test_the_return_on_equity_names_the_unit_rather_than_the_regime(self) -> None:
        year = {"period": "2025", "end": "2025-12-31", "net_income": 40.0, "stockholders_equity": 200.0, "_units": {"net_income": "USD", "stockholders_equity": "CAD"}}
        reading = evaluate_fundamentals({"source": "sec_filed_facts", "filings": [filing(years=[year], filed_at="2026-02-20")]}, as_of="2026-02-21")["profitability"]["return_on_equity"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "net_income_and_equity_measured_in_different_units")


class OneAccessionCanCarryTwoRegimes(unittest.TestCase):
    """Grouping by (accession, basis) cannot keep a fact the dedup already threw away.

    A transition filer tags the same period under both taxonomies in one document. Keyed
    without the regime, the second one never reached the group that exists to hold it -- and
    the provenance refusals added beside it had nothing left to refuse.
    """

    def test_both_taxonomies_survive_one_accession(self) -> None:
        row = lambda value: {"start": "2025-01-01", "end": "2025-12-31", "val": value, "accn": "same", "form": "20-F", "filed": "2026-03-01"}
        facts = {"cik": 1, "facts": {
            "us-gaap": {"Revenues": {"units": {"USD": [row(100.0)]}}},
            "ifrs-full": {"Revenue": {"units": {"USD": [row(130.0)]}}},
        }}
        submissions = {"cik": 1, "filings": {"recent": {"accessionNumber": ["same"], "filingDate": ["2026-03-01"], "reportDate": ["2025-12-31"], "form": ["20-F"]}}}
        filings = normalize_filed_facts(facts, submissions, as_of="2026-03-02")["filings"]

        self.assertEqual(sorted(record["accounting_basis"] for record in filings), ["IFRS", "US-GAAP"])


class ThePriceRefusalsAskOnlyAboutSessionsTheRequestReached(unittest.TestCase):
    """A provider that hands back more than was asked for does not move the point-in-time answer.

    The impossible-range check ran before the `as_of` filter, so one bad row three days past
    the boundary refused a history that was complete and correct through the session requested.
    """

    def test_a_bad_bar_past_as_of_does_not_refuse_the_history(self) -> None:
        frame = pd.DataFrame(
            {"Open": [10.0, 20.0], "High": [11.0, 19.0], "Low": [9.0, 18.0], "Close": [10.0, 20.0], "Volume": [100.0, 100.0]},
            index=pd.to_datetime(["2026-05-08", "2026-05-11"]),
        )
        snapshot = completed_daily_bars("TEST", as_of="2026-05-08", ticker=_Feed(frame), now=datetime(2026, 5, 9, tzinfo=timezone.utc), retrieved_at="2026-05-09T00:00:00Z")

        self.assertEqual([str(value.date()) for value in snapshot.data.index], ["2026-05-08"])

    def test_a_bad_bar_inside_the_window_still_refuses(self) -> None:
        frame = pd.DataFrame(
            {"Open": [10.0], "High": [11.0], "Low": [9.0], "Close": [99.0], "Volume": [100.0]},
            index=pd.to_datetime(["2026-05-08"]),
        )

        with self.assertRaises(ProviderUnavailable):
            completed_daily_bars("TEST", as_of="2026-05-08", ticker=_Feed(frame), now=datetime(2026, 5, 9, tzinfo=timezone.utc), retrieved_at="2026-05-09T00:00:00Z")


class EveryPresentTenseReadingAsksTheOneAnchor(unittest.TestCase):
    """The anchor reached the bands and stopped, and six other readings still said "latest".

    The fixture is the one from the round before: eight quarters of earnings, then a ninth
    filed with revenue and no earnings. Code 33 calls itself a situation the stock is in now,
    the margin trend and the smoothed pair say "the two latest filed quarters", and the
    cyclical reading names a direction the stock is supposed to be in.
    """

    @staticmethod
    def payload(**declared) -> dict:
        quarters = [quarter(2024, index, eps) for index, eps in zip((1, 2, 3, 4), (0.10, 0.20, 0.30, 0.40))]
        quarters += [quarter(2025, index, eps) for index, eps in zip((1, 2, 3, 4), (0.20, 0.40, 0.60, 0.80))]
        stale = {"period": "2026-Q1", "end": "2026-03-31", "revenue": 120.0, "diluted_shares": 100.0, "_units": {"revenue": "USD", "diluted_shares": "shares"}}
        return evaluate_fundamentals({"source": "sec_filed_facts", "filings": [filing(quarters + [stale])]}, as_of="2026-05-08", **declared)

    def test_code_33_is_not_a_situation_a_stale_quarter_puts_the_stock_in(self) -> None:
        reading = self.payload()["growth"]["code_33_triple_acceleration"]

        self.assertEqual(reading["state"], "unavailable")

    def test_the_margin_trend_and_the_smoothed_pair_go_unread(self) -> None:
        growth = self.payload()["growth"]

        self.assertEqual(growth["margin_trend"]["reason"], "two_filed_quarters_required")
        self.assertIsNone(growth["two_quarter_rolling_average"]["eps_yoy_pct"])

    def test_the_cyclical_direction_is_unavailable(self) -> None:
        reading = self.payload(leader_category="cyclical")["category_reading"]["readings"]["cyclical_inverse_pe_and_signals"]

        self.assertEqual(reading["earnings_direction"], "unavailable")
        self.assertIsNone(reading["latest_quarterly_eps_yoy_pct"])


class AWithheldPeriodIsStillAQuarterThatWasFiled(unittest.TestCase):
    """The collision rule removed the period before the anchor was derived from it.

    So the payload named the collision in `missing` and, beside it, a trailing year ending a
    quarter earlier published as `reported`. Two answers to one question, in one envelope.
    """

    @staticmethod
    def payload() -> dict:
        history = [quarter(2024, index, eps) for index, eps in zip((1, 2, 3), (0.80, 0.90, 1.00))]
        history += [quarter(2025, index, eps) for index, eps in zip((1, 2, 3), (1.00, 1.10, 1.20))]
        collided = [
            {"period": "2026-Q1", "end": "2026-02-15", "eps": 2.0, "revenue": 100.0, "net_income": 20.0, "diluted_shares": 100.0},
            {"period": "2026-Q1", "end": "2026-05-06", "eps": 3.0, "revenue": 100.0, "net_income": 30.0, "diluted_shares": 100.0},
        ]
        years = [{"period": "2024", "start": "2024-01-01", "end": "2024-12-31", "eps": 4.0}, {"period": "2025", "start": "2025-01-01", "end": "2025-12-31", "eps": 5.0}]
        evidence = {"source": "sec_filed_facts", "filings": [
            {"filed_at": "2026-02-20", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": history, "annual": years},
            {"filed_at": "2026-06-01", "form": "10-Q", "accounting_basis": "US-GAAP", "quarterly": collided, "annual": []},
        ]}
        return evaluate_fundamentals(evidence, as_of="2026-06-10", last_close=46.0, breakout_close=46.0, breakout_date="2026-06-05")

    def test_the_anchor_is_the_withheld_quarter(self) -> None:
        payload = self.payload()

        self.assertIn("quarterly_periods_two_closes_reached", payload["missing"])
        self.assertEqual(payload["quarterly"]["latest_filed_period"], "2026-Q1")

    def test_neither_trailing_year_falls_back_to_the_quarter_before(self) -> None:
        payload = self.payload()

        self.assertEqual(payload["valuation"]["price_earnings_ratio"]["state"], "unavailable")
        self.assertIsNone(payload["valuation"]["pe_expansion"]["trailing_12m_eps_at_breakout"])


class TheSourceStatedOneConditionAboutBothBalances(unittest.TestCase):
    """"If receivables and inventories are BOTH increasing at a greater rate than sales."

    Two gates applied the combined limit to each balance alone, so a company whose inventory
    ran ahead while its receivables did not carried a failing gate for a filter it had cleared.
    """

    @staticmethod
    def reading(receivables: float) -> dict:
        years = [
            {"period": "2024", "end": "2024-12-31", "eps": 1.0, "revenue": 100.0, "inventory": 40.0, "accounts_receivable": 20.0},
            {"period": "2025", "end": "2025-12-31", "eps": 1.0, "revenue": 110.0, "inventory": 50.0, "accounts_receivable": receivables},
        ]
        return evaluate_fundamentals({"source": "sec_filed_facts", "filings": [filing(years=years)]}, as_of="2026-05-10")["earnings_quality"]["inventory_receivables_vs_sales"]

    def test_one_balance_running_ahead_alone_clears_the_condition(self) -> None:
        reading = self.reading(20.4)

        self.assertEqual(reading["inventory_vs_sales_ratio"], 2.5)
        self.assertEqual(reading["accounts_receivable_vs_sales_ratio"], 0.2)
        self.assertEqual(reading["gate"]["state"], "pass")
        self.assertEqual(reading["state"], "reported")

    def test_both_running_ahead_reaches_the_one_gate(self) -> None:
        reading = self.reading(26.0)

        self.assertEqual(reading["gate"]["state"], "fail")
        self.assertEqual(reading["state"], "both_grew_at_least_twice_as_fast_as_sales")


class _Feed:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def history(self, **kwargs) -> pd.DataFrame:
        return self._frame


if __name__ == "__main__":
    unittest.main()
