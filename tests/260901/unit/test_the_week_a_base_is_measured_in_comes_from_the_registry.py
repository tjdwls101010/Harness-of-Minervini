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
from tests.readings import reregistered
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

    def test_moving_the_registry_moves_the_measurement(self) -> None:
        """The registry has to be moved, not the function that reads it.

        Handing `measure` two specs of my own making proves only that it reads its argument. A
        compiler that went back to hardcoding five would pass that and fail this.
        """

        frame, structure = structure_and_bars()

        five = measure(frame, structure, compile_measurement_spec())
        with reregistered(TRADING_WEEK, "parameters", "sessions_per_trading_week", 4):
            four = measure(frame, structure, compile_measurement_spec())

        self.assertAlmostEqual(five["base_duration_weeks"] * 5, four["base_duration_weeks"] * 4, places=6)
        self.assertGreater(four["base_duration_weeks"], five["base_duration_weeks"])

    def test_measure_reads_the_spec_it_was_handed_rather_than_a_constant(self) -> None:
        frame, structure = structure_and_bars()

        self.assertNotEqual(
            measure(frame, structure, spec(sessions_per_trading_week=4))["base_duration_weeks"],
            measure(frame, structure, spec(sessions_per_trading_week=5))["base_duration_weeks"],
        )

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


class ADenominatorIsNotTakenOnTrust(unittest.TestCase):
    """Zero raised out of the reducer as an internal error; a negative published minus thirty-three weeks."""

    def test_a_week_of_no_sessions_is_refused_before_anything_divides_by_it(self) -> None:
        for value in (0, -2, 1.5, True):
            with self.subTest(value=value):
                with reregistered(TRADING_WEEK, "parameters", "sessions_per_trading_week", value):
                    with self.assertRaises(ValueError):
                        compile_measurement_spec()

    def test_the_registry_itself_refuses_a_session_count_that_is_not_one(self) -> None:
        """`validate()` is not called at request time, so the read site checks too -- but it says so here."""

        for value in (0, -2, 1.5):
            with self.subTest(value=value):
                with reregistered(TRADING_WEEK, "parameters", "sessions_per_trading_week", value):
                    report = doctrine.validate()
                self.assertFalse(report["valid"])
                self.assertTrue(
                    any("measured in sessions" in error for error in report["errors"]),
                    report["errors"],
                )


class TheConventionIsCitedWhereItDecidedTheUnit(unittest.TestCase):
    def test_the_registry_registers_the_setup_surface_as_a_consumer(self) -> None:
        self.assertIn("ticker.setup", doctrine.get_claim(TRADING_WEEK)["claim"]["consumers"])
