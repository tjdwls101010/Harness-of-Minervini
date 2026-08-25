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
        self.assertTrue(verdict["rejected_under_every_top_read"])

    def test_one_reading_rejecting_alone_is_still_an_open_question(self):
        verdict = evaluate_power_play(evidence(marginal_new_high_at=-5))

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertFalse(verdict["rejected_under_every_top_read"])


class ADistributionDecidesOnlyWhatItActuallyMoved(unittest.TestCase):
    """A payout is a known amount, so it does not have to invalidate everything the way a split does.

    Blocking on any distribution would leave every dividend payer permanently unreadable, and an
    ordinary quarterly payment is a fraction of a percent against a twenty-five percent limit.
    What matters is whether the answer turns on it: a flag printing thirty-six percent that is
    twenty-four once the payout is added back has been decided by the payout, and an ordinary
    one has not.
    """

    def test_a_payout_that_carries_the_verdict_stops_the_criterion_deciding(self):
        pack = evidence(advance_pct=160.0, flag_depth_pct=24.0, distribution_in_the_flag=3.2)

        verdict = evaluate_power_play(pack)

        self.assertIn("flag_maximum_decline_gate_pct", pack["payout_sensitive_criteria"])
        self.assertNotIn(
            "fundamentals.power_play_exception.flag_maximum_decline_gate_pct", verdict["failed"]
        )

    def test_an_ordinary_payout_leaves_the_criterion_deciding(self):
        pack = evidence(flag_depth_pct=40.0, distribution_in_the_flag=0.05)

        verdict = evaluate_power_play(pack)

        self.assertEqual(pack["payout_sensitive_criteria"], [])
        self.assertIn(
            "fundamentals.power_play_exception.flag_maximum_decline_gate_pct", verdict["failed"]
        )


class EveryTopTheSearchCouldHaveLandedOnIsRead(unittest.TestCase):
    """Two readings are not every reading, and a rejection needs every reading.

    A flag that ticks a hundredth of a percent above its own high twice hands the search three
    candidate tops. Read from the two ticks the advance is too small and too long; read from the
    structure they sit inside, it is a hundred and eight percent in five weeks with a thirty
    session flag and nothing decisive against it. Stopping at two readings rejects a candidate
    the bars never rejected.
    """

    def test_a_structure_hidden_behind_two_ticks_is_not_rejected(self):
        pack = evidence(flag_sessions=30, flag_depth_pct=8.0, marginal_new_high_at=(-8, -4))

        verdict = evaluate_power_play(pack)

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertEqual(verdict["failed"], [])
        self.assertFalse(verdict["rejected_under_every_top_read"])

    def test_the_readings_it_took_are_reported(self):
        pack = evidence(flag_sessions=30, flag_depth_pct=8.0, marginal_new_high_at=(-8, -4))

        self.assertGreaterEqual(pack["readings"], 3)


class NoReadingRejectsOnWhatThePayoutDecided(unittest.TestCase):
    def test_a_payout_decided_criterion_carries_no_reading_s_rejection(self):
        """Read per reading, not once for the top one.

        The tops sit at different sessions, so a longer flag holds payouts a shorter one never
        saw. Neutralised only for the top reading, an earlier candidate could reject on a depth
        its own payout manufactured and cast that vote into "every reading rejects".
        """
        pack = evidence(advance_pct=160.0, flag_sessions=30, flag_depth_pct=24.0, distribution_in_the_flag=3.2)
        sensitive = {
            f"fundamentals.power_play_exception.{condition}"
            for condition in pack["payout_sensitive_criteria"]
        }

        self.assertTrue(sensitive)
        for rejection in pack["reading_rejections"]:
            self.assertEqual(sensitive.intersection(rejection["failed"]), set())


