"""Measure a Power Play from bars, without consulting doctrine about it.

The same separation the base measurements keep: the registry owns every limit, so the search
windows arrive as an argument and nothing here decides anything. Expected numbers are the ones
the series was built with, so agreement is with the fixture's construction rather than with the
arithmetic under test.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import measure_power_play
from tests.series import power_play_series, reverse_split_series, wide_launch_bar_series


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

    def test_a_high_inside_the_advance_becomes_the_peak_the_flag_hangs_from(self):
        """A flag is under the structure's high, not under whichever high the search stopped at.

        Two of twenty-three real tickers reported a six-week flag that was six weeks only
        because the search window ended there; a bar shortly before it had traded higher. The
        earlier high is the top the sideways move is under, so the flag is measured from it and
        comes out longer than the source allows.
        """
        bars = power_play_series(spike_above_peak_pct=8.0)

        measured = measure_power_play(bars, SPEC)

        self.assertAlmostEqual(measured["peak_high"], 21.0 * 1.08, places=6)
        self.assertGreater(measured["flag_weeks"], 6.0)

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

    def test_a_flag_longer_than_the_source_allows_measures_longer(self):
        """The six-week limit has to be able to reject, which means finding what it rejects.

        Looking for the peak inside the longest flag the source allows makes every flag six
        weeks or shorter by selection: the limit is then satisfied by the search rather than by
        the stock. The peak is looked for across the longest structure the criteria describe --
        an eight-week advance and a six-week flag -- so a flag that really ran ten weeks
        measures ten and fails on its own length.
        """
        bars = power_play_series(flag_sessions=50)

        measured = measure_power_play(bars, SPEC)

        self.assertEqual(measured["flag_sessions"], 50)
        self.assertAlmostEqual(measured["flag_weeks"], 10.0, places=6)

    def test_a_truncated_baseline_is_no_baseline(self):
        """The volume the advance began against needs the full window, or it is not that volume.

        Sliced to a shorter lookback, five real tickers reported the same peak, the same advance
        and the same flag while the launch volume ratio moved -- the only thing that had changed
        was how many sessions were left in front of the launch to average. A short average
        wearing a full one's name is worse than an admitted gap.
        """
        bars = power_play_series(dormancy_sessions=60)

        full = measure_power_play(bars, SPEC)
        clipped = measure_power_play(bars.iloc[-70:], SPEC)

        self.assertIsNotNone(full["advance_volume_ratio"])
        self.assertIsNone(clipped["advance_volume_ratio"])

    def test_a_reverse_split_advances_the_tape_and_nothing_else(self):
        """The advance is read three ways because the raw tape cannot tell a move from a split.

        A one-for-two reverse split doubles every printed price overnight. Extremes and raw
        closes both report the hundred percent the first criterion asks for, on a stock whose
        holders gained nothing. The provider does not adjust for corporate actions -- its own
        coverage says so -- so the adjusted closes are the only reading that knows.
        """
        measured = measure_power_play(reverse_split_series(), SPEC)

        self.assertAlmostEqual(measured["advance_pct_closes"], 100.0, places=6)
        self.assertAlmostEqual(measured["advance_pct_adjusted"], 0.0, places=6)

    def test_a_history_without_adjusted_closes_has_no_adjusted_reading(self):
        """Absent, not zero. A missing correction is a gap, and a gap is not a measurement."""

        measured = measure_power_play(power_play_series(), SPEC)

        self.assertIsNone(measured["advance_pct_adjusted"])
        self.assertIsNotNone(measured["advance_pct_closes"])

    def test_an_equal_high_from_before_the_structure_is_not_this_flag_s_start(self):
        """Reading the peak from the first equal high anywhere is the mirror of reading the last.

        The rule that stops a later equal high from re-labelling the flag as advance will, left
        unbounded, glue this structure to a session months earlier that merely printed the same
        price. Both are the same mistake about what a tie means. The peak is looked for inside
        the longest structure the criteria describe and nowhere else.
        """
        bars = power_play_series(ancient_equal_high=True)

        measured = measure_power_play(bars, SPEC)

        self.assertEqual(measured["flag_sessions"], 20)

    def test_the_closes_reading_starts_before_the_move_not_inside_it(self):
        """"An explosive price move commences on huge volume" -- the launch bar is part of it.

        Measured from the launch session's own close, the first day of the advance is discarded:
        a stock that went from ninety to two hundred in two weeks reports thirty-three percent,
        because the session that did half the work is where the reading starts. The price before
        the move is the last close before it.
        """
        measured = measure_power_play(wide_launch_bar_series(), SPEC)

        self.assertAlmostEqual(measured["advance_pct_closes"], (200.0 - 90.0) / 90.0 * 100, places=6)

    def test_a_launch_with_nothing_before_it_has_no_closes_reading(self):
        """Absent, not zero -- the price before the move is missing, so the reading is."""

        bars = wide_launch_bar_series()
        measured = measure_power_play(bars.iloc[45:], SPEC)

        self.assertIsNone(measured["advance_pct_closes"])

    def test_the_launch_session_carries_the_volume_clause_not_the_whole_advance(self):
        """"commences on huge volume" is about the session it commenced on.

        Averaged across the advance, a launch that printed ten times its baseline is diluted by
        the quiet sessions behind it: one session at 10M followed by nineteen at 0.5M averages
        under a 1M baseline and reads as no expansion at all, on a stock that began exactly the
        way the criterion describes.
        """
        measured = measure_power_play(wide_launch_bar_series(), SPEC)

        self.assertAlmostEqual(measured["launch_volume_ratio"], 10.0, places=6)
        self.assertLess(measured["advance_volume_ratio"], 10.0)


if __name__ == "__main__":
    unittest.main()
