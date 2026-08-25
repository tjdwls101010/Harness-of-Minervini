"""Measure the base the caller declared, without consulting doctrine about it.

Measurement and judgment are separate on purpose. Phase 1 made the registry the single
owner of every limit; a measurement function that also read limits would put the same
number in two places again, and the two would eventually disagree. So this takes the
window lengths it needs as an argument and returns numbers with no verdict attached.

Expected depths are the source's own worked example -- a 25 percent contraction, then 10,
then 5 -- so agreement here is agreement with the book, not with the code under test.
"""

from __future__ import annotations

import unittest

from scripts.minervini.setup_measurements import measure
from scripts.minervini.setup_structure import resolve_structure
from tests.series import anchor_dates, base_series


SPEC = {"volume_baseline_sessions": 50, "tightness_window_sessions": 10}


def measured(**kwargs) -> dict:
    frame, anchors = base_series(**kwargs)
    structure = resolve_structure(frame, anchor_dates(frame, anchors))
    assert structure["state"] == "resolved", structure["problems"]
    return measure(frame, structure, SPEC)


class ContractionSequenceTests(unittest.TestCase):
    def test_the_depths_the_source_named_come_back_as_the_depths_measured(self) -> None:
        numbers = measured(depths=(25.0, 10.0, 5.0))

        self.assertEqual([round(value, 4) for value in numbers["contraction_depths_pct"]], [25.0, 10.0, 5.0])
        self.assertEqual(numbers["contraction_count"], 3)

    def test_successive_ratios_are_reported_so_the_halving_can_be_read_not_decided(self) -> None:
        numbers = measured(depths=(25.0, 10.0, 5.0))

        self.assertEqual([round(value, 4) for value in numbers["successive_depth_ratios"]], [0.4, 0.5])

    def test_a_widening_sequence_reports_ratios_above_one_rather_than_failing_silently(self) -> None:
        numbers = measured(depths=(5.0, 10.0, 25.0))

        self.assertTrue(all(ratio > 1 for ratio in numbers["successive_depth_ratios"]), numbers["successive_depth_ratios"])
        self.assertFalse(numbers["contractions_contract"])

    def test_a_contracting_sequence_says_so(self) -> None:
        self.assertTrue(measured(depths=(25.0, 10.0, 5.0))["contractions_contract"])


class VolumeTests(unittest.TestCase):
    def test_volume_drying_into_the_final_contraction_reads_below_its_baseline(self) -> None:
        numbers = measured(volume_profile="drying")

        self.assertLess(numbers["final_contraction_volume_ratio"], 1.0)

    def test_volume_building_through_the_base_reads_above_its_baseline(self) -> None:
        numbers = measured(volume_profile="rising")

        self.assertGreater(numbers["final_contraction_volume_ratio"], 1.0)

    def test_distribution_shows_up_as_down_day_volume_outweighing_up_day_volume(self) -> None:
        """The source's one volume rule with no number in it: much bigger on up days."""

        numbers = measured(volume_profile="distribution")

        self.assertLess(numbers["up_down_volume_ratio"], 1.0)

    def test_accumulation_shows_up_as_up_day_volume_outweighing_down_day_volume(self) -> None:
        frame, anchors = base_series(volume_profile="distribution")
        frame["Volume"] = frame["Volume"].max() + frame["Volume"].min() - frame["Volume"]
        structure = resolve_structure(frame, anchor_dates(frame, anchors))

        numbers = measure(frame, structure, SPEC)

        self.assertGreater(numbers["up_down_volume_ratio"], 1.0)


class InsufficientHistoryTests(unittest.TestCase):
    def test_a_baseline_longer_than_the_history_is_unavailable_rather_than_a_short_average(self) -> None:
        frame, anchors = base_series()
        structure = resolve_structure(frame, anchor_dates(frame, anchors))

        numbers = measure(frame, structure, {"volume_baseline_sessions": 500, "tightness_window_sessions": 10})

        self.assertIsNone(numbers["final_contraction_volume_ratio"])


if __name__ == "__main__":
    unittest.main()


class RightSideDevelopmentTests(unittest.TestCase):
    def test_a_symmetric_base_reports_comparable_left_and_right_side_duration(self) -> None:
        numbers = measured(depths=(25.0, 10.0, 5.0))

        self.assertGreater(numbers["right_to_left_session_ratio"], 1.0)

    def test_a_v_shaped_recovery_reports_a_right_side_far_shorter_than_its_left(self) -> None:
        """The source calls this time compression and says to avoid it; it supplies no ratio."""

        numbers = measured(
            depths=(30.0, 5.0, 2.5),
            declines=(60, 6, 6),
            rallies=(3, 6, 6),
        )

        self.assertLess(numbers["right_to_left_session_ratio"], 0.5)

    def test_the_contractions_after_the_base_low_are_counted_separately(self) -> None:
        numbers = measured(depths=(25.0, 10.0, 5.0))

        self.assertEqual(numbers["right_side_contraction_count"], 2)


class BreakoutTests(unittest.TestCase):
    def test_a_close_above_the_declared_pivot_is_reported_as_cleared_with_its_extension(self) -> None:
        numbers = measured()

        self.assertTrue(numbers["pivot_cleared"])
        self.assertGreater(numbers["pivot_extension_pct"], 0)

    def test_the_breakout_bar_reports_its_volume_against_each_practitioner_baseline(self) -> None:
        numbers = measured()

        for sessions in (20, 30, 50):
            with self.subTest(sessions=sessions):
                self.assertGreater(numbers["breakout_volume_ratios"][sessions], 1.0)

    def test_the_closing_range_uses_the_formula_the_source_printed(self) -> None:
        """(Close - Low) / (High - Low), as a percentage; the source's own worked example is 80."""

        frame, anchors = base_series()
        frame.loc[frame.index[-1], ["High", "Low", "Close"]] = [100.0, 90.0, 98.0]
        structure = resolve_structure(frame, anchor_dates(frame, anchors))

        numbers = measure(frame, structure, SPEC)

        self.assertEqual(round(numbers["closing_range_pct"], 4), 80.0)

    def test_a_bar_with_no_range_leaves_the_closing_range_undefined(self) -> None:
        frame, anchors = base_series()
        frame.loc[frame.index[-1], ["High", "Low", "Close"]] = [100.0, 100.0, 100.0]
        structure = resolve_structure(frame, anchor_dates(frame, anchors))

        self.assertIsNone(measure(frame, structure, SPEC)["closing_range_pct"])
