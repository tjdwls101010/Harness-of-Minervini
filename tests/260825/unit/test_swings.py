"""A deterministic segmentation, so the caller's chart reading has something to be checked against.

The engine cannot tell an honest chain from a flattering one by measuring it -- every anchor
in a chain that skipped a contraction is still its own span's extreme. What it can do is
produce its own segmentation and compare. This is that segmentation, and it is the harness's
own convention rather than anything the source specifies: the source calls swing reading
chart work and never names a retracement.
"""

from __future__ import annotations

import unittest

from scripts.minervini.swings import segment
from tests.series import anchor_dates, base_series


class RecoversTheSourcesOwnExampleTests(unittest.TestCase):
    def test_the_turning_points_of_a_twenty_five_ten_five_base_are_found(self) -> None:
        frame, anchors = base_series(depths=(25.0, 10.0, 5.0))
        expected = anchor_dates(frame, anchors)

        found = segment(frame, retracement_pct=1.0)

        self.assertEqual([item["date"] for item in found["anchors"]], expected)

    def test_the_chain_alternates_high_and_low_starting_and_ending_on_a_high(self) -> None:
        frame, _ = base_series()

        kinds = [item["kind"] for item in segment(frame, retracement_pct=1.0)["anchors"]]

        self.assertEqual(kinds, ["high", "low"] * (len(kinds) // 2) + ["high"])

    def test_the_breakout_underway_is_kept_out_of_the_base(self) -> None:
        """A move still in progress is unconfirmed, and the breakout is exactly that move.

        Confirming an extreme means watching price fall away from it, which a breakout has not
        done. Folding it into the chain would put the pivot on the breakout bar -- the level
        the entry is measured against would become the entry's own session.
        """

        frame, anchors = base_series()

        found = segment(frame, retracement_pct=1.0)

        self.assertEqual(found["anchors"][-1]["date"], anchor_dates(frame, anchors)[-1])
        self.assertEqual(found["provisional"]["date"], frame.index[-1].date().isoformat())


class ThresholdSensitivityTests(unittest.TestCase):
    def test_a_threshold_above_the_smallest_contraction_stops_seeing_it(self) -> None:
        """The reason a single threshold cannot be trusted, made visible rather than hidden."""

        frame, _ = base_series(depths=(25.0, 10.0, 5.0))

        coarse = segment(frame, retracement_pct=7.0)["anchors"]
        fine = segment(frame, retracement_pct=1.0)["anchors"]

        self.assertLess(len(coarse), len(fine))

    def test_noise_below_the_threshold_is_not_counted_as_a_contraction(self) -> None:
        frame, _ = base_series(depths=(25.0, 10.0, 5.0))
        # A one-session wobble a fifth of the smallest declared contraction.
        position = len(frame) // 2
        frame.iloc[position, frame.columns.get_loc("Low")] *= 0.99

        self.assertEqual(len(segment(frame, retracement_pct=1.0)["anchors"]), 7)


class UnusableHistoryTests(unittest.TestCase):
    def test_a_history_with_no_completed_bars_segments_into_nothing(self) -> None:
        frame, _ = base_series()

        self.assertEqual(segment(frame.iloc[:0], retracement_pct=1.0)["anchors"], [])

    def test_a_retracement_that_is_not_a_positive_percentage_is_refused(self) -> None:
        frame, _ = base_series()

        for value in (0.0, -1.0, 100.0):
            with self.subTest(retracement=value):
                with self.assertRaises(ValueError):
                    segment(frame, retracement_pct=value)


if __name__ == "__main__":
    unittest.main()
