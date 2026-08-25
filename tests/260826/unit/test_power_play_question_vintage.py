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
from tests.readings import power_play_answers, reregistered
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


if __name__ == "__main__":
    unittest.main()
