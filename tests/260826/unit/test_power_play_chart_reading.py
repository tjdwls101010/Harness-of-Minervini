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
from tests.readings import power_play_answers
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
        """A chart is drawn over sessions, so the question names them.

        All three boundaries, on both questions. A reader sent to judge whether a flag shows VCP
        character over a span whose end is missing is being asked about a picture nobody named.
        """
        evidence = build_power_play_evidence(power_play_series())
        measurements = evidence["measurements"]

        for condition, question in _questions(evidence).items():
            with self.subTest(condition=condition):
                for boundary in ("peak_date", "advance_anchor_date", "flag_low_date"):
                    self.assertEqual(question[boundary], measurements[boundary])
                self.assertEqual(question["measured_bars"], evidence["measured_bars"])


    def test_each_question_carries_the_measurement_its_own_criterion_turns_on(self) -> None:
        """A chart approved at a nine percent flag is not an approval of the same flag re-measured
        at eleven -- which is only true while each question carries *its* number.

        Written out rather than read from the mapping the implementation uses: taken from there,
        swapping the two criteria's measurements swaps the expectation in the same stroke.
        """
        evidence = build_power_play_evidence(power_play_series())
        measurements = evidence["measurements"]
        questions = _questions(evidence)

        for condition, measured in (
            ("launch_volume_character", "advance_peak_volume_ratio"),
            ("flag_tightness_or_vcp", "flag_depth_pct"),
        ):
            with self.subTest(condition=condition):
                self.assertEqual(questions[condition]["measured"], {measured: measurements[measured]})

class AnAnswerClosesTheCriterionItWasAskedAbout(unittest.TestCase):
    def _both(self, history):
        evidence = build_power_play_evidence(history)
        return power_play_answers(
            history, {question["key"]: "observed" for question in evidence["chart_questions"]}
        )

    def test_observed_makes_the_criterion_pass(self) -> None:
        history = power_play_series()
        keys = self._both(history)
        answered = build_power_play_evidence(history, **keys)

        states = {signal["id"]: signal["state"] for signal in answered["signals"]}
        self.assertEqual(states["fundamentals.power_play_exception.launch_volume_character"], "pass")
        self.assertEqual(states["fundamentals.power_play_exception.flag_tightness_or_vcp"], "pass")

    def test_a_pass_a_person_supplied_never_looks_like_one_the_numbers_reached(self) -> None:
        """The one thing an auditor of a qualified verdict has to be able to see.

        Both criteria, not one. A qualified verdict rests on two answers a person gave, and an
        auditor reading only the volume signal's provenance would take the tightness pass for a
        measurement.
        """
        history = power_play_series()
        answered = build_power_play_evidence(history, **self._both(history))
        signals = {signal["id"]: signal for signal in answered["signals"]}

        for condition in ("launch_volume_character", "flag_tightness_or_vcp"):
            with self.subTest(condition=condition):
                signal = signals[f"fundamentals.power_play_exception.{condition}"]
                self.assertEqual(signal["state"], "pass")
                self.assertTrue(signal["read_from_chart"])

    def test_and_a_pass_the_numbers_reached_is_not_marked_as_a_reading(self) -> None:
        """The control. Marked on everything, the flag would say nothing."""
        signals = {
            signal["id"]: signal
            for signal in build_power_play_evidence(power_play_series())["signals"]
        }
        measured = signals["fundamentals.power_play_exception.advance_minimum_pct"]

        self.assertEqual(measured["state"], "pass")
        self.assertFalse(measured.get("read_from_chart"))

    def test_answering_both_is_what_makes_qualified_reachable(self) -> None:
        history = power_play_series()
        verdict = evaluate_power_play(build_power_play_evidence(history, **self._both(history)))

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
            build_power_play_evidence(history, **power_play_answers(history, {volume["key"]: "absent"}))
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
        history = power_play_series(flag_sessions=18)
        other = build_power_play_evidence(history, **power_play_answers(history, {key: "observed"}))

        self.assertEqual(other["unmatched_chart_readings"], [key])

    def test_every_part_of_the_question_moves_the_key(self) -> None:
        """The four things the prose says the key binds, each shown to actually bind.

        Checked against the function rather than through a fixture per part, because the point is
        that no component is decorative -- a boundary that never reaches the digest would let an
        approval of one reading answer for another.
        """
        from scripts.minervini.power_play_evidence import _chart_key

        # Written out rather than read from the module. Taken from `_BOUNDARIES`, the list is
        # whatever the implementation currently digests, so dropping a boundary drops it from the
        # expectation in the same stroke and the test goes on passing.
        boundaries = (
            "peak_date",
            "advance_anchor_date",
            "flag_low_date",
            "baseline_first_session",
            "baseline_last_session",
            "measured_span_first_session",
        )
        reading = {
            **dict.fromkeys(boundaries, "2026-01-02"),
            "advance_peak_volume_ratio": 1.0,
            "flag_depth_pct": 1.0,
        }
        base = _chart_key("digest", "launch_volume_character", reading, "asked")

        self.assertNotEqual(base, _chart_key("other-digest", "launch_volume_character", reading, "asked"))
        self.assertNotEqual(base, _chart_key("digest", "flag_tightness_or_vcp", reading, "asked"))
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                moved = {**reading, boundary: "2026-01-03"}
                self.assertNotEqual(base, _chart_key("digest", "launch_volume_character", moved, "asked"))
        remeasured = {**reading, "advance_peak_volume_ratio": 1.01}
        self.assertNotEqual(base, _chart_key("digest", "launch_volume_character", remeasured, "asked"))
        self.assertNotEqual(base, _chart_key("digest", "launch_volume_character", reading, "asked differently"))

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
        return build_power_play_evidence(history, **power_play_answers(history, keys)), keys

    def test_a_flag_that_has_not_finished_stays_unfinished(self) -> None:
        """Twelve sessions is the least a flag can be, and no reading of the chart adds one."""
        history = power_play_series(flag_sessions=6)
        answered, _ = self._answer_everything(history)
        verdict = evaluate_power_play(answered)

        self.assertIn("fundamentals.power_play_exception.flag_minimum_sessions", verdict["missing"])
        self.assertEqual(verdict["power_play_state"], "incomplete")

    def test_answering_one_of_two_tops_never_reaches_qualified(self) -> None:
        """What it does instead -- abstain rather than dispute -- is pinned next door, in
        tests/260826/unit/test_power_play_abstention.py. Here only that it cannot close."""
        history = two_tops_that_both_await_the_chart_series()
        answered, _ = self._answer_everything_for_reading(history, 0)

        self.assertNotEqual(evaluate_power_play(answered)["power_play_state"], "qualified")

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
        return build_power_play_evidence(history, **power_play_answers(history, keys)), keys

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


