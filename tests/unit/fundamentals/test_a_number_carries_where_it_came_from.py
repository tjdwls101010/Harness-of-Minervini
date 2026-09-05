"""Provenance is per number, and a boundary that lets a bad value through is not a boundary.

Merging a later filing's numbers into a period was right; relabelling the numbers it never
mentioned with its own filing date and accounting basis was not. A revenue figure filed under
US-GAAP came out stamped IFRS, and the margin built from it divided one regime's earnings by
another's sales.

Beside that, three boundaries that were letting through what they exist to stop: a fiscal-year
map built from filings the request may not see, a `nan` that reached a published reading and
then broke strict JSON, and a growth rate from a starting balance of zero reported as though it
had been computed.
"""

from __future__ import annotations

from tests.filings import evidence as shared_evidence, filing as shared_filing

import json
import math
import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers.sec import normalize_filed_facts


def evidence(filings: list[dict]) -> dict:
    return shared_evidence(filings=filings)


def filing(filed_at: str, form: str, basis: str, quarterly: list[dict] | None = None, annual: list[dict] | None = None) -> dict:
    return shared_filing(filed_at=filed_at, form=form, basis=basis, quarterly=quarterly or [], years=annual or [])


class EachNumberSaysWhichFilingItCameFrom(unittest.TestCase):
    def test_a_later_filing_does_not_restamp_the_numbers_it_never_mentioned(self) -> None:
        result = evaluate_fundamentals(evidence([
            filing("2025-04-01", "10-Q", "US-GAAP", [{"period": "2025-Q1", "end": "2025-03-31", "revenue": 100.0, "net_income": 10.0}]),
            filing("2025-05-01", "10-Q/A", "IFRS", [{"period": "2025-Q1", "end": "2025-03-31", "net_income": 20.0}]),
        ]), as_of="2025-05-02")

        revenue = result["quarterly"]["revenue"][0]
        self.assertEqual(revenue["accounting_basis"], "US-GAAP")
        self.assertEqual(revenue["filed_at"], "2025-04-01")

    def test_a_margin_is_not_built_across_two_accounting_regimes(self) -> None:
        result = evaluate_fundamentals(evidence([
            filing("2025-04-01", "10-Q", "US-GAAP", [{"period": "2025-Q1", "end": "2025-03-31", "revenue": 100.0, "net_income": 10.0}]),
            filing("2025-05-01", "10-Q/A", "IFRS", [{"period": "2025-Q1", "end": "2025-03-31", "net_income": 20.0}]),
        ]), as_of="2025-05-02")

        self.assertEqual(result["quarterly"]["margin_pct"], [])

    def test_one_regime_throughout_still_publishes_the_margin(self) -> None:
        result = evaluate_fundamentals(evidence([
            filing("2025-04-01", "10-Q", "US-GAAP", [{"period": "2025-Q1", "end": "2025-03-31", "revenue": 100.0, "net_income": 10.0}]),
            filing("2025-05-01", "10-Q/A", "US-GAAP", [{"period": "2025-Q1", "end": "2025-03-31", "net_income": 20.0}]),
        ]), as_of="2025-05-02")

        margin = result["quarterly"]["margin_pct"][0]
        self.assertEqual(margin["value"], 20.0)
        self.assertEqual(margin["filed_at"], "2025-05-01")


