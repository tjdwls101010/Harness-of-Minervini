"""Only a gate rejects a base. The band travels beside it and reports where it landed."""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.technical import build_eligibility_evidence


def history(*, sessions: int, peak_position: int, peak: float, trough: float, last: float) -> pd.DataFrame:
    closes = [peak * (0.6 + 0.35 * (index + 1) / (peak_position + 1)) for index in range(peak_position)]
    closes.append(peak)
    remaining = sessions - peak_position - 2
    step = (last - trough) / remaining
    closes.append(trough)
    closes.extend(trough + step * (index + 1) for index in range(remaining - 1))
    closes.append(last)
    return pd.DataFrame({"Close": closes}, index=pd.bdate_range(end="2026-08-21", periods=len(closes)))


def primary_base(*, peak_position: int, trough: float) -> dict:
    frame = history(sessions=60, peak_position=peak_position, peak=100.0, trough=trough, last=99.0)
    return build_eligibility_evidence(frame, rs_rating=85)["primary_base"]


def depth_claim(base: dict) -> dict:
    return next(claim for claim in base["quantitative_claims"] if claim["id"] == "primary_base.duration_depth")


class DepthRoleTests(unittest.TestCase):
    def test_the_rejecting_claim_is_a_gate_with_a_gate_s_wording(self) -> None:
        claim = depth_claim(primary_base(peak_position=10, trough=45.0))

        self.assertEqual(claim["state"], "fail")
        self.assertNotIn("source_range", claim["basis"])
        self.assertNotIn("band_position", claim["basis"])

    def test_the_band_is_reported_beside_the_claim_not_as_the_claim(self) -> None:
        base = primary_base(peak_position=10, trough=70.0)

        band = base["depth_band"]
        self.assertEqual(band["role"], "band")
        self.assertEqual(band["source_range"], [25, 35])
        self.assertEqual(band["measured"], 30.0)
        self.assertEqual(band["band_position"], 0.5)
        self.assertIn("quotation", band)

    def test_two_depths_inside_the_band_report_different_positions(self) -> None:
        loose = primary_base(peak_position=10, trough=66.0)["depth_band"]
        tight = primary_base(peak_position=10, trough=74.0)["depth_band"]

        self.assertEqual(loose["state"], tight["state"])
        self.assertGreater(loose["band_position"], tight["band_position"])

    def test_a_session_either_side_of_five_weeks_gets_the_same_verdict(self) -> None:
        # The old code routed on a duration reference, so 25 sessions failed and 26 went
        # unavailable at the same depth. A reference may not decide anything.
        at_five_weeks = depth_claim(primary_base(peak_position=34, trough=60.0))
        past_five_weeks = depth_claim(primary_base(peak_position=33, trough=60.0))

        self.assertEqual(at_five_weeks["state"], past_five_weeks["state"])


if __name__ == "__main__":
    unittest.main()
