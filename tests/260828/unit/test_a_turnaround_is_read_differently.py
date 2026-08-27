"""The same earnings history read as a turnaround, which the source holds to a different bar.

A turnaround is up against easy comparisons, so the source raises the bar rather than lowering
it: a hundred percent or better in the recent quarters, and either two strong quarters or one
big enough to carry trailing twelve-month earnings back to its old peak. Both are gates.

"Strong" is not defined in the two-quarter claim; the registry says so and points at the
hundred-percent claim for the quantified version, so that is what strong means here. "Near" its
old peak is not defined at all, so only "at or above" is measured and near is named as unread.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float) -> dict:
    return {"period": period, "end": end, "eps": eps, "revenue": 100.0, "net_income": eps * 10, "diluted_shares": 100.0}


def evidence(quarters: list[dict]) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": quarters, "annual": []}]}


def two_years(recent: list[float], base: float = 0.10) -> list[dict]:
    rows = [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", base) for n in range(4)]
    rows += [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", recent[n]) for n in range(4)]
    return rows


def turnaround(quarters: list[dict]) -> dict:
    return evaluate_fundamentals(evidence(quarters), as_of="2026-05-08", leader_category="turnaround")["category_reading"]["readings"]


class TheHundredPercentBar(unittest.TestCase):
    def test_three_quarters_of_doubling_clear_the_gate(self) -> None:
        reading = turnaround(two_years([0.15, 0.30, 0.40, 0.50]))

        growth = reading["turnaround_growth_rate_threshold"]
        self.assertEqual(growth["window_quarters"], [1, 3])
        self.assertEqual([(q["period"], q["state"]) for q in growth["window"]], [("2025-Q2", "pass"), ("2025-Q3", "pass"), ("2025-Q4", "pass")])
        self.assertEqual(growth["window_quarters_passing"], 3)

    def test_a_fifty_percent_rise_does_not_clear_it(self) -> None:
        reading = turnaround(two_years([0.15, 0.15, 0.15, 0.15]))

        growth = reading["turnaround_growth_rate_threshold"]
        self.assertEqual(growth["window_quarters_passing"], 0)
        self.assertEqual(growth["window"][-1]["measured"], 50.0)


class TwoStrongQuartersOrOneBigEnough(unittest.TestCase):
    def test_two_quarters_over_the_bar_satisfy_the_criterion(self) -> None:
        reading = turnaround(two_years([0.10, 0.10, 0.40, 0.50]))

        criteria = reading["turnaround_qualifying_criteria"]
        self.assertEqual(criteria["strong_quarters"], 2)
        self.assertEqual(criteria["gate"]["state"], "pass")
        self.assertEqual(criteria["strong_means"], "fundamentals.turnaround_growth_rate_threshold")

    def test_one_strong_quarter_alone_does_not(self) -> None:
        reading = turnaround(two_years([0.10, 0.10, 0.10, 0.50]))

        criteria = reading["turnaround_qualifying_criteria"]
        self.assertEqual(criteria["strong_quarters"], 1)
        self.assertEqual(criteria["gate"]["state"], "fail")

    def test_the_trailing_twelve_months_back_at_its_old_peak_is_the_other_route(self) -> None:
        # Peaks at 1.00 across 2023, collapses through 2024, and one 2025 quarter carries the
        # trailing figure back over the old high.
        rows = [quarter(f"2023-Q{n + 1}", f"2023-{(n + 1) * 3:02d}-30", 0.25) for n in range(4)]
        rows += [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", 0.05) for n in range(4)]
        rows += [quarter("2025-Q1", "2025-03-30", 0.05), quarter("2025-Q2", "2025-06-30", 0.05), quarter("2025-Q3", "2025-09-30", 0.05), quarter("2025-Q4", "2025-12-30", 0.90)]
        reading = turnaround(rows)

        criteria = reading["turnaround_qualifying_criteria"]
        self.assertEqual(criteria["trailing_12m_eps"], 1.05)
        self.assertEqual(criteria["trailing_12m_eps_prior_peak"], 1.00)
        self.assertIs(criteria["trailing_12m_eps_at_or_above_prior_peak"], True)
        self.assertIs(criteria["satisfied"], True)

    def test_near_the_old_peak_is_named_as_a_judgement_the_source_left_open(self) -> None:
        # One quarter well over the bar, but the trailing figure is nowhere near the old peak.
        # Whether 0.45 against 1.00 counts as "near" is the judgement the source left open, so
        # what is published is the two numbers and the fact that nobody quantified the word.
        rows = [quarter(f"2023-Q{n + 1}", f"2023-{(n + 1) * 3:02d}-30", 0.25) for n in range(4)]
        rows += [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", 0.05) for n in range(4)]
        rows += [quarter("2025-Q1", "2025-03-30", 0.05), quarter("2025-Q2", "2025-06-30", 0.05), quarter("2025-Q3", "2025-09-30", 0.05), quarter("2025-Q4", "2025-12-30", 0.30)]
        criteria = turnaround(rows)["turnaround_qualifying_criteria"]

        self.assertEqual(criteria["trailing_12m_eps"], 0.45)
        self.assertEqual(criteria["trailing_12m_eps_prior_peak"], 1.00)
        self.assertIs(criteria["trailing_12m_eps_at_or_above_prior_peak"], False)
        self.assertEqual(criteria["unquantified"], ["near_prior_peak_is_unquantified"])
        # Below the peak is not a failed criterion. "Near or above" is a disjunction whose
        # second half nobody quantified, so it can be satisfied or open and never refused.
        self.assertIsNone(criteria["satisfied"])


class TheCategoryDecidesWhatIsRead(unittest.TestCase):
    def test_an_undeclared_category_reads_no_category_claim(self) -> None:
        result = evaluate_fundamentals(evidence(two_years([0.15, 0.30, 0.40, 0.50])), as_of="2026-05-08")

        self.assertEqual(result["category_reading"], {"state": "not_declared", "category": None, "readings": {}})

    def test_a_market_leader_is_not_held_to_the_turnaround_bar(self) -> None:
        result = evaluate_fundamentals(evidence(two_years([0.15, 0.30, 0.40, 0.50])), as_of="2026-05-08", leader_category="market_leader")

        self.assertNotIn("turnaround_growth_rate_threshold", result["category_reading"]["readings"])


if __name__ == "__main__":
    unittest.main()
