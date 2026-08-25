"""Primary Base depth bands follow the source's three-week, three-to-five-week, and longer-correction cases."""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini.technical import build_eligibility_evidence


def history(*, sessions: int, peak_position: int, peak: float, trough: float, last: float) -> pd.DataFrame:
    """Build a completed-bar series with one prior peak, one base trough, and a chosen last close."""

    closes = [peak * (0.6 + 0.35 * (index + 1) / (peak_position + 1)) for index in range(peak_position)]
    closes.append(peak)
    remaining = sessions - peak_position - 2
    if remaining < 1:
        raise ValueError("series is too short for a base after the peak")
    step = (last - trough) / remaining
    closes.append(trough)
    closes.extend(trough + step * (index + 1) for index in range(remaining - 1))
    closes.append(last)
    index = pd.bdate_range(end="2026-08-21", periods=len(closes))
    return pd.DataFrame({"Close": closes}, index=index)


def base_claim(frame: pd.DataFrame, identifier: str, **judgments: str) -> dict:
    evidence = build_eligibility_evidence(frame, rs_rating=85, **judgments)
    claims = evidence["primary_base"]["quantitative_claims"]
    return next(claim for claim in claims if claim["id"] == identifier)


class PrimaryBaseDepthBandTests(unittest.TestCase):
    def test_three_week_base_rejects_a_correction_deeper_than_twenty_five_percent(self) -> None:
        frame = history(sessions=60, peak_position=44, peak=100.0, trough=70.0, last=99.0)

        claim = base_claim(frame, "primary_base.duration_depth")

        self.assertEqual(claim["state"], "fail")
        self.assertEqual(claim["basis"]["required"], "<= 25")

    def test_three_week_base_accepts_a_correction_inside_twenty_five_percent(self) -> None:
        frame = history(sessions=60, peak_position=44, peak=100.0, trough=80.0, last=99.0)

        self.assertEqual(base_claim(frame, "primary_base.duration_depth")["state"], "pass")

    def test_three_to_five_week_base_accepts_up_to_thirty_five_percent(self) -> None:
        frame = history(sessions=60, peak_position=38, peak=100.0, trough=70.0, last=99.0)

        claim = base_claim(frame, "primary_base.duration_depth")

        self.assertEqual(claim["state"], "pass")
        # The rejecting claim is a gate now, so it states a limit and nothing about range.
        self.assertEqual(claim["basis"]["required"], "<= 35")

    def test_longer_correction_between_thirty_five_and_fifty_percent_is_chart_review_not_failure(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=55.0, last=99.0)

        claim = base_claim(frame, "primary_base.duration_depth")

        self.assertEqual(claim["state"], "unavailable")
        self.assertEqual(claim["basis"]["measured"], 45.0)

    def test_longer_correction_inside_thirty_five_percent_passes_outright(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=70.0, last=99.0)

        self.assertEqual(base_claim(frame, "primary_base.duration_depth")["state"], "pass")

    def test_any_correction_deeper_than_fifty_percent_fails(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=45.0, last=99.0)

        self.assertEqual(base_claim(frame, "primary_base.duration_depth")["state"], "fail")


class LongCorrectionConfirmationTests(unittest.TestCase):
    def test_a_confirmed_year_long_correction_resolves_the_thirty_five_to_fifty_band(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=55.0, last=99.0)

        claim = base_claim(frame, "primary_base.duration_depth", primary_base_long_correction="confirmed")

        self.assertEqual(claim["state"], "pass")

    def test_a_rejected_year_long_correction_fails_the_band(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=55.0, last=99.0)

        claim = base_claim(frame, "primary_base.duration_depth", primary_base_long_correction="not_confirmed")

        self.assertEqual(claim["state"], "fail")

    def test_confirming_a_long_correction_cannot_rescue_a_correction_past_fifty_percent(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=45.0, last=99.0)

        claim = base_claim(frame, "primary_base.duration_depth", primary_base_long_correction="confirmed")

        self.assertEqual(claim["state"], "fail")

    def test_confirming_a_long_correction_cannot_widen_a_three_week_base(self) -> None:
        frame = history(sessions=60, peak_position=44, peak=100.0, trough=70.0, last=99.0)

        claim = base_claim(frame, "primary_base.duration_depth", primary_base_long_correction="confirmed")

        self.assertEqual(claim["state"], "fail")


class PrimaryBaseEmergenceTests(unittest.TestCase):
    def test_an_unbroken_all_time_high_is_a_separate_not_triggered_signal(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=70.0, last=99.0)

        primary_base = build_eligibility_evidence(frame, rs_rating=85)["primary_base"]

        self.assertEqual(primary_base["emergence"]["state"], "not_triggered")
        self.assertNotIn(
            "primary_base.all_time_high_breakout",
            [claim["id"] for claim in primary_base["quantitative_claims"]],
        )

    def test_a_close_above_every_prior_high_triggers_emergence(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=70.0, last=101.0)

        primary_base = build_eligibility_evidence(frame, rs_rating=85)["primary_base"]

        self.assertEqual(primary_base["emergence"]["state"], "pass")

    def test_a_confirmed_consolidation_near_the_all_time_high_also_triggers_emergence(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=70.0, last=99.0)

        primary_base = build_eligibility_evidence(
            frame, rs_rating=85, primary_base_emergence="near_high_consolidation"
        )["primary_base"]

        self.assertEqual(primary_base["emergence"]["state"], "pass")
        self.assertEqual(primary_base["emergence"]["basis"]["required"], "close above all prior completed-session highs, or a chart-confirmed constructive consolidation near them")

    def test_an_unconfirmed_near_high_judgment_leaves_emergence_untriggered(self) -> None:
        frame = history(sessions=60, peak_position=10, peak=100.0, trough=70.0, last=99.0)

        primary_base = build_eligibility_evidence(frame, rs_rating=85, primary_base_emergence="needs_chart")["primary_base"]

        self.assertEqual(primary_base["emergence"]["state"], "not_triggered")


if __name__ == "__main__":
    unittest.main()
