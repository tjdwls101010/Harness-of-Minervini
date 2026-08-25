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
        """tests/260825/unit/test_power_play.py names 30 and 40 so it can stay free of doctrine."""

        spec = compile_power_play_spec()

        self.assertEqual((spec["flag_window_sessions"], spec["advance_window_sessions"]), (30, 40))


if __name__ == "__main__":
    unittest.main()