class ANumberThatIsNotANumber(unittest.TestCase):
    def test_the_provider_refuses_a_non_finite_fact(self) -> None:
        facts = {"us-gaap": {"StockholdersEquity": {"label": "e", "units": {"USD": [
            {"end": "2025-12-31", "val": float("nan"), "accn": "a-1", "filed": "2026-02-19", "form": "10-K", "fy": 2025, "fp": "FY"},
        ]}}, "Revenues": {"label": "r", "units": {"USD": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 100.0, "accn": "a-1", "filed": "2026-02-19", "form": "10-K", "fy": 2025, "fp": "FY", "frame": "CY2025"},
        ]}}}}
        submissions = {"cik": 42, "filings": {"recent": {"accessionNumber": ["a-1"], "filingDate": ["2026-02-19"], "reportDate": ["2025-12-31"], "form": ["10-K"]}}}
        normalized = normalize_filed_facts({"cik": 42, "entityName": "T", "facts": facts}, submissions, as_of="2026-05-08")

        self.assertNotIn("stockholders_equity", normalized["filings"][0]["annual"][0])

    def test_a_non_finite_value_never_reaches_a_published_reading(self) -> None:
        result = evaluate_fundamentals(evidence([
            filing("2026-02-19", "10-K", "US-GAAP", annual=[{"period": "2025", "end": "2025-12-31", "eps": 1.0, "revenue": 100.0, "net_income": 32.0, "stockholders_equity": float("nan")}]),
        ]), as_of="2026-05-08")

        reading = result["profitability"]["return_on_equity"]
        self.assertEqual(reading["state"], "unavailable")
        self.assertIsNone(reading["roe_pct"])

    def test_the_whole_payload_survives_strict_json(self) -> None:
        result = evaluate_fundamentals(evidence([
            filing("2026-02-19", "10-K", "US-GAAP", annual=[{"period": "2025", "end": "2025-12-31", "eps": float("inf"), "revenue": 100.0}]),
        ]), as_of="2026-05-08")

        json.dumps(result, allow_nan=False)


class AZeroStartingBalanceIsNotAGrowthRate(unittest.TestCase):
    def test_the_reading_does_not_call_itself_reported_with_nothing_computed(self) -> None:
        annual = [
            {"period": "2024", "end": "2024-12-31", "eps": 1.0, "revenue": 100.0, "inventory": 0.0, "accounts_receivable": 10.0},
            {"period": "2025", "end": "2025-12-31", "eps": 1.1, "revenue": 110.0, "inventory": 10.0, "accounts_receivable": 13.0},
        ]
        result = evaluate_fundamentals(evidence([filing("2026-02-19", "10-K", "US-GAAP", annual=annual)]), as_of="2026-05-08")

        reading = result["earnings_quality"]["inventory_receivables_vs_sales"]
        self.assertEqual(reading["state"], "not_meaningful")
        self.assertEqual(reading["reason"], "a_balance_that_started_at_zero_has_no_growth_rate")


class TheFiscalYearMapSeesOnlyWhatTheRequestSees(unittest.TestCase):
    def test_a_filing_after_as_of_does_not_date_an_earlier_balance(self) -> None:
        facts = {"us-gaap": {
            "InventoryNet": {"label": "i", "units": {"USD": [
                {"end": "2024-12-31", "val": 40.0, "accn": "a-1", "filed": "2025-01-15", "form": "10-K", "fy": 2024, "fp": "FY"},
            ]}},
            "Revenues": {"label": "r", "units": {"USD": [
                {"start": "2024-01-01", "end": "2024-12-31", "val": 100.0, "accn": "a-2", "filed": "2025-02-20", "form": "10-K/A", "fy": 2024, "fp": "FY", "frame": "CY2024"},
            ]}},
        }}
        submissions = {"cik": 42, "filings": {"recent": {
            "accessionNumber": ["a-1", "a-2"],
            "filingDate": ["2025-01-15", "2025-02-20"],
            "reportDate": ["2024-12-31", "2024-12-31"],
            "form": ["10-K", "10-K/A"],
        }}}
        normalized = normalize_filed_facts({"cik": 42, "entityName": "T", "facts": facts}, submissions, as_of="2025-01-31")

        # The only fact naming 2024 as a fiscal year was filed three weeks after the request's
        # own boundary. Nothing the request can see says the balance belongs to 2024.
        self.assertEqual([year for f in normalized["filings"] for year in f["annual"]], [])


if __name__ == "__main__":
    unittest.main()
