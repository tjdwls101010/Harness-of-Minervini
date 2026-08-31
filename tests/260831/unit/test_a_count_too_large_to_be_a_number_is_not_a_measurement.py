"""An integer wider than a float is not a measurement, and it reached an evaluator as one.

`_measurable` exists so that a value nobody can compare produces the unavailable state
rather than a verdict word. It tested `math.isfinite(float(measured))` -- and `float()` on a
Python int too large for a binary64 raises rather than returning infinity, so the guard
never saw it. The exception escaped the reducer and the envelope came back internal_error.

`--base-count` is where a caller can hand one in: `operations` requires a whole number of at
least one and states no ceiling, because the source states none either. So the fix is here,
where the value stops being comparable, and not an invented upper bound on bases.
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.risk import reduce_risk


BAND = ("basecount.typical_top_after_3_to_5_bases", "typical_base_count_before_top")
GATE = ("risk.initial_stop_and_reward", "initial_stop_ceiling_pct")
WIDER_THAN_A_FLOAT = 10**400


class AnUncomparableMeasurementIsUnavailableAndNotAnError(unittest.TestCase):
    def test_a_band_reports_it_unmeasurable_rather_than_raising(self) -> None:
        reading = doctrine.evaluate_band(*BAND, WIDER_THAN_A_FLOAT)

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "measurement_not_finite")

    def test_a_gate_does_the_same_rather_than_publishing_a_verdict_word(self) -> None:
        reading = doctrine.evaluate_gate(*GATE, WIDER_THAN_A_FLOAT)

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "measurement_not_finite")


class TheReducerAndTheEnvelopeSurviveIt(unittest.TestCase):
    def test_both_modes_reduce_instead_of_raising(self) -> None:
        for mode in ("prospective", "active"):
            with self.subTest(mode=mode):
                result = reduce_risk({"mode": mode, "as_of": "2026-08-28", "base_count": WIDER_THAN_A_FLOAT})

                self.assertEqual(result["base_count_context"]["band"]["state"], "unavailable")

    def test_the_envelope_answers_instead_of_reporting_an_internal_error(self) -> None:
        payload = execute("ticker.risk", {"ticker": "AAPL", "as_of": "2026-08-28", "base_count": WIDER_THAN_A_FLOAT}, runtime=Runtime())

        self.assertNotEqual(payload["status"], "unavailable")
        self.assertEqual(payload["data"]["base_count_context"]["band"]["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
