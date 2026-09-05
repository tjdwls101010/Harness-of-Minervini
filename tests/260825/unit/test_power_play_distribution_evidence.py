"""Behavior checks for power play distribution evidence."""

from __future__ import annotations

import unittest
from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import payout_that_only_moves_a_gate_series, power_play_series
from ._power_play_evidence_fixtures import evidence


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


class ADistributionDecidesOnlyWhatItActuallyMoved(unittest.TestCase):
    """A payout is a known amount, so it does not have to invalidate everything the way a split does.

    Blocking on any distribution would leave every dividend payer permanently unreadable, and an
    ordinary quarterly payment is a fraction of a percent against a twenty-five percent limit.
    What matters is whether the answer turns on it. The room for that is narrow and real: a payout
    big enough to move the depth gate also reshuffles the tops, and then nothing decides anyway --
    but three tenths of a percent paid mid-advance still decides which side of the hundred percent
    line the advance sits on, because the cash came out of the prints between the anchor and the
    peak and the ratio is read across them.

    The pair below differs in one number: the size of the payout, on one structure, at one
    session.
    """

    def test_a_payout_that_carries_the_verdict_stops_the_criterion_deciding(self):
        pack = build_power_play_evidence(payout_that_only_moves_a_gate_series())

        self.assertEqual(pack["peak_identity"], "settled")
        self.assertEqual(pack["payout_sensitive_criteria"], ["advance_minimum_pct"])

    def test_an_ordinary_payout_leaves_the_criterion_deciding(self):
        pack = build_power_play_evidence(payout_that_only_moves_a_gate_series(payout=0.02))

        self.assertEqual(pack["peak_identity"], "settled")
        self.assertEqual(pack["payout_sensitive_criteria"], [])


class NoVerdictRestsOnWhatThePayoutDecided(unittest.TestCase):
    def test_lower_tops_rejecting_on_it_does_not_make_it_a_failure(self):
        """Read per reading, not once for the top one, and not pooled across the chain either.

        The tops sit at different sessions, so a longer flag holds payouts a shorter one never
        saw. Every one of the flag's own bars rejects this structure's advance on its own terms,
        and none of those is the reading whose answer the payout decided -- so the chain is loud
        with rejections while the criterion the verdict would rest on has no answer at all.
        """
        from tests.series import a_payout_decided_criterion_under_a_lower_top_series

        pack = build_power_play_evidence(a_payout_decided_criterion_under_a_lower_top_series())
        criterion = "fundamentals.power_play_exception.advance_minimum_pct"

        verdict = evaluate_power_play(pack)

        self.assertTrue(any(criterion in item["failed"] for item in pack["reading_rejections"]))
        self.assertNotIn(criterion, verdict["failed"])
        self.assertIn(criterion, verdict["missing"])


class APayoutWithholdsItsOwnSignalAndNothingElse(unittest.TestCase):
    def _verdict(self):
        # A structure no candidate top disputes, so the only thing in question here is the payout.
        return evaluate_power_play(build_power_play_evidence(payout_that_only_moves_a_gate_series()))

    def test_the_machine_channel_stops_saying_what_the_reducer_stopped_saying(self):
        verdict = self._verdict()
        advance = next(
            signal for signal in verdict["signals"]
            if signal["id"] == "fundamentals.power_play_exception.advance_minimum_pct"
        )

        self.assertEqual(advance["state"], "unavailable")
        self.assertEqual(advance["withheld"], "distribution_inside_the_measured_span")

    def test_it_withholds_only_the_criterion_the_payout_decided(self):
        verdict = self._verdict()
        withheld = {
            signal["id"] for signal in verdict["signals"]
            if signal.get("withheld") == "distribution_inside_the_measured_span"
        }

        self.assertEqual(withheld, {"fundamentals.power_play_exception.advance_minimum_pct"})

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
