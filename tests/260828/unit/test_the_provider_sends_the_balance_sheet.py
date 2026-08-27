"""What `normalize_filed_facts` has to carry for the earnings-quality reading to exist.

Inventory and receivables are instant facts -- a balance at a date, not a flow over a period
-- so they arrive in companyfacts without a `start`. The annual period they belong to is the
one whose books close on that date.
"""

from __future__ import annotations

import unittest

from scripts.minervini.providers.sec import normalize_filed_facts


CIK = "0000000042"


def duration(period: str, start: str, end: str, val: float, accn: str, filed: str, form: str) -> dict:
    return {"start": start, "end": end, "val": val, "accn": accn, "filed": filed, "form": form, "fy": int(end[:4]), "fp": "FY", "frame": period}


def instant(end: str, val: float, accn: str, filed: str, form: str, *, fy: int | None = None) -> dict:
    # `fy` is the fiscal year of the report the fact appeared in, not of the balance date.
    # A prior-year comparative balance printed in this year's 10-K carries this year's `fy`.
    return {"end": end, "val": val, "accn": accn, "filed": filed, "form": form, "fy": fy or int(end[:4]), "fp": "FY", "frame": f"CY{end[:4]}Q4I"}


FILINGS = [("0000042-25-000001", "2025-02-20", "10-K"), ("0000042-26-000001", "2026-02-19", "10-K")]


def company_facts() -> dict:
    concepts = {
        "EarningsPerShareDiluted": ("USD/shares", [
            duration("CY2024", "2024-01-01", "2024-12-31", 2.30, *FILINGS[0]),
            duration("CY2025", "2025-01-01", "2025-12-31", 3.70, *FILINGS[1]),
        ]),
        "Revenues": ("USD", [
            duration("CY2024", "2024-01-01", "2024-12-31", 100.0, *FILINGS[0]),
            duration("CY2025", "2025-01-01", "2025-12-31", 110.0, *FILINGS[1]),
        ]),
        "InventoryNet": ("USD", [
            instant("2024-12-31", 40.0, *FILINGS[0]),
            instant("2025-12-31", 50.0, *FILINGS[1]),
            # The same 2024 balance, reprinted as the comparative column of the 2025 report.
            instant("2024-12-31", 40.0, *FILINGS[1], fy=2025),
        ]),
        "AccountsReceivableNetCurrent": ("USD", [instant("2024-12-31", 20.0, *FILINGS[0]), instant("2025-12-31", 26.0, *FILINGS[1])]),
    }
    return {
        "cik": int(CIK),
        "entityName": "Test Corp",
        "facts": {"us-gaap": {name: {"label": name, "units": {unit: rows}} for name, (unit, rows) in concepts.items()}},
    }


def submissions() -> dict:
    return {
        "cik": int(CIK),
        "filings": {"recent": {
            "accessionNumber": [row[0] for row in FILINGS],
            "filingDate": [row[1] for row in FILINGS],
            "reportDate": ["2024-12-31", "2025-12-31"],
            "form": [row[2] for row in FILINGS],
        }},
    }


class TheBalanceSheetTravelsWithTheAnnualPeriodItCloses(unittest.TestCase):
    def test_inventory_and_receivables_reach_the_annual_facts(self) -> None:
        normalized = normalize_filed_facts(company_facts(), submissions(), as_of="2026-05-08")

        annual = {fact["period"]: fact for filing in normalized["filings"] for fact in filing["annual"]}
        self.assertEqual(annual["2025"]["inventory"], 50.0)
        self.assertEqual(annual["2025"]["accounts_receivable"], 26.0)
        self.assertEqual(annual["2024"]["inventory"], 40.0)

    def test_a_comparative_prior_year_balance_belongs_to_the_year_it_closed(self) -> None:
        # Read from `fy` it would be filed under 2025 and overwrite that year's inventory
        # with the previous year's, which turns 25% growth into no growth at all.
        normalized = normalize_filed_facts(company_facts(), submissions(), as_of="2026-05-08")

        annual = {fact["period"]: fact for filing in normalized["filings"] for fact in filing["annual"]}
        self.assertEqual(annual["2025"]["inventory"], 50.0)
        self.assertEqual(annual["2025"]["end"], "2025-12-31")


if __name__ == "__main__":
    unittest.main()
