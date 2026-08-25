"""The deeper allowance belongs to a long correction, not to any base that asks for it."""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.technical import build_eligibility_evidence


def base(*, peak_position: int, trough: float, **judgments: str) -> dict:
    peak, sessions, last = 100.0, 60, 99.0
    closes = [peak * (0.6 + 0.35 * (index + 1) / (peak_position + 1)) for index in range(peak_position)]
    closes.append(peak)
    remaining = sessions - peak_position - 2
    step = (last - trough) / remaining
    closes.append(trough)
    closes.extend(trough + step * (index + 1) for index in range(remaining - 1))
    closes.append(last)
    frame = pd.DataFrame({"Close": closes}, index=pd.bdate_range(end="2026-08-21", periods=len(closes)))
    evidence = build_eligibility_evidence(frame, rs_rating=85, **judgments)
    return next(
        claim for claim in evidence["primary_base"]["quantitative_claims"]
        if claim["id"] == "primary_base.duration_depth"
    )


class YearLongExceptionScopeTests(unittest.TestCase):
    def test_a_four_week_base_cannot_claim_the_year_long_allowance(self) -> None:
        # 20 sessions is four weeks. No confirmation can make that about a year.
        claim = base(peak_position=39, trough=60.0, primary_base_long_correction="confirmed")

        self.assertEqual(claim["state"], "fail")

    def test_a_correction_long_enough_to_be_about_a_year_may_use_it(self) -> None:
        claim = base(peak_position=10, trough=60.0, primary_base_long_correction="confirmed")

        self.assertEqual(claim["state"], "pass")

    def test_a_long_correction_without_confirmation_stays_unresolved(self) -> None:
        self.assertEqual(base(peak_position=10, trough=60.0)["state"], "unavailable")

    def test_the_ordinary_ceiling_still_applies_either_side_of_five_weeks(self) -> None:
        # Same depth, one session apart across the boundary: the ceiling does not move,
        # only whether the year-long exception is available at all.
        self.assertEqual(base(peak_position=34, trough=70.0)["state"], "pass")
        self.assertEqual(base(peak_position=33, trough=70.0)["state"], "pass")


if __name__ == "__main__":
    unittest.main()
