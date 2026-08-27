"""A measurement made of two numbers needs both of them measured the same way.

The margin already refused to divide US-GAAP earnings by IFRS sales, and decision 275 says why:
provenance is per number, and a filer that changes regime carries both in one period. Every
other measurement built from two numbers was still reading whatever the period happened to
hold -- year-over-year growth, the annual pair, the trailing year and return on equity all
crossed the boundary the margin was refusing to cross.

The provider had a matching hole. It accepts the IFRS taxonomy but looked for balance-sheet
facts under US-GAAP names only, so a 20-F filer's equity and inventory were dropped before any
provenance rule could see them -- and return on equity came back as evidence nobody filed.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers.sec import normalize_filed_facts


def filing(filed_at: str, basis: str, *, quarterly: list[dict] | None = None, annual: list[dict] | None = None) -> dict:
    return {"filed_at": filed_at, "form": "10-K", "accounting_basis": basis, "quarterly": quarterly or [], "annual": annual or []}


def quarter(period: str, end: str, eps: float) -> dict:
    return {"period": period, "end": end, "eps": eps, "revenue": 100.0, "net_income": eps * 10, "diluted_shares": 100.0}


def read(filings: list[dict], **declared) -> dict:
    return evaluate_fundamentals({"source": "sec_filed_facts", "filings": filings}, as_of="2026-05-08", **declared)


class GrowthIsNotMeasuredAcrossARegimeChange(unittest.TestCase):
    def test_a_quarter_filed_under_another_regime_has_no_year_over_year_pair(self) -> None:
        filings = [
            filing("2025-05-01", "US-GAAP", quarterly=[quarter("2024-Q1", "2024-03-31", 1.0)]),
            filing("2026-05-01", "IFRS", quarterly=[quarter("2025-Q1", "2025-03-31", 2.0)]),
        ]
        result = read(filings)

        self.assertEqual(result["quarterly"]["eps_yoy_growth"], [])
        self.assertEqual(result["growth"]["minimum_quarterly_earnings_growth"]["state"], "unavailable")

    def test_two_annual_years_under_different_regimes_are_not_a_pair(self) -> None:
        filings = [
            filing("2025-02-20", "US-GAAP", annual=[{"period": "2024", "end": "2024-12-31", "eps": 2.0, "revenue": 200.0}]),
            filing("2026-02-20", "IFRS", annual=[{"period": "2025", "end": "2025-12-31", "eps": 2.6, "revenue": 260.0}]),
        ]
        growth = read(filings)["annual_growth"]

        self.assertIsNone(growth["eps_yoy_pct"])
        self.assertIsNone(growth["revenue_yoy_pct"])
        self.assertEqual(growth["reason"], "annual_periods_measured_under_different_accounting_bases")


class TheReturnOnEquityDividesOneRegimeByItself(unittest.TestCase):
    def test_earnings_from_one_regime_over_equity_from_another_is_refused(self) -> None:
        year = {"period": "2025", "end": "2025-12-31", "net_income": 20.0}
        filings = [
            filing("2026-02-20", "US-GAAP", annual=[year]),
            filing("2026-03-20", "IFRS", annual=[{"period": "2025", "end": "2025-12-31", "stockholders_equity": 100.0}]),
        ]
        reading = read(filings)["profitability"]["return_on_equity"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "net_income_and_equity_measured_under_different_accounting_bases")


class AnIfrsBalanceSheetReachesTheEvaluator(unittest.TestCase):
    @staticmethod
    def company_facts() -> dict:
        duration = {"start": "2024-01-01", "end": "2024-12-31", "accn": "f", "filed": "2025-03-01", "form": "20-F"}
        instant = {"end": "2024-12-31", "accn": "f", "filed": "2025-03-01", "form": "20-F"}
        return {"cik": 1, "facts": {"ifrs-full": {
            "ProfitLoss": {"units": {"USD": [{**duration, "val": 20.0}]}},
            "Revenue": {"units": {"USD": [{**duration, "val": 100.0}]}},
            "Equity": {"units": {"USD": [{**instant, "val": 80.0}]}},
            "Inventories": {"units": {"USD": [{**instant, "val": 10.0}]}},
        }}}

    @staticmethod
    def submissions() -> dict:
        return {"cik": 1, "filings": {"recent": {"accessionNumber": ["f"], "filingDate": ["2025-03-01"], "reportDate": ["2024-12-31"], "form": ["20-F"]}}}

    def test_equity_filed_under_ifrs_is_not_dropped(self) -> None:
        evidence = normalize_filed_facts(self.company_facts(), self.submissions(), as_of="2025-03-02")
        reading = evaluate_fundamentals(evidence, as_of="2025-03-02")["profitability"]["return_on_equity"]

        self.assertEqual(reading["state"], "reported")
        self.assertEqual(reading["roe_pct"], 25.0)

    def test_inventory_filed_under_ifrs_is_not_dropped(self) -> None:
        evidence = normalize_filed_facts(self.company_facts(), self.submissions(), as_of="2025-03-02")
        year = evidence["filings"][0]["annual"][0]

        self.assertEqual(year["inventory"], 10.0)



class TheTrailingYearIsSummedInsideOneRegime(unittest.TestCase):
    def test_a_regime_change_inside_the_window_leaves_no_trailing_year(self) -> None:
        under = [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", 0.25) for n in range(3)]
        filings = [
            filing("2025-01-15", "US-GAAP", quarterly=under),
            filing("2025-05-01", "IFRS", quarterly=[quarter("2024-Q4", "2024-12-31", 0.25)]),
        ]
        reading = read(filings, last_close=50.0)["valuation"]["price_earnings_ratio"]

        self.assertIsNone(reading["trailing_12m_eps"])
        self.assertEqual(reading["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