class APayoutWithholdsItsOwnSignalAndNothingElse(unittest.TestCase):
    def _verdict(self):
        # An advance far enough above the limit that no candidate top crosses it, so the only
        # thing in question here is the payout.
        return evaluate_power_play(
            evidence(advance_pct=160.0, flag_depth_pct=24.0, distribution_in_the_flag=3.2)
        )

    def test_the_machine_channel_stops_saying_what_the_reducer_stopped_saying(self):
        verdict = self._verdict()
        depth = next(
            signal for signal in verdict["signals"]
            if signal["id"] == "fundamentals.power_play_exception.flag_maximum_decline_gate_pct"
        )

        self.assertEqual(depth["state"], "unavailable")
        self.assertEqual(depth["withheld"], "distribution_inside_the_measured_span")

    def test_a_payout_is_not_a_question_about_which_top_the_search_landed_on(self):
        verdict = self._verdict()

        self.assertEqual(verdict["peak_identity"], "settled")
        self.assertNotIn("peak_identity", verdict["missing"])


class OnlyThePayoutsThatCameOutOfTheLowCountAgainstIt(unittest.TestCase):
    """A distribution paid after the flag's low did not make that low.

    Summing the whole flag's payouts onto the extreme it already chose loses the order the
    sessions happened in: a twenty-six percent decline that bottomed before the ex-date reads as
    twenty-four, and a known failure is withheld as an open question.
    """

    def test_a_payout_after_the_low_does_not_shallow_it(self):
        pack = evidence(flag_depth_pct=26.0, distribution_after_the_flag_low=0.42)

        # Asserted on the measurement rather than on the verdict: a twenty-six percent flag sits
        # close enough to the limit that the candidate tops contest it on their own, which would
        # hide whether the payout was counted.
        self.assertEqual(pack["measurements"]["distribution_paid_in_the_flag"], 0.0)
        self.assertEqual(pack["payout_sensitive_criteria"], [])

    def test_a_payout_before_the_low_still_counts_against_it(self):
        pack = evidence(flag_depth_pct=26.0, distribution_in_the_flag=0.42)

        self.assertEqual(pack["measurements"]["distribution_paid_in_the_flag"], 0.42)


class AReadingNobodyCouldReadIsNotAReadingThatSurvived(unittest.TestCase):
    """Three states, not two: rejected, surviving, and unreadable.

    A reading whose own span holds a corporate action rejects nothing, because nothing in it was
    measured on one coordinate system. Counted as "surviving" it says the structure came through
    every reading intact, which is the opposite of what happened -- and it sends the reader to the
    chart to settle a top when what needs settling is the split.
    """

    def test_a_split_leaves_no_reading_surviving(self):
        pack = evidence(split_inside_the_flag=True)

        self.assertEqual(pack["surviving_readings"], [])
        self.assertEqual(pack["reading_rejections"], [])
        self.assertEqual(len(pack["unreadable_readings"]), pack["readings"])

    def test_a_flag_still_forming_is_not_named_as_a_reading_s_failure(self):
        """The reducer calls it unfinished; one envelope cannot call it both."""

        pack = evidence(flag_sessions=6)

        for rejection in pack["reading_rejections"]:
            self.assertNotIn(
                "fundamentals.power_play_exception.flag_minimum_sessions", rejection["failed"]
            )


class TheReadingCountsAccountForEveryTopTaken(unittest.TestCase):
    """Three buckets and a count that has to add up, or the provenance is decorative."""

    def test_every_reading_lands_in_exactly_one_bucket(self):
        for kwargs in (
            {},
            {"flag_depth_pct": 40.0},
            {"split_inside_the_flag": True},
            {"flag_sessions": 30, "marginal_new_high_at": (-8, -4)},
            {"dormancy_sessions": 1, "advance_sessions": 10, "advance_pct": 40.0},
        ):
            with self.subTest(**kwargs):
                pack = evidence(**kwargs)

                self.assertEqual(
                    pack["readings"],
                    len(pack["surviving_readings"])
                    + len(pack["unreadable_readings"])
                    + len(pack["reading_rejections"]),
                )

    def test_a_chain_the_bound_cut_does_not_claim_every_top(self):
        """The name has to survive the convention that shortened the chain.

        `readings_cut_at` names a top the bound removed, so a verdict resting on agreement among
        the tops that were read cannot be called agreement among all of them. It is agreement
        among the tops taken, and the field that says so points at the count and the cut.
        """
        pack = evidence(flag_depth_pct=40.0)

        self.assertTrue(pack["readings_cut_at"])
        self.assertIn("rejected_under_every_top_read", pack)
        self.assertNotIn("rejected_under_every_reading", pack)


