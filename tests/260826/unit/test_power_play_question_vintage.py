"""An answer is to one question, and the question is not a constant.

The key binds an answer to the bars, the criterion, the reading of the tops and the measurement.
What it did not bind is the sentence the reader was answering, or the registry that sentence was
written from -- both of which are editable while the capability is not versioned against them.

So an answer given to "the flag corrects no more than 10 percent" satisfied "no more than 11
percent" without anybody being asked, which is the one thing this seam exists to prevent: it is
the only channel in the harness through which a human sentence becomes a machine pass.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.readings import power_play_answers, reregistered, restated
from tests.series import power_play_series


def _issued(history):
    evidence = build_power_play_evidence(history)
    return {question["key"]: "observed" for question in evidence["chart_questions"]}


class AKeyOutlivesNoRegistryEdit(unittest.TestCase):
    def setUp(self) -> None:
        self.history = power_play_series()
        self.answers = _issued(self.history)
        self.assertTrue(self.answers, "fixture asks no chart question to answer")

    def test_the_same_registry_reissues_the_same_keys(self) -> None:
        """The control. Without this, every assertion below passes on a key that never repeats."""
        self.assertEqual(set(_issued(self.history)), set(self.answers))

    def test_moving_the_limit_the_question_quotes_retires_its_key(self) -> None:
        with reregistered("fundamentals.power_play_exception", "thresholds", "tight_action_maximum_pct", 11.0):
            evidence = build_power_play_evidence(
                self.history, **power_play_answers(self.history, self.answers)
            )

        self.assertEqual(set(evidence["unmatched_chart_readings"]), set(self.answers))
        self.assertEqual([question["answered"] for question in evidence["chart_questions"]], [None, None])

    def test_moving_a_value_the_sentence_never_quotes_retires_it_too(self) -> None:
        """The candidate distance is nowhere in the wording and still decides what the answer is
        about: it sets which tops may contest the criterion the answer settles."""
        with reregistered(
            "convention.power_play_top_candidates", "parameters", "candidate_top_maximum_distance_pct", 1.0
        ):
            evidence = build_power_play_evidence(
                self.history, **power_play_answers(self.history, self.answers)
            )

        self.assertEqual(set(evidence["unmatched_chart_readings"]), set(self.answers))

    def test_moving_the_segmentation_the_tops_were_found_by_retires_it_too(self) -> None:
        with reregistered(
            "setup.swing_segmentation_convention", "parameters", "retracement_range_multiple", 3.0
        ):
            evidence = build_power_play_evidence(
                self.history, **power_play_answers(self.history, self.answers)
            )

        self.assertEqual(set(evidence["unmatched_chart_readings"]), set(self.answers))

    def test_moving_the_week_the_windows_are_counted_in_retires_it_too(self) -> None:
        """Belt and braces, and the belt is the boundaries.

        A different trading week gives different search windows, so the reading's own boundary
        sessions move and the key moves with them whether or not the week is in the digest --
        which is why no test can isolate its membership there. What is worth pinning is the
        behaviour: an answer given under one week's calendar does not satisfy another's.
        """
        with reregistered("convention.trading_week", "parameters", "sessions_per_trading_week", 4):
            evidence = build_power_play_evidence(
                self.history, **power_play_answers(self.history, self.answers)
            )

        self.assertEqual(set(evidence["unmatched_chart_readings"]), set(self.answers))

    def test_moving_what_an_answer_means_retires_it_too(self) -> None:
        """The convention that decides what an answer *is* registers no threshold at all.

        Which words are admissible, what one settles and how far it reaches are stated in that
        claim's rule, not in a number -- so a digest of thresholds and parameters could not see it
        change, and an answer given under "one reader settles it" went on satisfying "two
        independent readers must agree".
        """
        with restated(
            "convention.power_play_chart_reading",
            "rule",
            {
                "summary": "An observed answer needs two independent readers; one leaves it open.",
                "conditions": [],
            },
        ):
            evidence = build_power_play_evidence(
                self.history, **power_play_answers(self.history, self.answers)
            )

        self.assertEqual(set(evidence["unmatched_chart_readings"]), set(self.answers))

    def test_and_so_does_moving_what_its_absence_means(self) -> None:
        with restated(
            "convention.power_play_chart_reading",
            "missing",
            {"effect": "reject", "meaning": "no reading, no exception"},
        ):
            evidence = build_power_play_evidence(
                self.history, **power_play_answers(self.history, self.answers)
            )

        self.assertEqual(set(evidence["unmatched_chart_readings"]), set(self.answers))


class AKeyNamesOneQuestion(unittest.TestCase):
    def test_it_is_long_enough_for_that_to_be_a_fact_rather_than_a_probability(self) -> None:
        """A hundred and twenty-eight bits, written out rather than read from the module.

        Shortened, two different questions collide and an answer to one settles the other -- which
        the request boundary cannot catch, because a colliding key is a key this run really did
        issue. The key is copied and never typed, so the length costs a caller nothing.
        """
        keys = [
            question["key"]
            for question in build_power_play_evidence(power_play_series())["chart_questions"]
        ]

        self.assertTrue(keys)
        for key in keys:
            with self.subTest(key=key):
                self.assertEqual(len(key), 32)
                self.assertEqual(set(key) - set("0123456789abcdef"), set())


if __name__ == "__main__":
    unittest.main()
