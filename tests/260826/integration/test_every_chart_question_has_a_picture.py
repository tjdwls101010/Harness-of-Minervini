"""Whenever the capability asks, the chart has to answer-able.

The two sides of this were built separately and nothing made them agree. `ticker power-play`
decides on its own evidence when the volume clause needs a person, and `ticker chart` decides
on its own whether there is an advance worth drawing. If those two ever disagreed in the
direction that matters -- a question issued at a reader while the picture stays blank -- the
reader would be back where the whole overlay started, asked about a session no chart names.

So the relation is asserted rather than argued: over the fixture family the capability's own
tests are built from, every history that issues an open chart question draws its span -- and
only those. Both directions are pinned, because the failure runs both ways. A picture that
stays blank under a question leaves the reader answering about a session nothing names; a span
drawn where nothing was asked is a structure the reader can approve that the capability never
put to them, which is how a chart came to show the highest top while the question was about a
lower one.

A rejected reading is therefore not drawn, and that is the decision rather than an oversight.
The bars threw it out, so no key exists that a reader could close with it, and an advance of
forty percent off a dormancy is rejected here while being an ordinary base to look at -- an
overlay on it is the chart having an opinion, which is the thing this seam gave up. What the
reader gets instead is the span itself: `reading_rejections` carries every landmark of the
structure that was read and the criteria it failed, so a rejection can be inspected without a
picture that would double as an invitation to approve it.
"""

from __future__ import annotations

import unittest

from scripts.minervini.chart import _SPAN_LANDMARKS, _power_play_spans
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


class ARejectionIsInspectableWithoutAPicture(unittest.TestCase):
    """The route that replaces the overlay a rejected reading used to get.

    Nothing is drawn for it, so the whole of what was read has to be in the envelope -- otherwise
    "the bars threw it out" arrives as a verdict with no structure behind it, and a reader who
    wants to know which top and how far its flag fell has nowhere to look. The landmark list
    comes from the chart's own so the two cannot drift into the picture showing something the
    rejection never names.
    """

    def setUp(self) -> None:
        self.history = power_play_series(advance_pct=40.0)

    def test_the_fixture_is_read_and_thrown_out_rather_than_never_read(self) -> None:
        evidence = build_power_play_evidence(self.history)

        self.assertEqual(len(evidence["reading_rejections"]), 1)
        self.assertEqual(
            evidence["reading_rejections"][0]["failed"],
            ["fundamentals.power_play_exception.advance_minimum_pct"],
        )

    def test_it_names_every_landmark_the_chart_would_have_drawn(self) -> None:
        rejection = build_power_play_evidence(self.history)["reading_rejections"][0]

        for landmark in _SPAN_LANDMARKS:
            with self.subTest(landmark=landmark):
                self.assertIn(landmark, rejection)

    def test_and_the_chart_still_draws_nothing_for_it(self) -> None:
        """An overlay a reader can see is one they can approve from, and no key exists here."""
        drawn = _power_play_spans(self.history, "digest-is-not-what-this-checks")

        self.assertEqual(drawn["spans"], [])
        self.assertEqual(drawn["asked_about"], [])


if __name__ == "__main__":
    unittest.main()
