"""Two tops that each reject by their own route still reject.

`failed` names criteria every reading agreed on, so a rejection the tops reached differently has
nothing to put there -- reporting the highest top's list would name limits the others say were
never exceeded. The verdict has to come off "every top read reached one" instead, and for a while
it came off a proxy: the tops were taken to have disagreed whenever the contested set was
non-empty.

That proxy died the moment an unanswered chart stopped counting as disagreement. Two tops, each
rejected by the reader's own `absent` reading of a different criterion, agree about nothing and
contest nothing -- and a finished rejection went back to being an open candidate asking for a
chart it had already been given.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import two_tops_that_both_await_the_chart_series


class ARejectionReachedByDifferentRoutesIsStillARejection(unittest.TestCase):
    def _answer(self, by_condition):
        history = two_tops_that_both_await_the_chart_series(flag_low=90.0)
        evidence = build_power_play_evidence(history)
        keys = {
            question["key"]: by_condition[(question["reading"], question["condition"])]
            for question in evidence["chart_questions"]
            if (question["reading"], question["condition"]) in by_condition
        }
        self.assertEqual(len(keys), len(by_condition))
        return evaluate_power_play(build_power_play_evidence(history, chart_readings=keys))

    def test_the_highest_top_out_on_one_criterion_and_the_next_on_another(self) -> None:
        verdict = self._answer(
            {(0, "flag_tightness_or_vcp"): "absent", (1, "launch_volume_character"): "absent"}
        )

        self.assertEqual(verdict["power_play_state"], "not_qualified")

    def test_nothing_is_named_as_the_limit_that_did_it(self) -> None:
        """Because there is no such limit: the tops rejected for different reasons."""
        verdict = self._answer(
            {(0, "flag_tightness_or_vcp"): "absent", (1, "launch_volume_character"): "absent"}
        )

        self.assertEqual(verdict["failed"], [])
        self.assertTrue(verdict["rejected_under_every_top_read"])

    def test_the_criteria_the_two_tops_left_open_are_not_a_disagreement(self) -> None:
        """Which is why the proxy died: nobody disputed anything and both tops are still out."""
        verdict = self._answer(
            {(0, "flag_tightness_or_vcp"): "absent", (1, "launch_volume_character"): "absent"}
        )

        self.assertEqual(verdict["contested_criteria"], [])
        self.assertEqual(verdict["peak_identity"], "settled")

    def test_a_criterion_every_top_failed_is_named_and_not_called_routeless(self) -> None:
        verdict = self._answer(
            {
                (0, "launch_volume_character"): "absent",
                (1, "launch_volume_character"): "absent",
                (0, "flag_tightness_or_vcp"): "absent",
                (1, "flag_tightness_or_vcp"): "absent",
            }
        )

        self.assertEqual(verdict["power_play_state"], "not_qualified")
        self.assertEqual(
            verdict["failed"],
            [
                "fundamentals.power_play_exception.launch_volume_character",
                "fundamentals.power_play_exception.flag_tightness_or_vcp",
            ],
        )
        self.assertFalse(verdict["rejected_under_every_top_read"])


if __name__ == "__main__":
    unittest.main()
