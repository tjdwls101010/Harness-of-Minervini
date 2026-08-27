"""Return on equity, and the registrant who never files a quarter.

ROE is a comparison the source makes against the industry group, and this evaluator holds one
company -- so the band is measured and the peer comparison is named as the half that is
missing. Two of the practitioners this harness reads say they never look at it at all, and the
registry records that disagreement, so it travels with the reading.

Separately: a foreign private issuer files an annual 20-F and no quarterly reports. Every
quarterly claim is then unavailable forever, and saying "quarterly_eps missing" reads like data
that might turn up. It never will, and the gap should say which.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers.sec import normalize_filed_facts


def annual(year: int, **fields) -> dict:
    return {"period": str(year), "end": f"{year}-12-31", "eps": 1.00, "revenue": 100.0, **fields}


def evidence(years: list[dict], *, form: str = "10-K", quarterly: list[dict] | None = None) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": form, "accounting_basis": "US-GAAP", "quarterly": quarterly or [], "annual": years}]}


class WhatTheEquityEarned(unittest.TestCase):
    def test_sixteen_percent_sits_inside_the_range_the_source_gave(self) -> None:
        years = [annual(2025, net_income=32.0, stockholders_equity=200.0)]
        reading = evaluate_fundamentals(evidence(years), as_of="2026-05-08")["profitability"]["return_on_equity"]

        self.assertEqual(reading["period"], "2025")
        self.assertEqual(reading["roe_pct"], 16.0)
        self.assertEqual(reading["band"]["source_range"], [15, 17])
        self.assertEqual(reading["band"]["state"], "within_source_range")

    def test_the_peer_comparison_is_the_half_this_evaluator_does_not_hold(self) -> None:
        years = [annual(2025, net_income=32.0, stockholders_equity=200.0)]
        reading = evaluate_fundamentals(evidence(years), as_of="2026-05-08")["profitability"]["return_on_equity"]

        self.assertEqual(reading["missing_inputs"], ["industry_group_roe_comparison"])
        self.assertEqual(len(reading["disagrees_with"]), 2)

    def test_without_equity_on_file_there_is_no_ratio(self) -> None:
        reading = evaluate_fundamentals(evidence([annual(2025, net_income=32.0)]), as_of="2026-05-08")["profitability"]["return_on_equity"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "annual_net_income_and_stockholders_equity_required")
        self.assertEqual(reading["band"]["state"], "unavailable")

    def test_equity_that_went_negative_has_no_meaningful_return(self) -> None:
        years = [annual(2025, net_income=32.0, stockholders_equity=-50.0)]
        reading = evaluate_fundamentals(evidence(years), as_of="2026-05-08")["profitability"]["return_on_equity"]

        self.assertEqual(reading["state"], "not_meaningful")
        self.assertEqual(reading["reason"], "stockholders_equity_not_positive")


class ARegistrantThatNeverFilesAQuarter(unittest.TestCase):
    def test_an_annual_only_filer_names_why_the_quarters_are_absent(self) -> None:
        result = evaluate_fundamentals(evidence([annual(2024), annual(2025)], form="20-F"), as_of="2026-05-08")

        self.assertEqual(result["missing"], ["quarterly_facts_not_filed_by_this_registrant"])
        self.assertEqual(result["fundamentals_state"], "incomplete")

    def test_a_domestic_filer_missing_quarters_still_reports_them_one_by_one(self) -> None:
        result = evaluate_fundamentals(evidence([annual(2024), annual(2025)]), as_of="2026-05-08")

        self.assertIn("quarterly_eps", result["missing"])
        self.assertNotIn("quarterly_facts_not_filed_by_this_registrant", result["missing"])


class TheProviderSendsTheEquity(unittest.TestCase):
    def test_stockholders_equity_and_annual_net_income_reach_the_evaluator(self) -> None:
        facts = {
            "us-gaap": {
                "NetIncomeLoss": {"label": "NetIncomeLoss", "units": {"USD": [
                    {"start": "2025-01-01", "end": "2025-12-31", "val": 32.0, "accn": "a-1", "filed": "2026-02-19", "form": "10-K", "fy": 2025, "fp": "FY", "frame": "CY2025"},
                ]}},
                "StockholdersEquity": {"label": "StockholdersEquity", "units": {"USD": [
                    {"end": "2025-12-31", "val": 200.0, "accn": "a-1", "filed": "2026-02-19", "form": "10-K", "fy": 2025, "fp": "FY"},
                ]}},
            }
        }
        submissions = {"cik": 42, "filings": {"recent": {"accessionNumber": ["a-1"], "filingDate": ["2026-02-19"], "reportDate": ["2025-12-31"], "form": ["10-K"]}}}
        normalized = normalize_filed_facts({"cik": 42, "entityName": "T", "facts": facts}, submissions, as_of="2026-05-08")

        year = normalized["filings"][0]["annual"][0]
        self.assertEqual(year["net_income"], 32.0)
        self.assertEqual(year["stockholders_equity"], 200.0)


if __name__ == "__main__":
    unittest.main()