class APayoutCanChooseTheTopItself(unittest.TestCase):
    """Adding the cash back to two scalars is not enough when the cash picked the peak.

    A distribution takes every print after its ex-date down, so a session before it can outprint
    the top the stock actually made. The flag then hangs from a bar the dividend chose -- and the
    real top, being later than it, is never reached by a chain that only walks backward. Nothing
    downstream can recover from that, so the ordering itself has to be checked.
    """

    def test_a_reordering_payout_leaves_the_top_unsettled(self):
        pack = evidence(flag_sessions=25, flag_depth_pct=8.0, payout_that_reorders_the_tops=True)

        verdict = evaluate_power_play(pack)

        self.assertEqual(pack["peak_identity"], "disputed")
        self.assertEqual(verdict["failed"], [])
        self.assertEqual(verdict["power_play_state"], "incomplete")

    def test_a_payout_too_small_to_reorder_anything_leaves_the_top_settled(self):
        """An advance far enough above its limit that the candidate tops agree on their own."""

        pack = evidence(advance_pct=160.0, flag_depth_pct=40.0, distribution_in_the_flag=0.05)

        self.assertEqual(pack["peak_identity"], "settled")


class ATopTheBoundExcludedStillPreventsARejection(unittest.TestCase):
    """The distance says which tops may contest a criterion. It cannot say which may object.

    Contesting is a claim about one structure -- a top far below the highest is a different one,
    and letting it dispute a limit would leave every criterion open. Objecting is weaker and
    survives the distance: a structure the chain walked past is still a reading of these bars
    under which nothing decisive failed, and rejecting while holding its date in hand is deciding
    against evidence already in the envelope.
    """

    def _pack(self, later_high):
        return build_power_play_evidence(
            power_play_series(dormant_price=10.0, flag_sessions=20, flag_depth_pct=8.0, later_high=later_high)
        )

    def test_a_top_just_inside_the_distance_keeps_the_structure_read(self):
        pack = self._pack(21.0 / 0.9)

        self.assertEqual(evaluate_power_play(pack)["power_play_state"], "incomplete")

    def test_a_top_a_cent_outside_it_does_not_turn_the_verdict(self):
        just_outside = self._pack(21.0 / 0.9 + 0.01)

        verdict = evaluate_power_play(just_outside)

        self.assertTrue(just_outside["readings_cut_at"])
        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertEqual(verdict["failed"], [])


class AnUnreadableTopBlocksTheRejectionItCannotVoteOn(unittest.TestCase):
    def test_a_split_in_one_candidate_s_span_leaves_nothing_deciding(self):
        """A candidate nobody could read has not agreed to a rejection by being silent.

        Its raw criteria still fed the agreement calculation while its verdict was excluded from
        the rejection list, so a value measured across two share counts was counted as consent.
        """
        pack = evidence(flag_sessions=30, marginal_new_high_at=-3, split_at=19)

        verdict = evaluate_power_play(pack)

        self.assertTrue(pack["unreadable_readings"])
        self.assertEqual(verdict["failed"], [])
        self.assertEqual(verdict["power_play_state"], "incomplete")


