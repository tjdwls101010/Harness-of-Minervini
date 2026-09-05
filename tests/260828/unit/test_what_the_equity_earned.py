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

from tests.filings import evidence as shared_evidence

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers.sec import normalize_filed_facts


def annual(year: int, **fields) -> dict:
    return {"period": str(year), "end": f"{year}-12-31", "eps": 1.00, "revenue": 100.0, **fields}


def evidence(years: list[dict], *, form: str = "10-K", quarterly: list[dict] | None = None) -> dict:
    return shared_evidence(form=form, quarters=quarterly or [], years=years)


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




class AFiscalYearThatDoesNotEndInDecember(unittest.TestCase):
    """The balance sheet closes on the company's year end, not on the calendar's.

    Requiring a 31 December date to recognise a year-end balance dropped every balance a
    September or January filer ever filed -- silently, because a dropped fact and a fact the
    company never filed look identical downstream. The fiscal year an instant belongs to is the
    one whose income statement closes on the same date, which the same taxonomy dump carries.
    """

    @staticmethod
    def facts(year_end: str, prior_end: str) -> dict:
        def duration(end: str, start: str, value: float, accession: str, filed: str) -> dict:
            return {"start": start, "end": end, "val": value, "accn": accession, "filed": filed, "form": "10-K", "fy": int(end[:4]), "fp": "FY"}

        def instant(end: str, value: float, accession: str, filed: str) -> dict:
            return {"end": end, "val": value, "accn": accession, "filed": filed, "form": "10-K", "fy": 2025, "fp": "FY"}

        return {
            "us-gaap": {
                "NetIncomeLoss": {"label": "n", "units": {"USD": [
                    duration(prior_end, f"{int(prior_end[:4]) - 1}-10-01", 20.0, "a-0", "2025-11-01"),
                    duration(year_end, f"{int(year_end[:4]) - 1}-10-01", 32.0, "a-1", "2026-02-19"),
                ]}},
                "StockholdersEquity": {"label": "e", "units": {"USD": [
                    instant(prior_end, 180.0, "a-1", "2026-02-19"),
                    instant(year_end, 200.0, "a-1", "2026-02-19"),
                ]}},
            }
        }

    def test_a_september_year_end_balance_reaches_the_evaluator(self) -> None:
        submissions = {"cik": 42, "filings": {"recent": {
            "accessionNumber": ["a-0", "a-1"],
            "filingDate": ["2025-11-01", "2026-02-19"],
            "reportDate": ["2025-09-27", "2025-09-27"],
            "form": ["10-K", "10-K"],
        }}}
        normalized = normalize_filed_facts({"cik": 42, "entityName": "T", "facts": self.facts("2025-09-27", "2024-09-28")}, submissions, as_of="2026-05-08")

        years = {year["period"]: year for filing in normalized["filings"] for year in filing["annual"]}
        self.assertEqual(years["2025"]["stockholders_equity"], 200.0)
        self.assertEqual(years["2024"]["stockholders_equity"], 180.0)

    def test_the_comparative_column_still_lands_on_its_own_year(self) -> None:
        submissions = {"cik": 42, "filings": {"recent": {
            "accessionNumber": ["a-0", "a-1"],
            "filingDate": ["2025-11-01", "2026-02-19"],
            "reportDate": ["2025-09-27", "2025-09-27"],
            "form": ["10-K", "10-K"],
        }}}
        normalized = normalize_filed_facts({"cik": 42, "entityName": "T", "facts": self.facts("2025-09-27", "2024-09-28")}, submissions, as_of="2026-05-08")

        years = {year["period"]: year for filing in normalized["filings"] for year in filing["annual"]}
        # Both instants carry fy 2025 because that is the report they were printed in. Reading
        # that field would file last year's equity under this year and erase a year of change.
        self.assertNotEqual(years["2024"]["stockholders_equity"], years["2025"]["stockholders_equity"])


if __name__ == "__main__":
    unittest.main()
