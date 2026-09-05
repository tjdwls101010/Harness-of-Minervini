"""A period's name comes from the date it closed, and two periods cannot share one name.

Decision 277 named a duration fact by the calendar quarter its span sat in. That reads the
start date as well as the end, and the start is the half an amendment can move: a 10-K/A
correcting a 52-week span to 53 weeks pushed the midpoint back across New Year, so the amended
year arrived as the year before and was compared against the original it was meant to replace.
The close is what a fiscal period is identified by, and an amendment never moves it.

The projection is still a projection, so it can still collide. Two duration facts that closed
on different dates and reached the same name are not a restatement of one period, and merging
them keeps one figure and discards the other with nothing said. The period is withheld instead.

And two annual periods whose spans overlap are not a year and the year before it. That reaches
the evaluator through a fiscal-year change, so the start dates travel with the facts.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers.sec import normalize_filed_facts


def facts(rows: list[tuple[str, str, str, float, str, str]]) -> dict:
    return {"cik": 1, "facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": [
        {"start": start, "end": end, "val": value, "accn": accn, "filed": filed, "form": form}
        for start, end, value, accn, filed, form in rows
    ]}}}}}


def submissions(rows: list[tuple[str, str, str, float, str, str]]) -> dict:
    seen: dict[str, tuple[str, str, str]] = {}
    for _, end, _, accn, filed, form in rows:
        seen[accn] = (filed, form, end)
    return {"cik": 1, "filings": {"recent": {
        "accessionNumber": list(seen),
        "filingDate": [value[0] for value in seen.values()],
        "form": [value[1] for value in seen.values()],
        "reportDate": [value[2] for value in seen.values()],
    }}}


def annual_periods(rows: list[tuple], as_of: str) -> list[tuple[str, float]]:
    evidence = normalize_filed_facts(facts(rows), submissions(rows), as_of=as_of)
    return [(fact["period"], fact.get("eps")) for filing in evidence["filings"] for fact in filing["annual"]]


class AnAmendmentCorrectsAYearRatherThanAddingOne(unittest.TestCase):
    def test_a_corrected_span_keeps_the_year_its_close_names(self) -> None:
        rows = [
            ("2024-07-04", "2025-07-02", 1.0, "a", "2025-08-01", "10-K"),
            ("2024-06-27", "2025-07-02", 1.2, "b", "2025-08-15", "10-K/A"),
        ]

        self.assertEqual(annual_periods(rows, "2025-09-01"), [("2025", 1.0), ("2025", 1.2)])

    def test_the_amended_figure_supersedes_rather_than_becoming_a_prior_year(self) -> None:
        rows = [
            ("2024-07-04", "2025-07-02", 1.0, "a", "2025-08-01", "10-K"),
            ("2024-06-27", "2025-07-02", 1.2, "b", "2025-08-15", "10-K/A"),
        ]
        evidence = normalize_filed_facts(facts(rows), submissions(rows), as_of="2025-09-01")
        growth = evaluate_fundamentals(evidence, as_of="2025-09-01")["annual_growth"]

        self.assertEqual(growth["periods"], [None, "2025"])
        self.assertIsNone(growth["eps_yoy_pct"])

    def test_two_consecutive_fifty_two_week_years_stay_two_years(self) -> None:
        rows = [
            ("2022-07-04", "2023-07-03", 1.0, "a", "2023-08-01", "10-K"),
            ("2023-07-04", "2024-07-01", 1.2, "b", "2024-08-01", "10-K"),
        ]

        self.assertEqual(annual_periods(rows, "2024-09-01"), [("2023", 1.0), ("2024", 1.2)])

    def test_a_close_that_drifts_across_the_cutoff_is_withheld_rather_than_merged(self) -> None:
        # A year ending 1 July and the next ending 30 June project into the same calendar year.
        # No rule reading one date alone avoids that for every close, so the two are named as a
        # collision rather than folded into one year whose figure is whichever arrived last.
        rows = [
            ("2023-07-04", "2024-07-01", 1.0, "a", "2024-08-01", "10-K"),
            ("2024-07-02", "2025-06-30", 1.2, "b", "2025-08-01", "10-K"),
        ]
        evidence = normalize_filed_facts(facts(rows), submissions(rows), as_of="2025-09-01")
        result = evaluate_fundamentals(evidence, as_of="2025-09-01")

        self.assertEqual(result["annual_growth"]["periods"], [None, None])
        self.assertIn("annual_periods_two_closes_reached", result["missing"])


class TwoClosesCannotShareOneName(unittest.TestCase):
    def test_a_period_two_different_closes_reached_is_withheld(self) -> None:
        # Eighty days apart, and both closes project into calendar Q1.
        rows = [
            ("2024-11-27", "2025-02-15", 1.0, "a", "2025-03-01", "10-Q"),
            ("2025-02-15", "2025-05-06", 2.0, "b", "2025-06-01", "10-Q"),
        ]
        evidence = normalize_filed_facts(facts(rows), submissions(rows), as_of="2025-10-01")
        result = evaluate_fundamentals(evidence, as_of="2025-10-01")

        self.assertEqual(result["quarterly"]["eps"], [])
        self.assertIn("quarterly_periods_two_closes_reached", result["missing"])


class TwoYearsThatOverlapAreNotAPair(unittest.TestCase):
    def test_an_overlapping_prior_year_is_not_compared(self) -> None:
        rows = [
            ("2023-04-01", "2024-03-31", 1.0, "a", "2024-05-01", "10-K"),
            ("2024-01-01", "2024-12-31", 2.0, "b", "2025-02-01", "10-K"),
        ]
        evidence = normalize_filed_facts(facts(rows), submissions(rows), as_of="2025-03-01")
        growth = evaluate_fundamentals(evidence, as_of="2025-03-01")["annual_growth"]

        self.assertIsNone(growth["eps_yoy_pct"])
        self.assertEqual(growth["reason"], "annual_periods_overlap")


if __name__ == "__main__":
    unittest.main()
