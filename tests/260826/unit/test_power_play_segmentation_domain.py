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

    def test_so_is_the_ambiguous_bar_itself(self) -> None:
        """The other resolution, which the first fix left out.

        Reversal-first ends the swing at the highest bar before the ambiguous session;
        extension-first makes the ambiguous bar the top. The segmenter picked one, so both are
        candidates -- reproduced on a down leg, the missing one reached `qualified` over a reading
        that fails advance, duration and depth together.
        """
        self.assertIn("2026-04-20", _turning_points(a_top_hidden_by_an_ambiguous_session_series()))

    def test_that_top_is_read_and_its_flag_runs_past_the_six_week_limit(self) -> None:
        evidence = build_power_play_evidence(a_top_hidden_by_an_ambiguous_session_series())

        # Three: the anchored top, the ambiguous bar itself, and the top before it. Both orders
        # are candidates because either can be the one the segmenter declined.
        self.assertEqual(evidence["readings"], 3)
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
