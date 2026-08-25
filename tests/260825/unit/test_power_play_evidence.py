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

    def test_a_split_leaves_no_session_count_deciding_either(self):
        """The peak is chosen by comparing prices, so an action chooses it too.

        Sixty-five sessions would be sixty-five sessions if the counting started somewhere the
        action could not move. It does not: the peak is whichever bar printed the highest high,
        and across a split that comparison is between two share counts. A forward split in the
        flag halves everything after the peak and leaves it standing; the same event in the other
        direction doubles it, the flag's own bars outprint the real top, and sixty-five sessions
        measure as zero. Which way a split happens to run is not a reason to trust a count.
        """
        pack = build_power_play_evidence(
            power_play_series(flag_sessions=65, split_inside_the_flag=True)
        )

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertEqual(verdict["failed"], [])

    def test_a_split_inside_the_advance_cannot_manufacture_a_long_flag(self):
        """Halving every print after it makes the last pre-split bar the highest high.

        The flag then runs from a top the stock never made, and the twenty sessions that
        followed the real one measure as thirty-five -- a confident failure on a limit the
        structure never approached.
        """
        pack = build_power_play_evidence(power_play_series(split_at=70))

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["failed"], [])
        self.assertIn("fundamentals.power_play_exception.flag_maximum_weeks", verdict["missing"])

    def test_the_measurements_stay_where_a_person_can_read_them(self):
        pack = build_power_play_evidence(power_play_series(split_inside_the_flag=True))

        verdict = evaluate_power_play(pack)

        self.assertIsNotNone(verdict["measurements"]["flag_depth_pct"])


if __name__ == "__main__":
    unittest.main()


class TheMachineChannelSaysWhatTheReducerSays(unittest.TestCase):
    """`signals` is read by machines, so a state the reducer refuses to use cannot sit in it.

    The reducer already declines a criterion it cannot trust -- but the signal it declined went
    out unchanged, carrying `fail` on a depth the split manufactured and `beyond_source_range` on
    the band beside it. A caller reading the machine channel got a confident rejection the
    verdict channel had already withdrawn.
    """

    def _states(self, pack):
        verdict = evaluate_power_play(pack)
        return {signal["id"]: signal["state"] for signal in verdict["signals"]}

    def test_a_split_withholds_every_state_it_moved(self):
        states = self._states(build_power_play_evidence(power_play_series(split_inside_the_flag=True)))

        self.assertEqual(set(states.values()), {"unavailable"})

    def test_a_withheld_signal_keeps_its_measurement_and_names_the_cause(self):
        verdict = evaluate_power_play(
            build_power_play_evidence(power_play_series(split_inside_the_flag=True))
        )
        depth = next(
            signal for signal in verdict["signals"]
            if signal["id"] == "fundamentals.power_play_exception.flag_maximum_decline_gate_pct"
        )

        self.assertEqual(depth["withheld"], "corporate_action_inside_the_measured_span")
        self.assertIsNotNone(depth["measured"])

    def test_a_contested_criterion_withholds_only_what_the_choice_moved(self):
        pack = evidence(advance_pct=40.0, marginal_new_high_at=100)
        states = self._states(pack)

        self.assertEqual(
            states["fundamentals.power_play_exception.advance_maximum_weeks"], "unavailable"
        )
        self.assertEqual(
            states["fundamentals.power_play_exception.advance_minimum_pct"], "fail"
        )


class BothReadingsRejectingIsAnAnswer(unittest.TestCase):
    """Agreeing that it is not a Power Play is agreement, even about different limits.

    Read from the marginal new high the advance is too small and took too long; read from the
    top it exceeded, the flag has run past six weeks. No single criterion is agreed, so nothing
    is trusted enough to name -- but there is no reading of these bars under which this is a
    Power Play, and reporting that as an open question waits for evidence that would not change
    it.
    """

    def _pack(self):
        return evidence(advance_pct=110.0, flag_sessions=36, marginal_new_high_at=-3)

    def test_a_verdict_no_reading_disputes_is_reported(self):
        verdict = evaluate_power_play(self._pack())

        self.assertEqual(verdict["power_play_state"], "not_qualified")

    def test_no_criterion_only_one_reading_failed_is_named(self):
        """The rejection stands; which limit carried it does not."""

        verdict = evaluate_power_play(self._pack())

        self.assertEqual(verdict["failed"], [])
        self.assertTrue(verdict["rejected_under_every_reading"])

    def test_one_reading_rejecting_alone_is_still_an_open_question(self):
        verdict = evaluate_power_play(evidence(marginal_new_high_at=-5))

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertFalse(verdict["rejected_under_every_reading"])


class ADistributionDecidesOnlyWhatItActuallyMoved(unittest.TestCase):
    """A payout is a known amount, so it does not have to invalidate everything the way a split does.

    Blocking on any distribution would leave every dividend payer permanently unreadable, and an
    ordinary quarterly payment is a fraction of a percent against a twenty-five percent limit.
    What matters is whether the answer turns on it: a thirty percent flag that is twenty-three
    without the payout has been decided by the payout, and a twelve percent flag has not.
    """

    def test_a_payout_that_carries_the_verdict_stops_the_criterion_deciding(self):
        pack = evidence(flag_depth_pct=30.0, distribution_in_the_flag=1.5)

        verdict = evaluate_power_play(pack)

        self.assertIn("flag_maximum_decline_gate_pct", pack["payout_sensitive_criteria"])
        self.assertNotIn(
            "fundamentals.power_play_exception.flag_maximum_decline_gate_pct", verdict["failed"]
        )

    def test_an_ordinary_payout_leaves_the_criterion_deciding(self):
        pack = evidence(flag_depth_pct=30.0, distribution_in_the_flag=0.05)

        verdict = evaluate_power_play(pack)

        self.assertEqual(pack["payout_sensitive_criteria"], [])
        self.assertIn(
            "fundamentals.power_play_exception.flag_maximum_decline_gate_pct", verdict["failed"]
        )
