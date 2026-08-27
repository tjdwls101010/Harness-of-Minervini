"""Arithmetic, checked against values worked out independently of the code that makes them.

Three ways a figure goes wrong without any guard being involved: a comparison window that
warms up one session late, an equality test on binary floats for a rule that is about the
number the harness publishes, and a value rounded for publication being fed back in as an
input to the next calculation.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence


def bars(rows: list[tuple[float, float, float, float]], *, start: str = "2026-07-01") -> pd.DataFrame:
    index = pd.bdate_range(start=start, periods=len(rows))
    frame = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    frame["Volume"] = np.full(len(frame), 1_000_000.0)
    frame["Stock Splits"] = np.zeros(len(frame))
    return frame


def build(frame: pd.DataFrame, **kwargs) -> dict:
    return build_management_evidence(frame, entry_date=frame.index[0].date(), as_of=frame.index[-1].date(), **kwargs)


class TheComparisonWarmsUpWhenItCan(unittest.TestCase):
    def test_twice_the_true_range_length_plus_one_is_enough_for_both_averages(self) -> None:
        # Fourteen ranges of 1.0 behind fourteen of 2.0, plus the session the first range
        # is measured from: twenty-nine bars, and the ratio is exactly two.
        rows = [(100.0, 100.5, 99.5, 100.0)] * 15 + [(100.0, 101.0, 99.0, 100.0)] * 14
        result = build(bars(rows))["stage3_transition"]

        self.assertEqual(result["earlier_average_true_range"]["value"], 1.0)
        self.assertEqual(result["average_true_range"]["value"], 2.0)
        self.assertEqual(result["volatility_ratio"], 2.0)


class ATieIsATieInTheNumberPublished(unittest.TestCase):
    DECLINES = [0.01, 0.00697, 0.00485809]

    def test_two_declines_that_publish_the_same_figure_resolve_to_the_later(self) -> None:
        rows = [(close, close, close, close) for close in self.DECLINES]
        frame = bars(rows, start="2026-08-24")
        result = build(frame, stage2_start=frame.index[0].date())["largest_decline_since_stage2_start"]["daily"]

        self.assertEqual(result["largest_pct"], -30.3)
        self.assertEqual(result["date"], "2026-08-26")
        self.assertIs(result["last_session_is_largest"], True)

    def test_the_weekly_reading_resolves_the_same_tie_the_same_way(self) -> None:
        index = pd.DatetimeIndex([pd.Timestamp("2026-08-07"), pd.Timestamp("2026-08-14"), pd.Timestamp("2026-08-21")])
        frame = pd.DataFrame([(close, close, close, close) for close in self.DECLINES], columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
        frame["Volume"] = np.full(len(frame), 1_000_000.0)
        frame["Stock Splits"] = np.zeros(len(frame))
        result = build_management_evidence(frame, entry_date=index[0].date(), as_of=index[-1].date(), stage2_start=index[0].date())["largest_decline_since_stage2_start"]["weekly"]

        self.assertEqual(result["largest_pct"], -30.3)
        self.assertEqual(result["largest_week_ending"], "2026-08-21")


class ARoundedFigureIsNotAnInput(unittest.TestCase):
    def test_the_extension_in_true_ranges_divides_by_the_measurement_not_the_report(self) -> None:
        # Every true range is exactly one third; the last close sits 2.45 above the 50-day
        # average, so the extension is 7.35 true ranges and not 7.3500000007.
        rows = [(100.0 + 0.1 * i, 100.0 + 0.1 * i + 1 / 6, 100.0 + 0.1 * i - 1 / 6, 100.0 + 0.1 * i) for i in range(60)]
        result = build(bars(rows))["moving_average_extension"]

        self.assertEqual(result["sma50"]["extension_atr"], 7.35)

    def test_the_volatility_ratio_divides_two_measurements(self) -> None:
        rows = [(100.0, 100.0 + 1 / 6, 100.0 - 1 / 6, 100.0)] * 15 + [(100.0, 100.0 + 1 / 3, 100.0 - 1 / 3, 100.0)] * 14
        result = build(bars(rows))["stage3_transition"]

        self.assertEqual(result["volatility_ratio"], 2.0)


if __name__ == "__main__":
    unittest.main()
