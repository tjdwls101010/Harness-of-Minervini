"""What the Power Play evidence pack says, and what it refuses to conclude.

`qualified` is a positive evidence set, not an absence of objections. Two of the criteria the
source states are questions completed bars cannot answer -- whether volume was *huge* rather
than merely expanded, and whether a flag that is not tight nonetheless shows VCP character --
so a structure that clears every measurable limit is incomplete rather than qualified, and
says which reading it is waiting for.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import power_play_series


def evidence(**kwargs):
    return build_power_play_evidence(power_play_series(**kwargs))


def states(pack) -> dict:
    return {signal["id"]: signal["state"] for signal in pack["signals"]}


class TheMeasurableLimitsDecideWhatTheyCanDecide(unittest.TestCase):
    def test_a_flag_deeper_than_the_source_allows_is_not_a_power_play(self):
        pack = evidence(flag_depth_pct=40.0)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertIn(
            "fundamentals.power_play_exception.flag_maximum_decline_gate_pct",
            verdict["failed"],
        )

    def test_an_advance_under_a_hundred_percent_is_not_a_power_play(self):
        pack = evidence(advance_pct=40.0)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")


class WhatTheBarsCannotSettleStaysUnsettled(unittest.TestCase):
    def test_clearing_every_measurable_limit_is_not_yet_qualification(self):
        pack = evidence()

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertEqual(verdict["failed"], [])
        self.assertIn(
            "fundamentals.power_play_exception.launch_volume_character",
            verdict["missing"],
        )

    def test_an_advance_with_no_expansion_anywhere_fails_without_a_chart(self):
        """No magnitude is needed to observe that nothing expanded at all."""

        pack = evidence(advance_volume_multiple=1.0)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertIn(
            "fundamentals.power_play_exception.launch_volume_character",
            verdict["failed"],
        )

    def test_a_history_that_cannot_say_whether_a_split_happened_says_so(self):
        pack = evidence(corporate_actions=False)

        verdict = evaluate_power_play(pack)

        self.assertIn("corporate_action_evidence", verdict["missing"])
class AFlagStillFormingHasNotFailed(unittest.TestCase):
    """"a period of three to six weeks (some can emerge after only 12 days)."

    Twelve sessions is the least a flag can be and still be one, which makes a shorter flag an
    unfinished flag rather than a failed structure. Time is the only thing it needs, and no
    amount of it has passed yet.

    The distinction is load-bearing here because the peak is found rather than declared: a new
    high a hundredth of a percent above the last one restarts the flag, and the source names no
    size below which a new high stops counting. Calling the four sessions that follow a failure
    removes a twenty-session flag from consideration on the strength of one cent.
    """

    def test_a_flag_shorter_than_the_minimum_is_unfinished_rather_than_failed(self):
        pack = evidence(flag_sessions=6)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertIn("fundamentals.power_play_exception.flag_minimum_sessions", verdict["missing"])

    def test_a_marginal_new_high_does_not_remove_the_flag_it_restarted(self):
        pack = evidence(marginal_new_high_at=-5)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertEqual(verdict["failed"], [])

    def test_the_readings_disagree_about_the_flag_and_not_about_the_advance(self):
        """A forty percent advance is not a Power Play from either top.

        The readings do disagree, so the identity stays disputed and says so. What they disagree
        about is the flag; the advance itself reads the same from both tops, and a criterion the
        bars answered twice the same way is not waiting on which top the search landed on.
        """
        pack = evidence(advance_pct=40.0, marginal_new_high_at=100)

        self.assertEqual(pack["peak_identity"], "disputed")
        self.assertNotIn("advance_minimum_pct", pack["contested_criteria"])
        self.assertIn("advance_maximum_weeks", pack["contested_criteria"])

    def test_the_criterion_both_readings_failed_is_the_one_reported(self):
        pack = evidence(advance_pct=40.0, marginal_new_high_at=100)

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertEqual(verdict["failed"], ["fundamentals.power_play_exception.advance_minimum_pct"])

    def test_a_criterion_only_one_reading_failed_is_not_reported(self):
        """The advance's length differs between the readings; only the advance itself agrees."""
        pack = evidence(advance_pct=40.0, marginal_new_high_at=100)

        verdict = evaluate_power_play(pack)

        self.assertNotIn("fundamentals.power_play_exception.advance_maximum_weeks", verdict["failed"])


class ACorporateActionInvalidatesWhatItMoved(unittest.TestCase):
    """A split moves every printed price and moves nobody's money.

    Detecting one and then letting the depth it manufactured reject the stock is worse than not
    detecting it: the answer comes back as a confident finding about price action that never
    happened. What a split cannot touch is how many sessions elapsed, so those criteria still
    decide -- the distinction is between measurements the action moved and measurements it did not.
    """

    def test_a_split_cannot_produce_a_confident_failure_on_depth(self):
        pack = build_power_play_evidence(power_play_series(split_inside_the_flag=True))

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertNotIn(
            "fundamentals.power_play_exception.flag_maximum_decline_gate_pct",
            verdict["failed"],
        )

    def test_a_split_leaves_the_session_counts_deciding(self):
        """Sixty-five sessions is sixty-five sessions whatever the prices did."""

        pack = build_power_play_evidence(
            power_play_series(flag_sessions=65, split_inside_the_flag=True)
        )

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertIn("fundamentals.power_play_exception.flag_maximum_weeks", verdict["failed"])

    def test_the_measurements_stay_where_a_person_can_read_them(self):
        pack = build_power_play_evidence(power_play_series(split_inside_the_flag=True))

        verdict = evaluate_power_play(pack)

        self.assertIsNotNone(verdict["measurements"]["flag_depth_pct"])


if __name__ == "__main__":
    unittest.main()
