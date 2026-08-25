"""A top some neighbouring reading of the same chart would confirm still gets a vote.

The candidate tops are confirmed turning points, and confirmation runs at one retracement -- two
and a half times the stock's typical daily range. That figure is this harness's own convention,
and the segmentation path beside this one already refuses to vouch for a chain when a neighbouring
value would have produced a different one, because reporting the instability and passing one
reading anyway is issuing a verdict over a gap the engine already knows about.

Here the same instability cuts one way only. A top the middle reading misses is a top that never
contests a criterion, and while `qualified` was unreachable that cost nothing. It is reachable
now, so a candidate visible at a neighbouring retracement and invisible at the middle one is a
known failure the verdict never hears -- which is how a structure with a rejecting top under it
comes back qualified.

Refusing outright is the wrong shape here: a Power Play is read from whatever top the search
lands on, and a stock whose segmentation is unstable still has tops. Taking every high any
neighbouring reading confirms is the conservative direction on the side that matters -- more tops
may contest a qualification, and a rejection needs all of them to agree.
"""

from __future__ import annotations

import unittest
from contextlib import contextmanager

from scripts.minervini import doctrine
from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import _turning_points, build_power_play_evidence
from scripts.minervini.swings import _typical_range_pct, segment
from scripts.minervini.setup_structure import read_bars
from tests.readings import power_play_answers
from tests.series import a_top_only_a_neighbour_confirms_series


def _registered_offsets():
    return doctrine.parameter("setup.swing_segmentation_convention", "sensitivity_offsets")


@contextmanager
def _offsets(values):
    """Re-register the convention's offsets for the duration of one reading.

    The registry is what the walk is meant to be reading, so the test moves the registry rather
    than the function that reads it -- a patched-out lookup would pass against a hardcoded list
    just as happily.
    """
    record = next(
        claim
        for claim in doctrine._load_registry()["claims"]
        if claim["id"] == "setup.swing_segmentation_convention"
    )
    slot = record["parameters"]["sensitivity_offsets"]
    before = slot["value"]
    slot["value"] = list(values)
    try:
        yield
    finally:
        slot["value"] = before

class EveryNeighbouringReadingsTopsAreCandidates(unittest.TestCase):
    def _highs(self, frame, offset):
        bars, _ = read_bars(frame)
        multiple = float(doctrine.parameter("setup.swing_segmentation_convention", "retracement_range_multiple"))
        anchors = segment(bars, retracement_pct=(multiple + offset) * _typical_range_pct(bars))["anchors"]
        return {str(anchor["date"]) for anchor in anchors if anchor["kind"] == "high"}

    def test_the_offsets_come_from_the_registry_rather_than_this_module(self) -> None:
        offsets = doctrine.parameter("setup.swing_segmentation_convention", "sensitivity_offsets")

        self.assertEqual([float(value) for value in offsets], [-0.1, 0.1])

    def test_moving_the_registered_offsets_moves_the_candidates(self) -> None:
        """The reading above only says what the registry holds -- the same pass a literal
        ``[-0.1, 0.1]`` in the walk would get. What couples the two is the candidates changing
        when the registered value does, so a re-registration reaches the measurement instead of
        leaving a stale copy of an old convention deciding verdicts.
        """
        frame = a_top_only_a_neighbour_confirms_series()
        registered = _registered_offsets()

        with _offsets([0.0]):
            narrowed = _turning_points(frame)
        with _offsets([float(value) for value in registered]):
            restored = _turning_points(frame)

        self.assertEqual(restored, _turning_points(frame))
        self.assertLess(narrowed, restored)
        self.assertEqual(narrowed, self._highs(frame, 0.0))

    def test_a_top_only_a_neighbour_confirms_is_still_a_candidate(self) -> None:
        frame = a_top_only_a_neighbour_confirms_series()
        offsets = [float(value) for value in doctrine.parameter("setup.swing_segmentation_convention", "sensitivity_offsets")]
        middle = self._highs(frame, 0.0)
        neighbours = set().union(*(self._highs(frame, offset) for offset in offsets))
        self.assertTrue(neighbours - middle, "fixture no longer has a neighbour-only top to test with")

        self.assertLessEqual(neighbours | middle, _turning_points(frame))

    def test_the_middle_readings_tops_are_never_dropped(self) -> None:
        frame = a_top_only_a_neighbour_confirms_series()

        self.assertLessEqual(self._highs(frame, 0.0), _turning_points(frame))

    def test_its_known_failure_is_what_the_verdict_would_otherwise_never_hear(self) -> None:
        """The reason the union is worth its extra readings.

        Read from that top the flag runs past six weeks; read from the peak above it nothing
        measurable fails, both charts can be answered, and the structure comes back qualified on
        a chain that walked past a reading of the same bars saying it is not one.
        """
        frame = a_top_only_a_neighbour_confirms_series()
        evidence = build_power_play_evidence(frame)
        answered = build_power_play_evidence(
            frame,
            **power_play_answers(
                frame, {question["key"]: "observed" for question in evidence["chart_questions"]}
            ),
        )
        verdict = evaluate_power_play(answered)

        self.assertEqual(evidence["readings"], 2)
        self.assertEqual(
            [rejection["peak_date"] for rejection in verdict["reading_rejections"]],
            [sorted(_turning_points(frame))[0]],
        )
        self.assertNotEqual(verdict["power_play_state"], "qualified")
        self.assertIn("fundamentals.power_play_exception.flag_maximum_weeks", verdict["missing"])


if __name__ == "__main__":
    unittest.main()
