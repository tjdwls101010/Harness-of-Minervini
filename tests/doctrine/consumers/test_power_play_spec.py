"""The search windows come out of the registry, not out of the module that searches with them.

The measurement module takes its windows as an argument so the same number is not written in
two places; this is the other half of that arrangement -- the claim's own limits, converted to
sessions, are what it gets handed. The conversion itself is a convention that changes verdicts,
so it is registered rather than left as a constant somewhere.
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.power_play_evidence import compile_power_play_spec


class TheWindowsAreTheSourcesOwnLimits(unittest.TestCase):
    def test_the_advance_window_is_the_eight_weeks_the_source_allows(self):
        spec = compile_power_play_spec()
        weeks = doctrine.threshold("fundamentals.power_play_exception", "advance_maximum_weeks")
        sessions = doctrine.parameter("convention.trading_week", "sessions_per_trading_week")

        self.assertEqual(spec["advance_window_sessions"], weeks * sessions)

    def test_the_flag_window_is_the_six_weeks_the_source_allows(self):
        spec = compile_power_play_spec()
        weeks = doctrine.threshold("fundamentals.power_play_exception", "flag_maximum_weeks")
        sessions = doctrine.parameter("convention.trading_week", "sessions_per_trading_week")

        self.assertEqual(spec["flag_window_sessions"], weeks * sessions)

    def test_the_conversion_travels_with_the_windows_it_compiled_them_from(self):
        """A module reporting durations in weeks has to divide by what the windows multiplied by.

        Divided by a constant instead, the two agree only while the registered value stays five:
        at four, a twenty-five session flag is six and a quarter weeks and would pass the six-week
        limit as five.
        """
        spec = compile_power_play_spec()

        self.assertEqual(
            spec["sessions_per_trading_week"],
            doctrine.parameter("convention.trading_week", "sessions_per_trading_week"),
        )

    def test_the_module_under_test_agrees_with_the_literal_its_unit_tests_use(self):
        """tests/unit/power_play/test_power_play.py names 30 and 40 so it can stay free of doctrine."""

        spec = compile_power_play_spec()

        self.assertEqual((spec["flag_window_sessions"], spec["advance_window_sessions"]), (30, 40))


if __name__ == "__main__":
    unittest.main()


class TheCandidateBoundIsThisHarnessSOwnConvention(unittest.TestCase):
    """Where the chain stops is a choice about structure identity, not a limit the source stated.

    The source's ten percent is the flag's decline after a peak has been chosen, and it is stated
    as an alternative to VCP character rather than as an elimination. Reusing that number to
    delete candidate tops applies one threshold to a different measurement, and a reader auditing
    the verdict would be sent to a passage that says nothing about which top the flag hangs from.
    """

    def test_the_bound_is_registered_at_the_harness_layer(self):
        claim = doctrine.get_claim("convention.power_play_top_candidates")

        self.assertEqual(claim["claim"]["layer"], "harness")
        self.assertEqual(claim["provenance"]["quotations"], [])

    def test_the_bound_is_a_parameter_rather_than_a_gate(self):
        claim = doctrine.get_claim("convention.power_play_top_candidates")

        self.assertEqual(claim["claim"]["thresholds"], {})
        self.assertIsNotNone(
            doctrine.parameter("convention.power_play_top_candidates", "candidate_top_maximum_distance_pct")
        )

    def test_the_spec_carries_it_to_the_reading(self):
        spec = compile_power_play_spec()

        self.assertEqual(
            spec["candidate_top_maximum_distance_pct"],
            float(doctrine.parameter("convention.power_play_top_candidates", "candidate_top_maximum_distance_pct")),
        )


class AConventionThatOnlyDefinesSomethingCannotFail(unittest.TestCase):
    """A registered failure effect is a promise about what a reducer will do.

    These two claims carry no threshold and state no filter -- they define how many sessions a
    week is, and how far down the chain of tops a reading goes. Nothing in them can be failed, so
    a declared effect of `needs_review` describes a reducer behaviour that does not exist and
    cannot: the reading past the bound is not evidence anybody withheld, it is a top this harness
    decided was a different structure.
    """

    def test_the_convention_claims_declare_no_failure_effect(self):
        for claim_id in ("convention.trading_week", "convention.power_play_top_candidates"):
            with self.subTest(claim_id=claim_id):
                claim = doctrine.get_claim(claim_id)["claim"]

                self.assertEqual(claim["thresholds"], {})
                self.assertTrue(claim["parameters"])
                self.assertEqual(claim["failure"]["effect"], "not_applicable")
