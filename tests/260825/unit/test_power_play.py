"""Measure a Power Play from bars, without consulting doctrine about it.

The same separation the base measurements keep: the registry owns every limit, so the search
windows arrive as an argument and nothing here decides anything. Expected numbers are the ones
the series was built with, so agreement is with the fixture's construction rather than with the
arithmetic under test.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import measure_power_play
from tests.series import power_play_series


# Six weeks of flag and eight of advance, in sessions. Checked against the registry by
# tests/260825/doctrine/test_power_play_spec.py rather than trusted here.
SPEC = {"flag_window_sessions": 30, "advance_window_sessions": 40}


class MeasuresTheStructureTheSourceDescribes(unittest.TestCase):
    def test_it_recovers_the_advance_and_flag_the_series_was_built_with(self):
        bars = power_play_series(
            dormant_price=10.0,
            advance_pct=110.0,
            advance_sessions=25,
            flag_sessions=20,
            flag_depth_pct=12.0,
        )

        measured = measure_power_play(bars, SPEC)

        self.assertAlmostEqual(measured["peak_high"], 21.0, places=6)
        self.assertAlmostEqual(measured["advance_low"], 10.0, places=6)
        self.assertAlmostEqual(measured["advance_pct"], 110.0, places=6)
        self.assertEqual(measured["flag_sessions"], 20)
        self.assertAlmostEqual(measured["flag_depth_pct"], 12.0, places=6)

    def test_a_high_inside_the_advance_denies_the_flag_its_peak(self):
        """A flag hanging under a high the same structure already made is not a Power Play flag.

        Both windows are anchored at the last bar, which is what keeps the reading still when a
        caller loads more history -- and is also what makes this invisible from the flag alone.
        Two of eighteen real tickers reported a six-week flag that was only six weeks because
        the window stopped there; the bar before it had traded higher.
        """
        bars = power_play_series(spike_above_peak_pct=8.0)

        measured = measure_power_play(bars, SPEC)

        self.assertIs(measured["peak_is_the_structure_high"], False)

    def test_an_undisturbed_advance_leaves_the_peak_the_structure_high(self):
        measured = measure_power_play(power_play_series(), SPEC)

        self.assertIs(measured["peak_is_the_structure_high"], True)

    def test_a_later_equal_high_does_not_restart_the_flag(self):
        """The flag runs from the first session that made this high, not the last.

        Reading it from the last equal high re-labels the flag that came before as part of the
        advance: a thirty-one session flag becomes a twelve session one and a structure that
        fails the six-week limit qualifies. Nothing explosive happened on a session that merely
        matched a high already made.
        """
        bars = power_play_series(flag_sessions=40, tie_the_peak_at=-13)

        measured = measure_power_play(bars, SPEC)

        self.assertEqual(measured["flag_sessions"], 40)


if __name__ == "__main__":
    unittest.main()
