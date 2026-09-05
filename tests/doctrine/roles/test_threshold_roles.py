"""A number's role decides whether it can reject a candidate or only describe one."""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine


GATE = ("risk.initial_stop_and_reward", "initial_stop_ceiling_pct")
BAND = ("eligibility.recent_ipo_primary_base", "three_to_five_week_base_depth_pct")


class GateTests(unittest.TestCase):
    def test_a_gate_inside_its_limit_passes(self) -> None:
        signal = doctrine.evaluate_gate(*GATE, 6.5)

        self.assertEqual(signal["state"], "pass")
        self.assertEqual(signal["role"], "gate")
        self.assertEqual(signal["required"], "<= 10")
        self.assertEqual(signal["doctrine_id"], GATE[0])

    def test_a_gate_just_past_its_limit_fails_without_proximity_language(self) -> None:
        signal = doctrine.evaluate_gate(*GATE, 10.1)

        self.assertEqual(signal["state"], "fail")
        self.assertNotIn("band_position", signal)
        self.assertNotIn("source_range", signal)

    def test_a_gate_at_its_limit_passes(self) -> None:
        self.assertEqual(doctrine.evaluate_gate(*GATE, 10.0)["state"], "pass")

    def test_an_absent_measurement_is_unavailable_not_a_pass(self) -> None:
        self.assertEqual(doctrine.evaluate_gate(*GATE, None)["state"], "unavailable")

    def test_a_band_cannot_be_read_as_a_gate(self) -> None:
        with self.assertRaises(ValueError):
            doctrine.evaluate_gate(*BAND, 30.0)


class BandTests(unittest.TestCase):
    def test_a_band_reports_where_in_the_range_the_measurement_landed(self) -> None:
        signal = doctrine.evaluate_band(*BAND, 34.9)

        self.assertEqual(signal["role"], "band")
        self.assertEqual(signal["state"], "within_source_range")
        self.assertEqual(signal["source_range"], [25, 35])
        self.assertEqual(signal["measured"], 34.9)
        self.assertEqual(signal["band_position"], 0.99)

    def test_two_measurements_inside_one_band_are_not_the_same_answer(self) -> None:
        loose = doctrine.evaluate_band(*BAND, 34.9)
        tight = doctrine.evaluate_band(*BAND, 26.0)

        self.assertEqual(loose["state"], tight["state"])
        self.assertNotEqual(loose["band_position"], tight["band_position"])

    def test_a_measurement_past_the_loose_edge_is_above_the_range(self) -> None:
        signal = doctrine.evaluate_band(*BAND, 41.0)

        self.assertEqual(signal["state"], "above_source_range")
        self.assertGreater(signal["band_position"], 1)

    def test_a_measurement_tighter_than_the_range_is_outside_it_on_the_good_side(self) -> None:
        # A shallower base than the source's range is better, never a defect -- and it is also
        # not inside the range. `direction` carries the first fact so the state can carry the
        # second one honestly.
        signal = doctrine.evaluate_band(*BAND, 12.0)

        self.assertEqual(signal["state"], "below_source_range")
        self.assertEqual(signal["direction"], "lower_is_better")
        self.assertLess(signal["band_position"], 0)

    def test_a_band_carries_the_quotation_the_response_must_cite(self) -> None:
        signal = doctrine.evaluate_band(*BAND, 30.0)

        self.assertIn("quotation", signal)
        self.assertGreater(len(signal["quotation"]), 20)

    def test_a_gate_cannot_be_read_as_a_band(self) -> None:
        with self.assertRaises(ValueError):
            doctrine.evaluate_band(*GATE, 6.5)


class ReferenceTests(unittest.TestCase):
    def test_a_reference_statistic_is_never_evaluated_against_a_ticker(self) -> None:
        with self.assertRaises(ValueError):
            doctrine.evaluate_gate("market.superperformers_emerge_from_corrections", "share_from_corrections_pct", 90)
        with self.assertRaises(ValueError):
            doctrine.evaluate_band("market.superperformers_emerge_from_corrections", "share_from_corrections_pct", 90)

    def test_a_reference_value_is_still_readable_as_context(self) -> None:
        self.assertEqual(doctrine.threshold("market.superperformers_emerge_from_corrections", "share_from_corrections_pct"), 90)


if __name__ == "__main__":
    unittest.main()
