"""A measurement that came out NaN or infinite is a measurement nobody made."""

from __future__ import annotations

import math
import unittest

from scripts.minervini import doctrine


GATE = ("risk.initial_stop_and_reward", "initial_stop_ceiling_pct")
BAND = ("management.tl_base_extension_pause_zone", "pause_zone_pct")
MARKER = ("setup.volume_state_convention", "high_volume_ratio")


class NonFiniteMeasurements(unittest.TestCase):
    def test_a_nan_never_becomes_a_verdict_word(self) -> None:
        for claim_id, name, evaluate in (
            (*GATE, doctrine.evaluate_gate),
            (*BAND, doctrine.evaluate_band),
            (*MARKER, doctrine.evaluate_marker),
        ):
            signal = evaluate(claim_id, name, float("nan"))

            self.assertEqual(signal["state"], "unavailable", claim_id)
            self.assertEqual(signal["reason"], "measurement_not_finite", claim_id)

    def test_an_infinity_is_unavailable_rather_than_a_failure(self) -> None:
        signal = doctrine.evaluate_gate(*GATE, math.inf)

        self.assertEqual(signal["state"], "unavailable")

    def test_no_non_finite_number_reaches_the_published_signal(self) -> None:
        for claim_id, name, evaluate in (
            (*GATE, doctrine.evaluate_gate),
            (*BAND, doctrine.evaluate_band),
            (*MARKER, doctrine.evaluate_marker),
        ):
            signal = evaluate(claim_id, name, float("nan"))

            for key, value in signal.items():
                if isinstance(value, float):
                    self.assertTrue(math.isfinite(value), f"{claim_id}.{key}")

    def test_a_measurement_that_is_simply_absent_says_nothing_about_why(self) -> None:
        signal = doctrine.evaluate_band(*BAND, None)

        self.assertEqual(signal["state"], "unavailable")
        self.assertNotIn("reason", signal)


if __name__ == "__main__":
    unittest.main()
