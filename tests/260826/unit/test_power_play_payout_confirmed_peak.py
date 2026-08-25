"""A confirmation the dividend made is not a confirmation the stock made.

The ex-date drop is a retracement nobody traded. Read on the tape it can be the very fall that
confirms the peak as a turning point; read with every print on one scale it confirms nothing. So
the structure comparison across the two scales has to carry whether the peak was confirmed --
without it, a payout that manufactured the confirmation walked past `reordered`, the criteria read
the same on both scales, and the qualification `peak_not_a_confirmed_turning_point` exists to
withhold came back qualified on answers a reader gave in good faith.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import _on_one_scale, build_power_play_evidence
from tests.readings import power_play_answers
from tests.series import a_payout_that_confirms_the_peak_series


class TheConfirmationDisappearsOnOneScale(unittest.TestCase):
    def setUp(self) -> None:
        self.history = a_payout_that_confirms_the_peak_series()

    def test_the_fixture_really_confirms_on_one_scale_and_not_the_other(self) -> None:
        self.assertTrue(
            build_power_play_evidence(self.history)["peak_is_a_confirmed_turning_point"]
        )
        self.assertFalse(
            build_power_play_evidence(_on_one_scale(self.history))["peak_is_a_confirmed_turning_point"]
        )

    def test_nothing_is_asked_of_a_reader_about_a_structure_the_payout_chose(self) -> None:
        self.assertEqual(build_power_play_evidence(self.history)["chart_questions"], [])

    def test_and_answering_anyway_cannot_qualify_it(self) -> None:
        evidence = build_power_play_evidence(self.history)
        keys = {question["key"]: "observed" for question in evidence["chart_questions"]}
        verdict = evaluate_power_play(
            build_power_play_evidence(self.history, **power_play_answers(self.history, keys))
        )

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertEqual(verdict["contested_criteria"], sorted(verdict["contested_criteria"]))
        self.assertTrue(verdict["contested_criteria"])


if __name__ == "__main__":
    unittest.main()
