"""A band contributes to convergence. It never decides it.

The governing contract says so in as many words, and the branch was breaking it in the one place
it mattered most: the latest quarter's growth landing inside 20-25 percent produced
`supports_convergence` on its own, and `ticker.risk` consumes that as the fundamentals leg of a
prospective entry. A company whose annual earnings and sales had both halved cleared it.

Convergence is the source's own word for a conjunction. What replaces the single band is every
polarity-bearing reading this evaluator publishes, each named with what it said -- and no-trade
is the default when any of them prompts review, because marginal evidence never earns a pass.
"""

from __future__ import annotations

from tests.filings import evidence as shared_evidence, quarter as shared_quarter

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, eps: float, revenue: float = 100.0, net_income: float = 10.0) -> dict:
    ends = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}
    year, label = period.split("-")
    return shared_quarter(period, f"{year}-{ends[label]}", eps, revenue=revenue, net_income=net_income)


def year(period: str, eps: float, revenue: float) -> dict:
    return {"period": period, "end": f"{period}-12-31", "eps": eps, "revenue": revenue}


def evidence(quarters: list[dict], annual: list[dict]) -> dict:
    return shared_evidence(filed_at="2026-02-20", quarters=quarters, years=annual)


def eight(latest_growth_pct: float) -> list[dict]:
    base = [quarter(f"2024-Q{n}", 1.00) for n in range(1, 5)]
    return base + [quarter(f"2025-Q{n}", 1.00 * (1 + latest_growth_pct / 100)) for n in range(1, 5)]


class TheAnnualCollapseIsNotOverruledByOneQuarter(unittest.TestCase):
    def test_a_quarter_inside_the_range_does_not_carry_a_halved_year(self) -> None:
        result = evaluate_fundamentals(evidence(eight(20.0), [year("2024", 2.00, 200.0), year("2025", 1.00, 100.0)]), as_of="2026-05-08")

        self.assertEqual(result["growth"]["minimum_quarterly_earnings_growth"]["state"], "within_source_range")
        self.assertEqual(result["fundamentals_state"], "does_not_support_convergence")
        self.assertIn("annual_earnings_did_not_grow", result["quality"]["review_reasons"])

    def test_everything_agreeing_still_supports_convergence(self) -> None:
        result = evaluate_fundamentals(evidence(eight(30.0), [year("2024", 2.00, 200.0), year("2025", 2.60, 260.0)]), as_of="2026-05-08")

        self.assertEqual(result["quality"]["state"], "supports")
        self.assertEqual(result["quality"]["review_reasons"], [])
        self.assertEqual(result["fundamentals_state"], "supports_convergence")

    def test_the_verdict_names_every_reading_that_took_part_not_one(self) -> None:
        result = evaluate_fundamentals(evidence(eight(30.0), [year("2024", 2.00, 200.0), year("2025", 2.60, 260.0)]), as_of="2026-05-08")

        # `decided_by` used to name the single band. Convergence is a conjunction, so what is
        # published is the whole conjunction -- otherwise the page says one claim decided
        # something several readings had to agree on.
        self.assertIn("fundamentals.minimum_quarterly_earnings_growth", result["quality"]["read"])
        self.assertIn("fundamentals.annual_earnings_requirement", result["quality"]["read"])
        self.assertNotIn("decided_by", result["quality"])

    def test_sales_falling_while_earnings_rise_prompts_review_rather_than_a_pass(self) -> None:
        result = evaluate_fundamentals(evidence(eight(30.0), [year("2024", 2.00, 200.0), year("2025", 2.60, 180.0)]), as_of="2026-05-08")

        self.assertEqual(result["quality"]["state"], "review")
        self.assertIn("annual_sales_did_not_grow", result["quality"]["review_reasons"])
        self.assertEqual(result["fundamentals_state"], "does_not_support_convergence")

    def test_a_quarter_short_of_the_range_still_prompts_review(self) -> None:
        result = evaluate_fundamentals(evidence(eight(10.0), [year("2024", 2.00, 200.0), year("2025", 2.60, 260.0)]), as_of="2026-05-08")

        self.assertIn("quarterly_earnings_growth_below_source_range", result["quality"]["review_reasons"])
        self.assertEqual(result["fundamentals_state"], "does_not_support_convergence")


class ReviewIsNotRejection(unittest.TestCase):
    def test_the_state_word_says_it_does_not_support_rather_than_that_it_failed(self) -> None:
        result = evaluate_fundamentals(evidence(eight(20.0), [year("2024", 2.00, 200.0), year("2025", 1.00, 100.0)]), as_of="2026-05-08")

        # Every fundamentals claim in the registry carries `needs_review`, so nothing here can
        # reject. "Does not support" is the no-trade default, not a verdict the corpus granted.
        self.assertEqual(result["quality"]["state"], "review")
        self.assertNotIn("contradicts", result["quality"]["state"])

    def test_missing_evidence_is_still_incomplete_rather_than_review(self) -> None:
        result = evaluate_fundamentals(evidence(eight(30.0), []), as_of="2026-05-08")

        self.assertEqual(result["quality"]["state"], "unavailable")
        self.assertEqual(result["fundamentals_state"], "incomplete")


if __name__ == "__main__":
    unittest.main()
