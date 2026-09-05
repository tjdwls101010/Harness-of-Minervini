"""What happens between a finite filed figure and a published one.

Every input here is a number a filer could tag, and every output is a number binary64 cannot
hold. The refusals that exist check the inputs and the sums; nothing was checking the quotient
those sums went into, so a state was chosen before the value that state describes existed --
and `reported` went out beside a null, while `inf >= inf` became affirmative evidence about a
turnaround nobody could measure.
"""

from __future__ import annotations

from tests.filings import evidence as shared_evidence

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def filing(quarterly: list[dict] | None = None, years: list[dict] | None = None) -> dict:
    return shared_evidence(filed_at="2026-02-01", quarters=quarterly or [], years=years or [])


_ENDS = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


class AnOverflowedTrailingYearIsNotEvidenceOfARecovery(unittest.TestCase):
    """`inf >= inf` is true, and it is not a company that got back to its old peak.

    Both figures are refused on the way out, so the reading publishes two nulls -- and beside
    them a boolean and a `satisfied` that were computed from the infinities. A criterion
    answered from numbers nobody is allowed to see is the plainest form of a verdict without
    evidence.
    """

    def test_a_turnaround_route_computed_from_infinities_stays_unknown(self) -> None:
        quarters = [{"period": f"2024-Q{index}", "end": f"2024-{_ENDS[index]}", "eps": 1e308, "revenue": 1e308, "net_income": 1e308} for index in (1, 2, 3, 4)]
        quarters.append({"period": "2025-Q1", "end": "2025-03-31", "eps": 1e308, "revenue": 1e308, "net_income": 1e308})
        reading = evaluate_fundamentals(filing(quarterly=quarters), as_of="2026-05-01", leader_category="turnaround")["category_reading"]["readings"]["turnaround_qualifying_criteria"]

        self.assertIsNone(reading["trailing_12m_eps"])
        self.assertIsNone(reading["trailing_12m_eps_at_or_above_prior_peak"])
        self.assertIsNone(reading["satisfied"])


class AQuotientThatOverflowedWasNotReported(unittest.TestCase):
    """The inputs are finite, the sums are finite, and the division is not.

    `_reported` turns the infinity into a null on the way out, which is correct -- but the
    state was chosen before it, so the block says `reported` and carries no ratio. A reader
    cannot tell that from a number the filings never had.
    """

    @staticmethod
    def payload() -> dict:
        quarters = [{"period": f"2025-Q{index}", "end": f"2025-{_ENDS[index]}", "eps": 2.5e-309} for index in (1, 2, 3, 4)]
        year = {"period": "2025", "start": "2025-01-01", "end": "2025-12-31", "net_income": 1e308, "stockholders_equity": 1e-308}
        return evaluate_fundamentals(filing(quarterly=quarters, years=[year]), as_of="2026-05-01", last_close=1e308)

    def test_the_multiple_says_the_division_overflowed(self) -> None:
        reading = self.payload()["valuation"]["price_earnings_ratio"]

        self.assertEqual(reading["state"], "not_meaningful")
        self.assertEqual(reading["reason"], "price_earnings_ratio_beyond_arithmetic_range")
        self.assertIsNone(reading["pe_ratio"])

    def test_the_return_on_equity_says_the_same(self) -> None:
        reading = self.payload()["profitability"]["return_on_equity"]

        self.assertEqual(reading["state"], "not_meaningful")
        self.assertEqual(reading["reason"], "return_on_equity_beyond_arithmetic_range")
        self.assertIsNone(reading["roe_pct"])


class TwoQuartersSevenApartAreNotSequential(unittest.TestCase):
    """Deceleration is this quarter against the one before it, and the one before it has to exist.

    Taking the last two surviving points of a series answers with whatever survived. On a
    history with a hole in it that is a rate from two years ago called "previous", and a
    company that grew faster every year reads as decelerating.
    """

    def test_a_gap_between_the_last_two_rates_leaves_deceleration_unread(self) -> None:
        quarters = [
            {"period": "2024-Q1", "end": "2024-03-31", "eps": 0.10, "revenue": 100.0, "net_income": 10.0, "diluted_shares": 50.0},
            {"period": "2025-Q1", "end": "2025-03-31", "eps": 0.30, "revenue": 100.0, "net_income": 30.0, "diluted_shares": 50.0},
            {"period": "2025-Q4", "end": "2025-12-31", "eps": 0.40, "revenue": 100.0, "net_income": 40.0, "diluted_shares": 50.0},
            {"period": "2026-Q4", "end": "2026-12-31", "eps": 0.80, "revenue": 100.0, "net_income": 80.0, "diluted_shares": 100.0},
        ]
        reading = evaluate_fundamentals(filing(quarterly=quarters), as_of="2027-03-01")["growth"]["earnings_deceleration"]

        self.assertEqual(reading["reason"], "no_adjacent_quarter_to_compare")
        self.assertEqual(reading["periods"], ["2025-Q1", "2026-Q4"])
        self.assertIsNone(reading["decelerated"])


if __name__ == "__main__":
    unittest.main()