class RejectingAndQualifyingAskDifferentQuestions(unittest.TestCase):
    """A far top blocks a rejection and does not block a qualification, on purpose.

    Rejecting claims that no reading of these bars is a Power Play, so one reading that stands is
    enough to withdraw it. Qualifying claims that *this* reading is one, and a top the registered
    distance puts outside this structure has no standing to answer that. The quantifiers differ,
    so the evidence that settles them differs.
    """

    def test_a_top_outside_the_distance_does_not_contest_a_criterion(self):
        pack = build_power_play_evidence(
            power_play_series(dormant_price=10.0, flag_sessions=20, flag_depth_pct=8.0, later_high=21.0 / 0.9 + 0.01)
        )

        self.assertTrue(pack["readings_cut_at"])
        self.assertEqual(pack["contested_criteria"], [])

    def test_but_it_does_withdraw_the_rejection(self):
        pack = build_power_play_evidence(
            power_play_series(dormant_price=10.0, flag_sessions=20, flag_depth_pct=8.0, later_high=21.0 / 0.9 + 0.01)
        )

        self.assertFalse(pack["every_top_rejects"])
        self.assertTrue(pack["surviving_readings"])


class TheOrderingCheckGoesThroughTheSameNormaliser(unittest.TestCase):
    """Row order is not evidence, and slice three made one module the owner of saying so.

    The scale check read the caller's frame directly instead of the normalised bars, so a history
    handed over newest-first had its distributions accumulated backwards and the check answered
    the opposite question. Same dates, same prices, opposite verdict.
    """

    def test_the_same_bars_in_reverse_order_read_the_same(self):
        forward = power_play_series(flag_sessions=25, flag_depth_pct=8.0, payout_that_reorders_the_tops=True)
        backward = forward.iloc[::-1]

        self.assertEqual(
            build_power_play_evidence(backward)["peak_identity"],
            build_power_play_evidence(forward)["peak_identity"],
        )


class RunningOutOfHistoryIsNotRunningOutOfTops(unittest.TestCase):
    """A candidate the loaded history cannot reach behind is a gap, not a chain that ended.

    The enumeration stops on any refusal, and one of them means the opposite of the others: there
    *is* a lower top, but nothing before it to measure an advance from. Treated as "no more tops"
    it becomes a silent vote for the rejection the tops above it reached -- which is exactly the
    shape a recently listed stock arrives in.
    """

    def test_a_top_with_no_history_behind_it_withholds_the_rejection(self):
        pack = build_power_play_evidence(
            power_play_series(dormancy_sessions=1, advance_sessions=10, advance_pct=40.0, flag_sessions=20)
        )

        verdict = evaluate_power_play(pack)

        self.assertTrue(pack["readings_ran_out_of_history"])
        self.assertFalse(pack["every_top_rejects"])
        self.assertEqual(verdict["failed"], [])
        self.assertEqual(verdict["power_play_state"], "incomplete")


class TheScaleCheckComparesTheWholeStructure(unittest.TestCase):
    """Comparing peak dates asks whether the payout picked the top. That is not the only thing it picks.

    The anchor is the last session at the window's lowest close, so a distribution can leave the
    peak exactly where it was and still move where the advance starts, how long it took, and
    which forty sessions the volume is measured against.
    """

    def _pack(self):
        from tests.series import anchor_moving_payout_series

        return build_power_play_evidence(anchor_moving_payout_series())

    def test_a_payout_that_moves_only_the_anchor_still_unsettles_the_reading(self):
        pack = self._pack()

        verdict = evaluate_power_play(pack)

        self.assertEqual(pack["peak_identity"], "disputed")
        self.assertEqual(verdict["failed"], [])


class AHistoryWithoutTheDistributionColumnHasNotSaidThereWereNone(unittest.TestCase):
    """The same rule the split column already gets, for the same reason.

    Dropping the column from a frame whose payout had reordered the tops turned an open question
    into a confident rejection. A provider that usually supplies the events is not the same as
    this input having supplied them.
    """

    def test_the_absence_is_reported_as_its_own_gap(self):
        from tests.series import anchor_moving_payout_series

        bars = anchor_moving_payout_series().drop(columns=["Dividends"])

        pack = build_power_play_evidence(bars)
        verdict = evaluate_power_play(pack)

        self.assertEqual(pack["distribution_evidence"], "missing")
        self.assertIn("distribution_evidence", verdict["missing"])
        self.assertEqual(verdict["failed"], [])
