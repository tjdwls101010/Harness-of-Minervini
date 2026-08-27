"""Two things this evaluator was publishing that no source says.

A ten-percent quarterly share-count rise turned into `contradicts` and could reject a
candidate outright. Neither corpus mentions dilution at all -- the word appears zero times
in both -- so the limit was the harness's own, wearing the shape of doctrine. The share
count is a filed fact worth putting in front of a reader; the verdict on it was not.

The other is what a filing amendment is. An amended 10-K restates numbers that were already
published, which is provenance the reader should have. It is not a finding about the
company, because no source in this harness's corpus says a restatement is one.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, shares: float) -> dict:
    return {"period": period, "end": end, "eps": 1.0, "revenue": 100.0, "net_income": 10.0, "diluted_shares": shares}


def filings(*quarters: dict, amended: list[str] | None = None) -> dict:
    filing = {"filed_at": "2026-02-19", "accounting_basis": "US-GAAP", "quarterly": list(quarters), "annual": []}
    if amended is not None:
        filing["amended_periods"] = amended
        filing["form"] = "10-K/A"
    return {"source": "sec_filed_facts", "filings": [filing]}


class TheShareCountIsReportedAndNeverJudged(unittest.TestCase):
    def test_a_large_quarterly_rise_is_a_measurement_not_a_contradiction(self) -> None:
        result = evaluate_fundamentals(filings(quarter("2025-Q3", "2025-09-30", 100.0), quarter("2025-Q4", "2025-12-31", 130.0)), as_of="2026-05-10")

        dilution = result["integrity"]["dilution"]
        self.assertEqual(dilution["state"], "reported")
        self.assertEqual(dilution["quarterly_share_change_pct"], 30.0)
        self.assertNotEqual(result["fundamentals_state"], "does_not_support_convergence")

    def test_the_reading_names_no_claim_because_no_source_states_one(self) -> None:
        result = evaluate_fundamentals(filings(quarter("2025-Q3", "2025-09-30", 100.0), quarter("2025-Q4", "2025-12-31", 101.0)), as_of="2026-05-10")

        self.assertNotIn("doctrine_id", result["integrity"]["dilution"])
        self.assertNotIn("binds", result["integrity"]["dilution"])

    def test_an_absent_share_count_is_not_a_gap_in_a_verdict_nothing_gates_on(self) -> None:
        bare = {"period": "2025-Q4", "end": "2025-12-31", "eps": 1.0, "revenue": 100.0, "net_income": 10.0}
        result = evaluate_fundamentals({"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "accounting_basis": "US-GAAP", "quarterly": [bare], "annual": []}]}, as_of="2026-05-10")

        self.assertEqual(result["integrity"]["dilution"]["state"], "unavailable")
        self.assertNotIn("dilution", result["missing"])


class AnAmendedFilingSaysSo(unittest.TestCase):
    def test_the_reading_carries_which_filings_were_amendments(self) -> None:
        result = evaluate_fundamentals(filings(quarter("2025-Q4", "2025-12-31", 100.0), amended=["2025-Q4"]), as_of="2026-05-10")

        self.assertEqual(result["amended_filings"], [{"filed_at": "2026-02-19", "form": "10-K/A"}])

    def test_an_amendment_is_provenance_and_not_a_finding_about_the_company(self) -> None:
        amended = evaluate_fundamentals(filings(quarter("2025-Q3", "2025-09-30", 100.0), quarter("2025-Q4", "2025-12-31", 101.0), amended=["2025-Q4"]), as_of="2026-05-10")
        original = evaluate_fundamentals(filings(quarter("2025-Q3", "2025-09-30", 100.0), quarter("2025-Q4", "2025-12-31", 101.0)), as_of="2026-05-10")

        self.assertEqual(amended["fundamentals_state"], original["fundamentals_state"])
        self.assertEqual(original["amended_filings"], [])


if __name__ == "__main__":
    unittest.main()
