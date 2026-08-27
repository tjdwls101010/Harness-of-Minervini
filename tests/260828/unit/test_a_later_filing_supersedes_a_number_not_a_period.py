"""A later filing restates the numbers it mentions, and says nothing about the ones it does not.

A 10-Q carries a comparative balance sheet: last fiscal year's equity, inventory and
receivables, and no income statement for that year. Letting the later filing replace the whole
period erased the revenue and earnings the annual report had filed -- so the latest fiscal year
came out holding a balance sheet and nothing to measure it against, while every earlier year,
whose 10-Qs had aged out of the eligible window, looked complete.

Later-filed wins per field. That is what a restatement is.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def filing(filed_at: str, form: str, annual: list[dict]) -> dict:
    return {"filed_at": filed_at, "form": form, "accounting_basis": "US-GAAP", "quarterly": [], "annual": annual}


class ARestatementIsPerNumber(unittest.TestCase):
    def test_a_comparative_balance_sheet_does_not_erase_the_income_statement(self) -> None:
        evidence = {"source": "sec_filed_facts", "filings": [
            filing("2025-11-01", "10-K", [{"period": "2025", "end": "2025-09-27", "eps": 6.00, "revenue": 400.0, "net_income": 100.0, "stockholders_equity": 500.0}]),
            # The next quarter's report carries last year's balance sheet as a comparative and
            # no income statement for it at all.
            filing("2026-02-01", "10-Q", [{"period": "2025", "end": "2025-09-27", "stockholders_equity": 500.0}]),
        ]}
        result = evaluate_fundamentals(evidence, as_of="2026-05-08")

        self.assertEqual(result["annual_growth"]["periods"], ["2025"])
        self.assertEqual(result["profitability"]["return_on_equity"]["period"], "2025")
        self.assertEqual(result["profitability"]["return_on_equity"]["roe_pct"], 20.0)

    def test_a_restated_number_is_the_one_that_stands(self) -> None:
        evidence = {"source": "sec_filed_facts", "filings": [
            filing("2025-11-01", "10-K", [{"period": "2025", "end": "2025-09-27", "revenue": 400.0, "net_income": 100.0, "stockholders_equity": 500.0}]),
            filing("2026-02-01", "10-K/A", [{"period": "2025", "end": "2025-09-27", "net_income": 90.0}]),
        ]}
        result = evaluate_fundamentals(evidence, as_of="2026-05-08")

        reading = result["profitability"]["return_on_equity"]
        self.assertEqual(reading["net_income"], 90.0)
        self.assertEqual(reading["stockholders_equity"], 500.0)

    def test_the_filing_a_period_is_credited_to_is_the_latest_that_spoke_about_it(self) -> None:
        evidence = {"source": "sec_filed_facts", "filings": [
            filing("2025-11-01", "10-K", [{"period": "2025", "end": "2025-09-27", "eps": 6.00, "revenue": 400.0}]),
            filing("2026-02-01", "10-Q", [{"period": "2025", "end": "2025-09-27", "stockholders_equity": 500.0}]),
        ]}
        result = evaluate_fundamentals(evidence, as_of="2026-05-08")

        # Provenance travels with the merged fact: the reader asking when a number was published
        # gets the filing that last spoke about the period, not the one that opened it.
        self.assertEqual(result["filings_used"], ["2025-11-01", "2026-02-01"])


if __name__ == "__main__":
    unittest.main()
