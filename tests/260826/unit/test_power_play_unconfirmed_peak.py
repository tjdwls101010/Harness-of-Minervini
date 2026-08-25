"""The top the whole structure hangs from, when the segmentation confirms nothing.

Every other candidate is found by descending from the one above it, and the turning-point filter
answers the question that raises: is this descending high a top, or a bar inside the flag? The
span's highest bar is not found that way -- the measurement picks it as the highest session of the
longest structure the criteria describe -- so it is read whatever the segmentation says. Refusing
to read it costs three of the twenty-four rejections this repository can currently reach, with
nothing read in their place.

What was false was calling that top settled. A flag tighter than one day's ordinary range confirms
no turning point at all, and answering its chart qualified a structure hanging from a bar nothing
confirmed. So the reading stands and the qualification does not.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import _turning_points, build_power_play_evidence
from tests.readings import power_play_answers
from tests.series import a_flag_tighter_than_one_days_range_series, power_play_series


def answered(history):
    evidence = build_power_play_evidence(history)
    keys = {question["key"]: "observed" for question in evidence["chart_questions"]}
    return build_power_play_evidence(history, **power_play_answers(history, keys))


class AStructureHangingFromAnUnconfirmedHigh(unittest.TestCase):
    def setUp(self) -> None:
        self.history = a_flag_tighter_than_one_days_range_series()

    def test_the_fixture_really_confirms_no_turning_point(self) -> None:
        self.assertEqual(_turning_points(self.history), frozenset())

    def test_the_highest_bar_is_still_read(self) -> None:
        """The reading stands. Dropped, the bars measure nothing and a failure among them is lost
        rather than reported."""
        self.assertEqual(build_power_play_evidence(self.history)["readings"], 1)

    def test_it_is_reported_as_a_top_the_segmentation_did_not_confirm(self) -> None:
        self.assertFalse(
            build_power_play_evidence(self.history)["peak_is_a_confirmed_turning_point"]
        )

    def test_answering_every_chart_it_asks_does_not_qualify_it(self) -> None:
        verdict = evaluate_power_play(answered(self.history))

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertIn("peak_confirmation", verdict["missing"])

    def test_a_confirmed_peak_is_not_held_by_this(self) -> None:
        """The control, and the reason this is not just a blanket block: the ordinary fixture's
        peak *is* confirmed, and it qualifies on the same answers."""
        history = power_play_series()
        evidence = build_power_play_evidence(history)

        self.assertTrue(evidence["peak_is_a_confirmed_turning_point"])
        verdict = evaluate_power_play(answered(history))
        self.assertEqual(verdict["power_play_state"], "qualified")
        self.assertNotIn("peak_confirmation", verdict["missing"])


if __name__ == "__main__":
    unittest.main()