class AnAnswerNeverRescuesARejectedReading(unittest.TestCase):
    """The property that keeps a rejection from being talked out of.

    It holds structurally rather than by a rule: a reading rejects only on a criterion a number
    settled, and no key is issued for a reading in that state -- so there is nothing for an
    `observed` to be spent on. Pinned because the two halves live in different loops, and a later
    edit that issued keys before checking the rejection would open exactly this door.
    """

    def test_no_reading_the_bars_rejected_is_ever_offered_a_key(self) -> None:
        for history in (
            power_play_series(flag_depth_pct=40.0),
            power_play_series(advance_pct=20.0),
            power_play_series(flag_sessions=45),
            two_tops_that_both_await_the_chart_series(),
        ):
            evidence = build_power_play_evidence(history)
            asked = {question["peak_date"] for question in evidence["chart_questions"]}
            rejected = {rejection["peak_date"] for rejection in evidence["reading_rejections"]}
            with self.subTest(readings=evidence["readings"], asked=len(asked)):
                self.assertEqual(asked & rejected, set())
                # And the ones asked are the ones still standing, so a key always belongs to a
                # reading whose answer could still decide something.
                self.assertLessEqual(asked, set(evidence["surviving_readings"]))

    def test_answering_observed_cannot_move_a_reading_out_of_the_rejections(self) -> None:
        history = power_play_series(flag_depth_pct=40.0)
        before = build_power_play_evidence(history)
        keys = {question["key"]: "observed" for question in before["chart_questions"]}
        after = build_power_play_evidence(history, **power_play_answers(history, keys))

        self.assertEqual(before["chart_questions"], [])
        self.assertEqual(
            [rejection["peak_date"] for rejection in after["reading_rejections"]],
            [rejection["peak_date"] for rejection in before["reading_rejections"]],
        )
        self.assertEqual(evaluate_power_play(after)["power_play_state"], "not_qualified")
