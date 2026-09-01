"""The one conversion this module performs was written into it rather than handed to it.

`base_duration_weeks` is a session count divided by five. `convention.trading_week` registers
that five, and registers it precisely because it decides verdicts -- a base measured against
the 3-to-60 and 5-to-26 week bands moves when it changes. Re-registering the parameter left
the measurement where it was, so the registry recorded a number the measurement did not read.

The fix is not for this module to consult the registry: its own contract is that it takes the
window lengths it needs as an argument and returns numbers with no verdict attached, and
`compile_measurement_spec` exists to be the one place that reads claims on its behalf. So the
five travels the same road the volume baselines already travel.

A missing key is an error rather than a five. A default here would be the same constant back
in the same place, only harder to find, and it would answer for a registry nobody consulted.
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.setup_evidence import compile_measurement_spec
from scripts.minervini.setup_measurements import measure
from scripts.minervini.setup_structure import resolve_structure
from tests.series import anchor_dates, base_series


TRADING_WEEK = "convention.trading_week"


def structure_and_bars():
    frame, anchors = base_series()
    structure = resolve_structure(frame, anchor_dates(frame, anchors))
    assert structure["state"] == "resolved", structure["problems"]
    return frame, structure


def spec(**overrides) -> dict:
    return {**compile_measurement_spec(), **overrides}


class TheConversionArrivesAsAnArgument(unittest.TestCase):
    def test_the_spec_carries_the_registered_sessions_per_week(self) -> None:
        self.assertEqual(
            compile_measurement_spec()["sessions_per_trading_week"],
            int(doctrine.parameter(TRADING_WEEK, "sessions_per_trading_week")),
        )

    def test_a_different_registered_week_measures_a_different_number_of_weeks(self) -> None:
        """The registry says this number decides verdicts. It has to reach the measurement."""

        frame, structure = structure_and_bars()

        five = measure(frame, structure, spec(sessions_per_trading_week=5))
        four = measure(frame, structure, spec(sessions_per_trading_week=4))

        self.assertAlmostEqual(five["base_duration_weeks"] * 5, four["base_duration_weeks"] * 4, places=6)
        self.assertGreater(four["base_duration_weeks"], five["base_duration_weeks"])

    def test_the_measured_weeks_are_the_sessions_over_the_registered_week(self) -> None:
        frame, structure = structure_and_bars()
        numbers = measure(frame, structure, compile_measurement_spec())
        sessions = structure["base"]["duration_sessions"]
        week = int(doctrine.parameter(TRADING_WEEK, "sessions_per_trading_week"))

        self.assertEqual(numbers["base_duration_weeks"], round(sessions / week, 4))

    def test_a_spec_that_does_not_carry_it_is_an_error_rather_than_a_five(self) -> None:
        frame, structure = structure_and_bars()
        incomplete = {key: value for key, value in compile_measurement_spec().items() if key != "sessions_per_trading_week"}

        with self.assertRaises(KeyError):
            measure(frame, structure, incomplete)


if __name__ == "__main__":
    unittest.main()
