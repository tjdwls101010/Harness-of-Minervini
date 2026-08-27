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


if __name__ == "__main__":
    unittest.main()
