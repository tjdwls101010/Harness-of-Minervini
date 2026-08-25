"""A bar the chain walked past is not a reading, so it cannot narrow what gets read.

The descent looks for the highest session below the last one and before it. Walking past a bar
that is not a confirmed turning point has to move the price ceiling -- the tops beneath it are
found by descending -- but moving the *date* as well makes a non-reading decide which readings
exist: a confirmed top that is lower in price and later in time than the bar walked past is behind
it forever.

Two reviewers reproduced the same thing from different frames, and both ended at `ok qualified`
over a top whose own flag runs past the six-week limit.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import _turning_points, build_power_play_evidence
from tests.readings import power_play_answers
from tests.series import a_top_behind_a_taller_bar_series


class TheTopBehindTheTallerBar(unittest.TestCase):
    def setUp(self) -> None:
        self.history = a_top_behind_a_taller_bar_series()
        self.evidence = build_power_play_evidence(self.history)

    def test_the_union_confirms_it(self) -> None:
        self.assertIn("2026-04-17", _turning_points(self.history))

    def test_the_bar_in_front_of_it_is_confirmed_by_nothing(self) -> None:
        """Which is why it is walked past, and why walking past it must not cost a reading."""
        candidates = _turning_points(self.history)

        self.assertNotIn("2026-02-23", candidates)
        self.assertLess("2026-02-23", "2026-04-17")

    def test_the_walk_reaches_it(self) -> None:
        self.assertEqual(self.evidence["readings"], 2)
        self.assertEqual(
            [rejection["peak_date"] for rejection in self.evidence["reading_rejections"]],
            ["2026-04-17"],
        )

    def test_so_answering_every_chart_cannot_qualify_over_it(self) -> None:
        keys = {question["key"]: "observed" for question in self.evidence["chart_questions"]}
        verdict = evaluate_power_play(
            build_power_play_evidence(self.history, **power_play_answers(self.history, keys))
        )

        self.assertEqual(verdict["power_play_state"], "incomplete")


if __name__ == "__main__":
    unittest.main()
