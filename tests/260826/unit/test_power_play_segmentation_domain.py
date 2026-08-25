"""Two ways the candidate walk can lose a top it should have read.

Both were found by review rather than by a sweep, and both end the same way: a structure comes
back `qualified` while a top whose own reading fails a hard limit was never read. One is a bar
that reads two ways and a segmenter that had to pick one; the other is a scale the segmenter has
no domain for at all.
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import _SEGMENTATION, _turning_points, build_power_play_evidence
from scripts.minervini.setup_structure import read_bars
from scripts.minervini.swings import _typical_range_pct, segment
from tests.readings import power_play_answers
from tests.series import (
    a_range_too_wide_to_segment_series,
    a_top_hidden_by_an_ambiguous_session_series,
    two_orders_that_confirm_different_tops_series,
)


def _retracements(history):
    bars, _ = read_bars(history)
    typical = _typical_range_pct(bars)
    multiple = float(doctrine.parameter(_SEGMENTATION, "retracement_range_multiple"))
    offsets = [0.0, *(float(value) for value in doctrine.parameter(_SEGMENTATION, "sensitivity_offsets"))]
    return bars, [(multiple + offset) * typical for offset in offsets]


def answered(history):
    evidence = build_power_play_evidence(history)
    keys = {question["key"]: "observed" for question in evidence["chart_questions"]}
    return build_power_play_evidence(history, **power_play_answers(history, keys))


class OneBarThatReadsTwoWays(unittest.TestCase):
    """A session that both extends the advance and ends it. The segmenter records the ambiguity
    and resolves it; reading only what it resolved to spends a known uncertainty as a pass."""

    def test_every_registered_retracement_calls_the_same_session_ambiguous(self) -> None:
        bars, retracements = _retracements(a_top_hidden_by_an_ambiguous_session_series())

        for retracement in retracements:
            run = segment(bars, retracement_pct=retracement)
            self.assertEqual(list(run["ambiguous_sessions"]), ["2026-04-20"])
            self.assertNotIn(
                "2026-04-17", [anchor["date"] for anchor in run["anchors"] if anchor["kind"] == "high"]
            )

    def test_the_top_the_other_order_would_confirm_is_a_candidate(self) -> None:
        self.assertIn("2026-04-17", _turning_points(a_top_hidden_by_an_ambiguous_session_series()))

    def test_the_segmenter_is_asked_rather_than_approximated(self) -> None:
        """Which top the other order confirms is the segmenter's answer, not a guess from anchors.

        Approximating it -- take the ambiguous bar, and the highest bar before it -- gets both
        halves wrong. The ambiguous bar here is confirmed under neither reading, so adding it
        claimed a turning point that does not exist and reported the peak as confirmed on the
        strength of it. And the other order goes on running after the ambiguous bar: it can
        confirm turns further along that no rule about the two neighbouring bars reaches.
        """
        candidates = _turning_points(a_top_hidden_by_an_ambiguous_session_series())

        self.assertEqual(candidates, frozenset({"2026-04-17", "2026-04-24"}))
        self.assertNotIn("2026-04-20", candidates)

    def test_that_top_is_read_and_its_flag_runs_past_the_six_week_limit(self) -> None:
        evidence = build_power_play_evidence(a_top_hidden_by_an_ambiguous_session_series())

        self.assertEqual(evidence["readings"], 2)
        self.assertEqual(
            evidence["reading_rejections"],
            [
                {
                    "peak_date": "2026-04-17",
                    "failed": ["fundamentals.power_play_exception.flag_maximum_weeks"],
                }
            ],
        )

    def test_answering_every_chart_it_asks_still_cannot_reach_qualified(self) -> None:
        verdict = evaluate_power_play(answered(a_top_hidden_by_an_ambiguous_session_series()))

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertIn("peak_identity", verdict["missing"])


class TheOtherOrderIsRunRatherThanGuessed(unittest.TestCase):
    """The segmenter takes a reading of the ambiguous bar and keeps running under it.

    So the turns the other reading would have confirmed are not the two bars either side of the
    ambiguity -- they are a whole chain, and it diverges further the longer it runs. Asking the
    segmenter for that chain is the only way to get it; the alternative was a rule about
    neighbours that both invented a turning point nothing confirms and missed the ones further
    along.
    """

    def setUp(self) -> None:
        self.frame = two_orders_that_confirm_different_tops_series()

    def _highs(self, order):
        run = segment(self.frame, retracement_pct=0.5, ambiguous_order=order)
        self.assertEqual(run["ambiguous_sessions"], ["2026-05-21"])
        return {anchor["date"] for anchor in run["anchors"] if anchor["kind"] == "high"}

    def test_each_reading_confirms_a_high_the_other_does_not(self) -> None:
        extension, reversal = self._highs("extension"), self._highs("reversal")

        self.assertTrue(extension - reversal)
        self.assertTrue(reversal - extension)

    def test_an_order_that_is_neither_reading_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            segment(self.frame, retracement_pct=0.5, ambiguous_order="whichever")

    def test_the_default_is_the_reading_that_confirms_nothing_new(self) -> None:
        """Every other caller keeps one chain, and it has to be the one they already had."""
        self.assertEqual(
            segment(self.frame, retracement_pct=0.5)["anchors"],
            segment(self.frame, retracement_pct=0.5, ambiguous_order="extension")["anchors"],
        )


class AScaleTheSegmenterHasNoDomainFor(unittest.TestCase):
    """Valid OHLCV whose ordinary session spans a large fraction of its own close. The middle
    reading still runs; the upper neighbour the same convention registers does not."""

    def test_the_upper_neighbour_really_does_leave_the_domain(self) -> None:
        bars, retracements = _retracements(a_range_too_wide_to_segment_series())

        self.assertLess(retracements[0], 100)
        self.assertGreater(max(retracements), 100)
        with self.assertRaises(ValueError):
            segment(bars, retracement_pct=max(retracements))

    def test_the_walk_finds_no_turning_points_instead_of_raising(self) -> None:
        self.assertIsNone(_turning_points(a_range_too_wide_to_segment_series()))

    def test_the_structure_is_still_read_from_every_descending_high(self) -> None:
        verdict = evaluate_power_play(build_power_play_evidence(a_range_too_wide_to_segment_series()))

        self.assertEqual(verdict["power_play_state"], "not_qualified")


if __name__ == "__main__":
    unittest.main()
