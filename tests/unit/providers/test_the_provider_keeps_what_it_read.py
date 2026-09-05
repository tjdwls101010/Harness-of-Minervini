"""What the SEC and price boundaries throw away before anything downstream can see it.

Provenance moved to the field two rounds ago, and the readings that compare two numbers now
ask which regime measured each one. None of that helps when the boundary underneath has
already dropped one of the numbers, collapsed two of them into one, or answered a question
about a fiscal year with a taxonomy the filer had not adopted yet.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

import pandas as pd

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.sec import normalize_filed_facts
from scripts.minervini.providers.yfinance import completed_daily_bars


def submissions(rows: list[tuple[str, str, str, str]]) -> dict:
    return {"cik": 1, "filings": {"recent": {
        "accessionNumber": [row[0] for row in rows],
        "filingDate": [row[1] for row in rows],
        "reportDate": [row[2] for row in rows],
        "form": [row[3] for row in rows],
    }}}


def company_facts(taxonomies: dict) -> dict:
    return {"cik": 1, "facts": taxonomies}


class BothTaxonomiesAreReadBecauseAFilerCanChangeOne(unittest.TestCase):
    """A registrant that moves from IFRS to US-GAAP filed both, and both were filed.

    Choosing one taxonomy for the whole company reads whichever is present first, so the day a
    10-K appears every IFRS year the filer ever published stops existing -- including for an
    `as_of` before that 10-K was filed, which is a future document deciding a past answer.
    """

    @staticmethod
    def facts() -> dict:
        return company_facts({
            "ifrs-full": {"Revenue": {"units": {"USD": [{"start": "2024-01-01", "end": "2024-12-31", "val": 100.0, "accn": "old", "form": "20-F", "filed": "2025-03-01"}]}}},
            "us-gaap": {"Revenues": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 120.0, "accn": "future", "form": "10-K", "filed": "2026-03-01"}]}}},
        })

    @staticmethod
    def index() -> dict:
        return submissions([("old", "2025-03-01", "2024-12-31", "20-F"), ("future", "2026-03-01", "2025-12-31", "10-K")])

    def test_a_later_us_gaap_filing_does_not_erase_the_ifrs_years(self) -> None:
        filings = normalize_filed_facts(self.facts(), self.index(), as_of="2025-03-02")["filings"]

        self.assertEqual([filing["accounting_basis"] for filing in filings], ["IFRS"])
        self.assertEqual([fact["period"] for filing in filings for fact in filing["annual"]], ["2024"])

    def test_both_regimes_arrive_once_both_have_been_filed(self) -> None:
        filings = normalize_filed_facts(self.facts(), self.index(), as_of="2026-03-02")["filings"]

        self.assertEqual([(filing["form"], filing["accounting_basis"]) for filing in filings], [("20-F", "IFRS"), ("10-K", "US-GAAP")])


class TwoCurrenciesAreNotOneSeries(unittest.TestCase):
    """SEC stores a concept's facts in one array per unit, and the unit is the point.

    A hundred US dollars and a hundred and thirty Canadian ones are not thirty percent of
    growth. Collapsing the arrays loses the only thing that says so, and the rate goes out
    under the same field name as a rate that means something.
    """

    def test_growth_across_two_currencies_is_not_computed(self) -> None:
        facts = company_facts({"us-gaap": {"Revenues": {"units": {
            "USD": [{"start": "2024-01-01", "end": "2024-12-31", "val": 100.0, "accn": "a", "form": "10-K", "filed": "2025-02-20"}],
            "CAD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 130.0, "accn": "b", "form": "10-K", "filed": "2026-02-20"}],
        }}}})
        index = submissions([("a", "2025-02-20", "2024-12-31", "10-K"), ("b", "2026-02-20", "2025-12-31", "10-K")])
        reading = evaluate_fundamentals(normalize_filed_facts(facts, index, as_of="2026-03-01"), as_of="2026-03-01")["annual_growth"]

        self.assertIsNone(reading["revenue_yoy_pct"])
        self.assertEqual(reading["reason"], "annual_periods_measured_in_different_units")


class TwoClosesReachingOneNameSurviveTheBoundary(unittest.TestCase):
    """The period name is a projection, and the withholding rule needs both closes to fire.

    Deduplicating on the accession and the projected name alone keeps whichever fact the
    provider happened to send first, so the collision decision 280 exists to publish never
    reaches the evaluator -- and which figure survives depends on input order.
    """

    @staticmethod
    def rows() -> list[dict]:
        return [
            {"start": "2024-11-27", "end": "2025-02-15", "val": 1.0, "accn": "a", "filed": "2025-06-01", "form": "10-Q"},
            {"start": "2025-02-15", "end": "2025-05-06", "val": 2.0, "accn": "a", "filed": "2025-06-01", "form": "10-Q"},
        ]

    def normalized(self, rows: list[dict]) -> dict:
        facts = company_facts({"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": rows}}}})
        return normalize_filed_facts(facts, submissions([("a", "2025-06-01", "2025-05-06", "10-Q")]), as_of="2025-10-01")

    def test_both_closes_reach_the_evaluator(self) -> None:
        quarters = [fact["end"] for filing in self.normalized(self.rows())["filings"] for fact in filing["quarterly"]]

        self.assertEqual(sorted(quarters), ["2025-02-15", "2025-05-06"])

    def test_the_collided_period_is_withheld_and_named(self) -> None:
        missing = evaluate_fundamentals(self.normalized(self.rows()), as_of="2025-10-01")["missing"]

        self.assertIn("quarterly_periods_two_closes_reached", missing)

    def test_the_answer_does_not_depend_on_provider_order(self) -> None:
        forward = self.normalized(self.rows())
        backward = self.normalized(list(reversed(self.rows())))

        self.assertEqual(forward, backward)


class TheConceptListReachesTheNamesIFRSActuallyUses(unittest.TestCase):
    """`DilutedEarningsLossPerShare` is the IFRS diluted concept, and it was not in the list.

    The alias list carried the combined basic-and-diluted concept and not the diluted-only one,
    so a 20-F filer's earnings per share arrived as a provider gap -- evidence the company had
    filed, reported as evidence nobody had.
    """

    def test_an_ifrs_diluted_eps_fact_is_read(self) -> None:
        facts = company_facts({"ifrs-full": {"DilutedEarningsLossPerShare": {"units": {"USD/shares": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 2.5, "accn": "x", "form": "20-F", "filed": "2026-03-01"},
        ]}}}})
        filings = normalize_filed_facts(facts, submissions([("x", "2026-03-01", "2025-12-31", "20-F")]), as_of="2026-03-02")["filings"]

        self.assertEqual([fact["eps"] for filing in filings for fact in filing["annual"]], [2.5])


class TheCanadianAnnualFormIsAnAnnualFiling(unittest.TestCase):
    """This harness covers ADRs, and an MJDS filer's annual report is a 40-F.

    Dropping the form entirely turns every Canadian issuer into a company that has filed
    nothing. Like the 20-F it carries a year and no quarters, so it reads as annual-only rather
    than as three quarterly series a reader would keep re-fetching.
    """

    def test_a_forty_f_year_is_read(self) -> None:
        facts = company_facts({"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 2.5, "accn": "x", "form": "40-F", "filed": "2026-03-01"},
        ]}}}})
        payload = normalize_filed_facts(facts, submissions([("x", "2026-03-01", "2025-12-31", "40-F")]), as_of="2026-03-02")

        self.assertEqual([fact["eps"] for filing in payload["filings"] for fact in filing["annual"]], [2.5])
        self.assertIn("quarterly_facts_not_filed_by_this_registrant", evaluate_fundamentals(payload, as_of="2026-03-02")["missing"])


class ASessionTheIndexCannotReadIsNotASessionToDrop(unittest.TestCase):
    """An index entry that is not a date coerces to `NaT`, and `NaT <= as_of` is false.

    The row then disappears from a history whose coverage still says it is complete, so a
    session with a full set of prices is silently absent from every average built on it.
    """

    def test_an_unreadable_index_entry_is_typed_unavailability(self) -> None:
        frame = pd.DataFrame(
            {"Open": [10.0, 11.0, 12.0], "High": [11.0, 12.0, 13.0], "Low": [9.0, 10.0, 11.0], "Close": [10.0, 11.0, 12.0], "Volume": [100.0, 100.0, 100.0]},
            index=["2026-05-06", "not-a-session", "2026-05-08"],
        )

        with self.assertRaises(ProviderUnavailable) as raised:
            completed_daily_bars("TEST", as_of="2026-05-08", ticker=_Feed(frame), now=datetime(2026, 5, 9, tzinfo=timezone.utc), retrieved_at="2026-05-09T00:00:00Z")

        self.assertEqual(raised.exception.reason, "daily_bars_unreadable_session_index")


class ABarWhoseCloseIsOutsideItsRangeIsNotABar(unittest.TestCase):
    """A close above the high did not happen, and the boundary is where that is decided.

    Every measurement downstream reads the close as the session's price. Accepting one the same
    row says the session never reached publishes a multiple, a stop distance and an extension
    from a number the tape never printed.
    """

    def test_a_close_above_the_high_is_typed_unavailability(self) -> None:
        frame = pd.DataFrame(
            {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [200.0], "Volume": [1_000_000.0]},
            index=pd.to_datetime(["2026-05-08"]),
        )

        with self.assertRaises(ProviderUnavailable) as raised:
            completed_daily_bars("TEST", as_of="2026-05-08", ticker=_Feed(frame), now=datetime(2026, 5, 9, tzinfo=timezone.utc), retrieved_at="2026-05-09T00:00:00Z")

        self.assertEqual(raised.exception.reason, "daily_bars_impossible_session_range")


class _Feed:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def history(self, **kwargs) -> pd.DataFrame:
        return self._frame


if __name__ == "__main__":
    unittest.main()
