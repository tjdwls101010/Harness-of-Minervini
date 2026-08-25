"""The seam a chart reading comes back through, and what it is bound to.

Two of this capability's criteria end in questions completed bars do not answer, so the verdict
stops at `incomplete` and names them. Letting a reader answer them is what makes `qualified`
reachable at all -- and it is also the only channel through which a human sentence can turn into
a machine `pass` here, so what it is bound to is the whole of its safety.

An approval names one question by a key the capability issued, and that key is a digest of the
input, the criterion, the boundaries of the reading it was asked under, and the measurement it
turns on. Anything the caller could answer without having been asked is therefore not answerable:
a chart drawn from other bars, a criterion the numbers already settled, a reading whose top moved.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import power_play_series, two_tops_that_both_await_the_chart_series


def _questions(evidence):
    return {question["condition"]: question for question in evidence["chart_questions"]}


class TheCapabilityAsksBeforeItIsAnswered(unittest.TestCase):
    def test_every_criterion_waiting_on_a_chart_arrives_with_a_key(self) -> None:
        """A caller cannot answer a question they were never asked.

        The two criteria are the ones the source states without a magnitude. Nothing else is
        offered a key, because everything else was settled by a number.
        """
        evidence = build_power_play_evidence(power_play_series())

        self.assertEqual(
            sorted(_questions(evidence)),
            ["flag_tightness_or_vcp", "launch_volume_character"],
        )

    def test_the_question_carries_the_span_it_is_asked_about(self) -> None:
        """A chart is drawn over sessions, so the question names them."""
        evidence = build_power_play_evidence(power_play_series())
        question = _questions(evidence)["launch_volume_character"]

        self.assertEqual(question["peak_date"], evidence["measurements"]["peak_date"])
        self.assertEqual(question["advance_anchor_date"], evidence["measurements"]["advance_anchor_date"])
        self.assertEqual(question["measured_bars"], evidence["measured_bars"])


class AnAnswerClosesTheCriterionItWasAskedAbout(unittest.TestCase):
    def _both(self, history):
        evidence = build_power_play_evidence(history)
        return {question["key"]: "observed" for question in evidence["chart_questions"]}

    def test_observed_makes_the_criterion_pass(self) -> None:
        history = power_play_series()
        keys = self._both(history)
        answered = build_power_play_evidence(history, chart_readings=keys)

        states = {signal["id"]: signal["state"] for signal in answered["signals"]}
        self.assertEqual(states["fundamentals.power_play_exception.launch_volume_character"], "pass")
        self.assertEqual(states["fundamentals.power_play_exception.flag_tightness_or_vcp"], "pass")

    def test_a_pass_a_person_supplied_never_looks_like_one_the_numbers_reached(self) -> None:
        """The one thing an auditor of a qualified verdict has to be able to see."""
        history = power_play_series()
        answered = build_power_play_evidence(history, chart_readings=self._both(history))

        volume = next(
            signal for signal in answered["signals"]
            if signal["id"].endswith("launch_volume_character")
        )
        self.assertTrue(volume["read_from_chart"])

    def test_answering_both_is_what_makes_qualified_reachable(self) -> None:
        history = power_play_series()
        verdict = evaluate_power_play(build_power_play_evidence(history, chart_readings=self._both(history)))

        self.assertEqual(verdict["power_play_state"], "qualified")
        self.assertEqual(verdict["missing"], [])

    def test_absent_is_an_answer_too(self) -> None:
        """A reader who looked and saw ordinary volume settled the criterion against the stock.

        Resolving a question the numbers declined to answer is not overriding a number, so the
        negative reading is admissible on the same terms as the positive one.
        """
        history = power_play_series()
        evidence = build_power_play_evidence(history)
        volume = _questions(evidence)["launch_volume_character"]
        verdict = evaluate_power_play(
            build_power_play_evidence(history, chart_readings={volume["key"]: "absent"})
        )

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertIn("fundamentals.power_play_exception.launch_volume_character", verdict["failed"])


class AnApprovalIsBoundToWhatWasMeasured(unittest.TestCase):
    def test_a_key_from_other_bars_is_refused_rather_than_ignored(self) -> None:
        """Silently dropping it would let a caller believe they had answered something.

        The stale case is the ordinary one: the chart was drawn yesterday, a session closed, and
        the same question now has a different answer. That has to arrive as a refusal.
        """
        evidence = build_power_play_evidence(power_play_series())
        key = evidence["chart_questions"][0]["key"]
        other = build_power_play_evidence(power_play_series(flag_sessions=18), chart_readings={key: "observed"})

        self.assertEqual(other["unmatched_chart_readings"], [key])

    def test_a_payout_inside_the_span_changes_the_key(self) -> None:
        """Same prices on the tape, different prices on one scale.

        The digest has to move for the same reason the verdict does: what the reader looked at
        was not what this run measured.
        """
        plain = build_power_play_evidence(power_play_series())
        paying = build_power_play_evidence(power_play_series(distribution_in_the_flag=0.30))

        self.assertNotEqual(
            {question["key"] for question in plain["chart_questions"]},
            {question["key"] for question in paying["chart_questions"]},
        )


if __name__ == "__main__":
    unittest.main()


class WhatAnApprovalCanNeverClose(unittest.TestCase):
    """The gaps that close on time, on history, or on the dividend calendar.

    Each of them looks like the two the chart answers -- a criterion short of what the source
    asks, reported as missing rather than failed -- and each closes on something a reader looking
    at a chart cannot supply. Nothing here is enforced by a rule saying so; it falls out of a key
    being issued only for a question a chart is what settles.
    """

    def _answer_everything(self, history):
        evidence = build_power_play_evidence(history)
        keys = {question["key"]: "observed" for question in evidence["chart_questions"]}
        return build_power_play_evidence(history, chart_readings=keys), keys

    def test_a_flag_that_has_not_finished_stays_unfinished(self) -> None:
        """Twelve sessions is the least a flag can be, and no reading of the chart adds one."""
        history = power_play_series(flag_sessions=6)
        answered, _ = self._answer_everything(history)
        verdict = evaluate_power_play(answered)

        self.assertIn("fundamentals.power_play_exception.flag_minimum_sessions", verdict["missing"])
        self.assertEqual(verdict["power_play_state"], "incomplete")

    def test_a_disputed_peak_is_not_settled_by_answering_one_of_the_tops(self) -> None:
        """Answering the highest top leaves the lower one still asking.

        Both tops ask the same question about different spans, so a reading of one is not a
        reading of the other -- and a criterion the two tops now answer differently is disputed,
        which is the truth of it: the reader settled one chart and the search has another.
        """
        history = two_tops_that_both_await_the_chart_series()
        answered, _ = self._answer_everything_for_reading(history, 0)
        verdict = evaluate_power_play(answered)

        self.assertEqual(verdict["peak_identity"], "disputed")
        self.assertNotEqual(verdict["power_play_state"], "qualified")
        volume = next(
            signal for signal in verdict["signals"]
            if signal["id"].endswith("launch_volume_character")
        )
        self.assertEqual(volume["withheld"], "peak_identity_disputed")

    def test_answering_every_top_that_may_contest_is_what_settles_it(self) -> None:
        """The honest cost of two candidate structures: a reader looks at both charts."""
        history = two_tops_that_both_await_the_chart_series()
        answered, _ = self._answer_everything(history)
        verdict = evaluate_power_play(answered)

        self.assertEqual(verdict["peak_identity"], "settled")
        self.assertEqual(verdict["power_play_state"], "qualified")

    def _answer_everything_for_reading(self, history, index):
        evidence = build_power_play_evidence(history)
        keys = {
            question["key"]: "observed"
            for question in evidence["chart_questions"]
            if question["reading"] == index
        }
        self.assertTrue(keys)
        return build_power_play_evidence(history, chart_readings=keys), keys

    def test_a_split_in_the_span_leaves_nothing_to_approve(self) -> None:
        """No key is issued, so the approval has nothing to attach to and says so.

        Detecting the action and then letting a reader corroborate what it manufactured is worse
        than not detecting it: the answer comes back as a person's confirmation of price action
        that never happened.
        """
        history = power_play_series(split_inside_the_flag=True)
        evidence = build_power_play_evidence(history)

        self.assertEqual(evidence["chart_questions"], [])

    def test_a_history_that_cannot_say_whether_a_split_happened_asks_nothing(self) -> None:
        history = power_play_series(corporate_actions=False)
        evidence = build_power_play_evidence(history)

        self.assertIsNone(evidence["measured_bars"])
        self.assertEqual(evidence["chart_questions"], [])


class ARejectedStructureAsksNothing(unittest.TestCase):
    """A question whose answer cannot move anything is noise, and worse than noise here.

    Offering a key on a structure the bars already threw out invites a reader to go and read a
    chart, come back with an answer, and find the verdict unchanged -- and the doctrine that a
    visual opinion never overturns a deterministic failure means it was always going to be
    unchanged. So the questions stop where the measurement stopped.
    """

    def test_a_flag_the_depth_gate_threw_out_is_not_offered_a_vcp_reading(self) -> None:
        history = power_play_series(flag_depth_pct=40.0)
        evidence = build_power_play_evidence(history)
        verdict = evaluate_power_play(evidence)

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertEqual(evidence["chart_questions"], [])
