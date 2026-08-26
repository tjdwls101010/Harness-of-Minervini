"""Whenever the capability asks, the chart has to answer-able.

The two sides of this were built separately and nothing made them agree. `ticker power-play`
decides on its own evidence when the volume clause needs a person, and `ticker chart` decides
on its own whether there is an advance worth drawing. If those two ever disagreed in the
direction that matters -- a question issued at a reader while the picture stays blank -- the
reader would be back where the whole overlay started, asked about a session no chart names.

So the relation is asserted rather than argued: over the fixture family the capability's own
tests are built from, every history that issues an open chart question draws its span. The
other direction is allowed and is not a defect. An advance can clear the two gates and then
fail on its flag, and a structure the bars threw out asks nobody anything -- the chart having
drawn it is what lets a reader see the thing that was rejected.
"""

from __future__ import annotations

import unittest

from scripts.minervini.chart import _power_play_spans
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import power_play_series

# Chosen to land inside the region where the capability actually asks, not to cover the space.
# Extremes on every axis at once mostly produce structures the bars reject outright, which say
# nothing about a relation between asking and drawing: sixteen such histories asked twice. So
# both advances clear the size gate, the durations straddle the eight-week one, and the flag's
# length and depth cross their own limits. Thirty-six histories, sixteen of which ask.
GRID = tuple(
    (advance_pct, advance_sessions, flag_sessions, flag_depth_pct)
    for advance_pct in (105.0, 160.0)
    for advance_sessions in (10, 25, 45)
    for flag_sessions in (12, 26, 34)
    for flag_depth_pct in (8.0, 22.0)
)


class NoQuestionIsAskedAboutAPictureThatShowsNothing(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.asked = 0
        cls.blank = []
        for case in GRID:
            advance_pct, advance_sessions, flag_sessions, flag_depth_pct = case
            history = power_play_series(
                advance_pct=advance_pct,
                advance_sessions=advance_sessions,
                flag_sessions=flag_sessions,
                flag_depth_pct=flag_depth_pct,
            )
            evidence = build_power_play_evidence(history)
            asked_about = {
                question["peak_date"] for question in (evidence.get("chart_questions") or [])
                if not question.get("answered")
            }
            if not asked_about:
                continue
            cls.asked += 1
            drawn = set(_power_play_spans(history, "digest-is-not-what-this-checks")["asked_about"])
            if drawn != asked_about:
                cls.blank.append((case, sorted(asked_about), sorted(drawn)))

    def test_the_sweep_actually_reaches_the_capability_asking(self) -> None:
        """A sweep where nothing is ever asked would pass the test below by saying nothing, and
        a grid of extremes is exactly how that happens -- structures the bars reject outright
        ask nobody anything."""
        self.assertGreaterEqual(self.asked, len(GRID) // 4)

    def test_and_every_one_draws_exactly_the_tops_it_is_asked_about(self) -> None:
        """Not "drew something" -- the same tops. Drawing the highest top while the question is
        about a lower one leaves the reader answering about a structure they cannot see, and
        the digest on the picture is the same either way, so nothing catches it."""
        self.assertEqual(self.blank, [])


if __name__ == "__main__":
    unittest.main()
