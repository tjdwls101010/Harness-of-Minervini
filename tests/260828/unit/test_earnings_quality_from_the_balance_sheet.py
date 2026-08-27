"""The earnings-quality reading the filed numbers can actually make.

The source's tell is that inventory and receivables should rise and fall roughly with
sales, and that both growing at twice the sales rate without explanation is "double
trouble". All three numbers are filed, so this is a measurement rather than a narrative --
which is what makes it the replacement for an accounting-integrity verdict the provider
never sent.

It is an interpretation, not a hard gate: a finding prompts review. So it is reported with
its gate state beside it and never turns a verdict on its own.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def annual(period: str, eps: float, revenue: float, **balance: float) -> dict:
    return {"period": period, "eps": eps, "revenue": revenue, **balance}


# Eight quarters of accelerating growth, so the growth half of the verdict is settled and
# whatever the balance-sheet reading does is visible on its own.
QUARTERS = [
    {"period": "2024-Q1", "end": "2024-03-31", "eps": 0.50, "revenue": 100.0, "net_income": 10.0, "diluted_shares": 100.0},
    {"period": "2024-Q2", "end": "2024-06-30", "eps": 0.55, "revenue": 110.0, "net_income": 11.5, "diluted_shares": 100.0},
    {"period": "2024-Q3", "end": "2024-09-30", "eps": 0.60, "revenue": 120.0, "net_income": 13.2, "diluted_shares": 100.0},
    {"period": "2024-Q4", "end": "2024-12-31", "eps": 0.65, "revenue": 130.0, "net_income": 15.0, "diluted_shares": 100.0},
    {"period": "2025-Q1", "end": "2025-03-31", "eps": 0.70, "revenue": 140.0, "net_income": 17.0, "diluted_shares": 100.5},
    {"period": "2025-Q2", "end": "2025-06-30", "eps": 0.82, "revenue": 158.0, "net_income": 20.5, "diluted_shares": 100.5},
    {"period": "2025-Q3", "end": "2025-09-30", "eps": 0.98, "revenue": 182.0, "net_income": 25.5, "diluted_shares": 101.0},
    {"period": "2025-Q4", "end": "2025-12-31", "eps": 1.20, "revenue": 215.0, "net_income": 32.5, "diluted_shares": 101.0},
]


def filings(*, this_year: dict, last_year: dict) -> dict:
    return {
        "source": "sec_filed_facts",
        "filings": [{
            "filed_at": "2026-02-19",
            "accounting_basis": "US-GAAP",
            "quarterly": QUARTERS,
            "annual": [{"period": "2023", "eps": 1.60, "revenue": 340.0}, last_year, this_year],
        }],
    }


class BothGrowingAtTwiceTheSalesRateIsDoubleTrouble(unittest.TestCase):
    def test_the_reading_names_the_finding_without_turning_the_verdict(self) -> None:
        # Sales +10%; receivables +30% and inventory +25% -- both above twice the sales rate.
        evidence = filings(
            last_year=annual("2024", 2.30, 100.0, inventory=40.0, accounts_receivable=20.0),
            this_year=annual("2025", 3.70, 110.0, inventory=50.0, accounts_receivable=26.0),
        )
        result = evaluate_fundamentals(evidence, as_of="2026-05-10")

        reading = result["earnings_quality"]["inventory_receivables_vs_sales"]
        self.assertEqual(reading["state"], "double_trouble")
        self.assertEqual(reading["revenue_growth_pct"], 10.0)
        self.assertEqual(reading["accounts_receivable_growth_pct"], 30.0)
        self.assertEqual(reading["inventory_growth_pct"], 25.0)
        self.assertEqual(reading["doctrine_id"], "fundamentals.inventory_receivables_vs_sales")

    def test_the_finding_does_not_move_the_verdict_the_growth_facts_settled(self) -> None:
        # An interpretation prompts review. The same growth facts must reach the same state
        # whether the balance sheet ran ahead of sales or tracked it.
        flagged = evaluate_fundamentals(filings(
            last_year=annual("2024", 2.30, 100.0, inventory=40.0, accounts_receivable=20.0),
            this_year=annual("2025", 3.70, 110.0, inventory=50.0, accounts_receivable=26.0),
        ), as_of="2026-05-10")
        clean = evaluate_fundamentals(filings(
            last_year=annual("2024", 2.30, 100.0, inventory=40.0, accounts_receivable=20.0),
            this_year=annual("2025", 3.70, 110.0, inventory=44.0, accounts_receivable=22.0),
        ), as_of="2026-05-10")

        self.assertEqual(flagged["earnings_quality"]["inventory_receivables_vs_sales"]["state"], "double_trouble")
        self.assertEqual(clean["earnings_quality"]["inventory_receivables_vs_sales"]["state"], "reported")
        self.assertEqual(flagged["fundamentals_state"], clean["fundamentals_state"])

    def test_one_of_the_two_running_ahead_is_not_the_double_finding(self) -> None:
        evidence = filings(
            last_year=annual("2024", 2.30, 100.0, inventory=40.0, accounts_receivable=20.0),
            this_year=annual("2025", 3.70, 110.0, inventory=50.0, accounts_receivable=21.0),
        )
        result = evaluate_fundamentals(evidence, as_of="2026-05-10")

        self.assertEqual(result["earnings_quality"]["inventory_receivables_vs_sales"]["state"], "reported")

    def test_balance_growing_with_sales_is_the_pattern_the_source_expects(self) -> None:
        evidence = filings(
            last_year=annual("2024", 2.30, 100.0, inventory=40.0, accounts_receivable=20.0),
            this_year=annual("2025", 3.70, 110.0, inventory=44.0, accounts_receivable=22.0),
        )
        result = evaluate_fundamentals(evidence, as_of="2026-05-10")

        reading = result["earnings_quality"]["inventory_receivables_vs_sales"]
        self.assertEqual(reading["state"], "reported")
        self.assertEqual(reading["inventory_vs_sales_ratio"], 1.0)
        self.assertEqual(reading["accounts_receivable_vs_sales_ratio"], 1.0)


class ACompanyWithNoInventoryIsNotACompanyWithMissingEvidence(unittest.TestCase):
    def test_the_reading_names_what_the_filings_did_not_carry(self) -> None:
        evidence = filings(
            last_year=annual("2024", 2.30, 100.0),
            this_year=annual("2025", 3.70, 110.0),
        )
        result = evaluate_fundamentals(evidence, as_of="2026-05-10")

        reading = result["earnings_quality"]["inventory_receivables_vs_sales"]
        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["missing_inputs"], ["accounts_receivable", "inventory"])
        self.assertNotIn("inventory_receivables_vs_sales", result["missing"])


class ShrinkingSalesCannotBeGrownFasterThan(unittest.TestCase):
    def test_a_ratio_against_a_fall_is_withheld_rather_than_signed(self) -> None:
        # Sales fell. Dividing a rise by a fall gives a negative ratio that reads as "well
        # inside the limit" when the finding is the opposite, so no ratio is published.
        evidence = filings(
            last_year=annual("2024", 2.30, 100.0, inventory=40.0, accounts_receivable=20.0),
            this_year=annual("2025", 3.70, 90.0, inventory=50.0, accounts_receivable=26.0),
        )
        result = evaluate_fundamentals(evidence, as_of="2026-05-10")

        reading = result["earnings_quality"]["inventory_receivables_vs_sales"]
        self.assertIsNone(reading["inventory_vs_sales_ratio"])
        self.assertEqual(reading["state"], "sales_did_not_grow")
        self.assertEqual(reading["inventory_growth_pct"], 25.0)


if __name__ == "__main__":
    unittest.main()
