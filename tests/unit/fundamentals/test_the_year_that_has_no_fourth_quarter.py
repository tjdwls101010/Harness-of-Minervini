"""No filer publishes a fourth quarter, so a trailing year cannot be four filed quarters.

A 10-K states the fiscal year and the three 10-Qs state the first three quarters. Nobody files
a fourth-quarter column, so for every US filer the run of four consecutive quarters this
evaluator was summing does not exist -- and the price-earnings ratio came back `unavailable`
for NVDA, ANET and AAPL alike, naming four consecutive filed quarters as what it lacked.

The twelve months are still on file, in three numbers rather than four: the last complete
fiscal year, plus the quarters filed since it closed, minus the same quarters of the year
before. Nothing is reconstructed and no quarter nobody filed is published -- the subtraction
runs on filed figures only, and it produces exactly the window a trailing year means.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers.sec import normalize_filed_facts


AS_OF = "2026-08-27"

# (accession, form, filed, [(start, end, eps)]) -- a January-closing filer, as SEC returns it.
_FILINGS = [
    ("0000042-24-000002", "10-Q", "2024-08-28", [("2024-04-29", "2024-07-28", 0.67)]),
    ("0000042-24-000003", "10-Q", "2024-11-20", [("2024-07-29", "2024-10-27", 0.78)]),
    ("0000042-25-000001", "10-K", "2025-02-26", [("2024-01-29", "2025-01-26", 2.94)]),
    ("0000042-25-000002", "10-Q", "2025-05-28", [("2025-01-27", "2025-04-27", 0.76)]),
    ("0000042-25-000003", "10-Q", "2025-08-27", [("2025-04-28", "2025-07-27", 1.08)]),
    ("0000042-25-000004", "10-Q", "2025-11-19", [("2025-07-28", "2025-10-26", 1.30)]),
    ("0000042-26-000001", "10-K", "2026-02-25", [("2025-01-27", "2026-01-25", 4.90)]),
    ("0000042-26-000002", "10-Q", "2026-05-20", [("2026-01-26", "2026-04-26", 2.39)]),
    ("0000042-26-000003", "10-Q", "2026-08-26", [("2026-04-27", "2026-07-26", 2.46)]),
]


def company_facts() -> dict:
    rows = [
        {"start": start, "end": end, "val": eps, "accn": accn, "filed": filed, "form": form, "fy": int(end[:4]), "fp": "FY" if form == "10-K" else "Q1"}
        for accn, form, filed, facts in _FILINGS
        for start, end, eps in facts
    ]
    return {
        "cik": 42,
        "entityName": "January Close, Inc.",
        "facts": {"us-gaap": {"EarningsPerShareDiluted": {"label": "EPS diluted", "units": {"USD/shares": rows}}}},
    }


def submissions() -> dict:
    return {
        "cik": 42,
        "filings": {"recent": {
            "accessionNumber": [row[0] for row in _FILINGS],
            "filingDate": [row[2] for row in _FILINGS],
            "reportDate": [row[3][-1][1] for row in _FILINGS],
            "form": [row[1] for row in _FILINGS],
        }},
    }


def valuation(**declared) -> dict:
    evidence = normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
    return evaluate_fundamentals(evidence, as_of=AS_OF, **declared)["valuation"]


class TheTrailingYearIsBuiltFromWhatWasFiled(unittest.TestCase):
    def test_the_fourth_quarter_is_absent_from_the_filings(self) -> None:
        evidence = normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
        quarters = {fact["period"] for filing in evidence["filings"] for fact in filing["quarterly"]}

        self.assertEqual(sorted(quarters), ["2024-Q2", "2024-Q3", "2025-Q1", "2025-Q2", "2025-Q3", "2026-Q1", "2026-Q2"])

    def test_the_trailing_year_is_the_last_full_year_rolled_forward(self) -> None:
        # 4.90 for the year closed 2026-01-25, plus 2.39 and 2.46 filed since, minus the 0.76
        # and 1.08 those two quarters replace.
        reading = valuation(last_close=79.10)["price_earnings_ratio"]

        self.assertEqual(reading["state"], "reported")
        self.assertEqual(reading["trailing_12m_eps"], 7.91)
        self.assertEqual(reading["pe_ratio"], 10.0)

    def test_the_route_the_trailing_year_came_by_is_published(self) -> None:
        reading = valuation(last_close=79.10)["price_earnings_ratio"]

        self.assertEqual(reading["trailing_12m_route"], "annual_rolled_forward_by_filed_quarters")


class AQuarterMissingFromTheRollForwardIsAHoleInTheYear(unittest.TestCase):
    """The quarters since the close have to be all of them, not merely consecutive with each other.

    Filed Q2 alone, with Q1 absent, is consecutive with itself and ends at the quarter being
    measured, so the subtraction ran and quietly assumed Q1 was unchanged year over year. On the
    fixture above that publishes 6.28 where the twelve months were 7.91 -- a fifth of the
    earnings dropped, with nothing in the envelope saying so.
    """

    @staticmethod
    def without_the_first_quarter() -> list[tuple]:
        return [row for row in _FILINGS if row[0] != "0000042-26-000002"]

    def test_a_hole_between_the_close_and_the_latest_quarter_leaves_no_trailing_year(self) -> None:
        global _FILINGS
        kept, _FILINGS = _FILINGS, self.without_the_first_quarter()
        try:
            reading = valuation(last_close=79.10)["price_earnings_ratio"]
        finally:
            _FILINGS = kept

        self.assertIsNone(reading["trailing_12m_eps"])
        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["missing_inputs"], ["filed_quarters_for_a_complete_trailing_year"])



_CALENDAR = [
    ("0000043-24-000001", "10-Q", "2024-05-01", [("2024-01-01", "2024-03-31", 0.90)]),
    ("0000043-24-000002", "10-Q", "2024-08-01", [("2024-04-01", "2024-06-30", 1.00)]),
    ("0000043-24-000003", "10-Q", "2024-11-01", [("2024-07-01", "2024-09-30", 1.05)]),
    ("0000043-25-000001", "10-K", "2025-02-20", [("2024-01-01", "2024-12-31", 4.00)]),
    ("0000043-25-000002", "10-Q", "2025-05-01", [("2025-01-01", "2025-03-31", 1.10)]),
    ("0000043-25-000003", "10-Q", "2025-08-01", [("2025-04-01", "2025-06-30", 1.20)]),
    ("0000043-25-000004", "10-Q", "2025-11-03", [("2025-07-01", "2025-09-30", 1.30)]),
    ("0000043-26-000001", "10-K", "2026-02-20", [("2025-01-01", "2025-12-31", 5.00)]),
]


def calendar_valuation(filings: list[tuple], **declared) -> dict:
    global _FILINGS
    kept, _FILINGS = _FILINGS, filings
    try:
        return valuation(**declared)
    finally:
        _FILINGS = kept


class TheYearRolledForwardIsOneThatHadClosed(unittest.TestCase):
    """The fiscal year has to have closed before the quarter being measured.

    The latest 10-K on file covers a year that ends after the latest 10-Q's quarter, so taking
    "the latest annual" rather than "the latest annual that had closed" rolls a quarter forward
    from a year it is inside. Every window in the series is built the same way, so the prior
    peak the turnaround reads goes with it.
    """

    def test_the_trailing_year_uses_the_year_that_closed_before_this_quarter(self) -> None:
        # Latest quarter is 2025-Q3; the 2025 fiscal year has not closed at that point, so the
        # year rolled forward is 2024: 4.00 plus 3.60 filed since, minus the 2.95 those replace.
        reading = calendar_valuation(_CALENDAR, last_close=46.50)["price_earnings_ratio"]

        self.assertEqual(reading["trailing_12m_eps"], 4.65)
        self.assertEqual(reading["trailing_12m_route"], "annual_rolled_forward_by_filed_quarters")


class ATrailingYearThatDoesNotReachTheLatestQuarterIsNotCurrent(unittest.TestCase):
    def test_an_unmatchable_latest_quarter_leaves_the_trailing_year_absent(self) -> None:
        # 2024-Q3 is gone, so 2025-Q3 has nothing to replace and the only windows that can be
        # built end earlier. An earlier window is a historical figure, not today's denominator.
        without_the_replaced_quarter = [row for row in _CALENDAR if row[0] != "0000043-24-000003"]
        reading = calendar_valuation(without_the_replaced_quarter, last_close=46.50)["price_earnings_ratio"]

        self.assertIsNone(reading["trailing_12m_eps"])
        self.assertEqual(reading["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
