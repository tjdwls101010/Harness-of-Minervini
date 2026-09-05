"""The shape the SEC provider actually returns, evaluated.

`normalize_filed_facts` emits four things per filing: when it was filed, the accounting
basis, and the quarterly and annual facts. It emits no narrative. An evaluator that asks a
filing for a going-concern opinion or an accounting-integrity verdict is asking the provider
for something it has never sent, and every live request comes back INCOMPLETE for a reason
that has nothing to do with the company.

A check this harness does not run is a boundary of what it does, published once. It is not
missing evidence about a ticker, which is what it becomes when it is counted per request.
"""

from __future__ import annotations

from tests.filings import quarter as shared_quarter

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float, revenue: float, net_income: float, shares: float = 100.0) -> dict:
    return shared_quarter(period, end, eps, revenue=revenue, net_income=net_income, diluted_shares=shares)


# Eight quarters of year-over-year acceleration in earnings, sales and margin, and three
# annual periods growing with them. Nothing here is narrative -- it is what the provider sends.
ACCELERATING = {
    "source": "sec_filed_facts",
    "filings": [
        {
            "filed_at": "2026-05-01",
            "accounting_basis": "US-GAAP",
            "quarterly": [
                quarter("2024-Q1", "2024-03-31", 0.50, 100.0, 10.0),
                quarter("2024-Q2", "2024-06-30", 0.55, 110.0, 11.5),
                quarter("2024-Q3", "2024-09-30", 0.60, 120.0, 13.2),
                quarter("2024-Q4", "2024-12-31", 0.65, 130.0, 15.0),
                quarter("2025-Q1", "2025-03-31", 0.70, 140.0, 17.0),
                quarter("2025-Q2", "2025-06-30", 0.82, 158.0, 20.5),
                quarter("2025-Q3", "2025-09-30", 0.98, 182.0, 25.5),
                quarter("2025-Q4", "2025-12-31", 1.20, 215.0, 32.5),
            ],
            "annual": [
                {"period": "2023", "eps": 1.60, "revenue": 380.0},
                {"period": "2024", "eps": 2.30, "revenue": 460.0},
                {"period": "2025", "eps": 3.70, "revenue": 695.0},
            ],
        }
    ],
}


class AProviderShapedFilingReachesAVerdict(unittest.TestCase):
    def test_clean_accelerating_facts_support_convergence(self) -> None:
        result = evaluate_fundamentals(ACCELERATING, as_of="2026-05-10")

        self.assertEqual(result["fundamentals_state"], "supports_convergence")

    def test_a_check_the_harness_never_runs_is_not_a_gap_about_this_ticker(self) -> None:
        result = evaluate_fundamentals(ACCELERATING, as_of="2026-05-10")

        self.assertNotIn("going_concern", result["missing"])
        self.assertNotIn("accounting_integrity", result["missing"])
        self.assertNotIn("leader_category", result["missing"])


class TheClassificationIsTheAnalystsToMake(unittest.TestCase):
    def test_a_declared_category_is_read_and_an_undeclared_one_is_not_invented(self) -> None:
        undeclared = evaluate_fundamentals(ACCELERATING, as_of="2026-05-10")
        declared = evaluate_fundamentals(ACCELERATING, as_of="2026-05-10", leader_category="market_leader")

        self.assertIsNone(undeclared["leader_category"]["category"])
        self.assertEqual(undeclared["leader_category"]["state"], "not_declared")
        self.assertEqual(declared["leader_category"]["category"], "market_leader")


class ADeclaredGoingConcernIsStillRead(unittest.TestCase):
    def test_an_analyst_who_read_the_filing_can_hand_the_finding_in(self) -> None:
        result = evaluate_fundamentals(ACCELERATING, as_of="2026-05-10", going_concern="substantial_doubt")

        self.assertEqual(result["fundamentals_state"], "does_not_support_convergence")
        self.assertEqual(result["integrity"]["going_concern"]["state"], "contradicts")

    def test_with_nothing_declared_the_reading_names_its_own_boundary(self) -> None:
        result = evaluate_fundamentals(ACCELERATING, as_of="2026-05-10")

        self.assertEqual(result["integrity"]["going_concern"]["state"], "not_evaluated")
        self.assertEqual(result["integrity"]["going_concern"]["reason"], "narrative_disclosure_not_read_by_this_harness")


if __name__ == "__main__":
    unittest.main()
