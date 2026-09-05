"""Selling into strength has reference points and reversal signatures; these measure them and decide nothing."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence


END = "2025-12-26"


def frame(rows: list[tuple[float, float, float, float, int]], *, end: str = END) -> pd.DataFrame:
    index = pd.bdate_range(end=end, periods=len(rows))
    bars = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=index)
    bars["Stock Splits"] = 0.0  # the provider always hands the column over; a frame without it has its own tests
    return bars


def flat(sessions: int, close: float = 100.0, volume: int = 1_000_000) -> list[tuple[float, float, float, float, int]]:
    return [(close, close * 1.01, close * 0.99, close, volume)] * sessions


def bar(close: float, volume: int = 1_000_000) -> tuple[float, float, float, float, int]:
    return (close, close * 1.01, close * 0.99, close, volume)


def rising(closes: list[float], volume: int = 1_000_000) -> list[tuple[float, float, float, float, int]]:
    """Bars that advance without gapping: each opens inside the prior session's range."""
    rows = []
    previous = closes[0]
    for close in closes:
        rows.append((max(close * 0.99, min(previous, close * 1.01)), close * 1.01, close * 0.99, close, volume))
        previous = close
    return rows


def build(bars: pd.DataFrame, *, entry: int = 0, **kwargs: object) -> dict:
    return build_management_evidence(bars, entry_date=bars.index[entry].date(), as_of=bars.index[-1].date(), **kwargs)


class BaseExtension(unittest.TestCase):
    def test_twenty_two_percent_over_the_base_top_sits_inside_the_pause_zone(self) -> None:
        bars = frame(flat(59) + [bar(122.0)])
        result = build(bars, entry=40, base_top=100.0)

        block = result["base_extension"]
        self.assertEqual(block["state"], "reported")
        self.assertEqual(block["base_top"], 100.0)
        self.assertEqual(block["extension_pct"], 22.0)
        self.assertAlmostEqual(block["max_extension_pct"], 23.22)
        self.assertEqual(block["band"]["state"], "within_source_range")
        self.assertEqual(block["band"]["source_range"], [20.0, 25.0])

    def test_past_the_zone_is_above_it_and_short_of_it_is_below(self) -> None:
        self.assertEqual(build(frame(flat(59) + [bar(130.0)]), entry=40, base_top=100.0)["base_extension"]["band"]["state"], "above_source_range")
        self.assertEqual(build(frame(flat(59) + [bar(110.0)]), entry=40, base_top=100.0)["base_extension"]["band"]["state"], "below_source_range")

    def test_without_the_base_top_there_is_nothing_to_measure_from(self) -> None:
        self.assertEqual(build(frame(flat(60)), entry=40)["base_extension"], {"state": "unavailable", "reason": "base_top_not_declared"})


class ExtensionFromTheAverages(unittest.TestCase):
    def test_the_extension_is_reported_in_percent_and_in_average_true_range(self) -> None:
        # Fifty-nine sessions at 100, then 110. The 50 SMA is 100.2; the 14-session ATR is
        # (13 x 2.0 + 11.1) / 14 = 2.65, the last true range being 111.1 - 100.
        result = build(frame(flat(59) + [bar(110.0)]), entry=40)

        block = result["moving_average_extension"]
        self.assertEqual(block["atr"]["length_sessions"], 14)
        self.assertAlmostEqual(block["atr"]["value"], 2.65)
        sma = block["sma50"]
        self.assertAlmostEqual(sma["extension_pct"], 9.7804391218)
        self.assertAlmostEqual(sma["extension_atr"], 9.8 / 2.65)
        self.assertEqual(sma["historical_percentile"], 100.0)
        self.assertEqual(sma["history_sessions"], 10)
        self.assertAlmostEqual(block["ema21"]["extension_pct"], 9.009009009, places=6)

    def test_too_little_history_reports_unavailable_not_a_number(self) -> None:
        result = build(frame(flat(10)), entry=5)

        self.assertEqual(result["moving_average_extension"]["atr"]["state"], "unavailable")
        self.assertEqual(result["moving_average_extension"]["sma50"]["state"], "unavailable")


class KeyReversalCriteria(unittest.TestCase):
    def test_the_three_computable_criteria_are_read_off_the_last_bar(self) -> None:
        # Flat at 100 (high 101, low 99), then a bar that gaps to 103, trades down to 98 and
        # closes 98.5 on triple volume: the widest bar and the heaviest since the breakout.
        bars = frame(flat(29) + [(103.0, 104.0, 98.0, 98.5, 3_000_000)])
        result = build(bars, entry=20, breakout_date=bars.index[20].date())

        block = result["key_reversal"]
        self.assertEqual(block["since"], bars.index[20].date().isoformat())
        self.assertEqual(block["date"], bars.index[-1].date().isoformat())
        features = block["features"]
        self.assertIs(features["gap_up_filled_and_reversed"], True)
        self.assertIs(features["highest_volume_since"], True)
        self.assertIs(features["widest_range_since"], True)
        self.assertIs(features["closed_below_prior_low"], True)
        self.assertAlmostEqual(features["closing_range_pct"], 8.3333333333)
        self.assertIsNone(features["visually_extended"])
        self.assertIsNone(features["trend_line_of_highs_breached"])
        # Three, not four: the source's sixth item asks for a reversal below the prior low
        # AND a close low in the range, and the second half has no boundary in the source.
        self.assertEqual(block["computable_criteria_met"], 3)
        self.assertIsNone(block["features"]["reversed_below_prior_low_and_closed_low_in_range"])
        self.assertIn("reversed_below_prior_low_and_closed_low_in_range", block["unresolved_criteria"])
        self.assertIs(block["needs_chart"], True)

    def test_an_ordinary_bar_meets_none(self) -> None:
        # Narrower and quieter than the sessions before it: nothing about it is a maximum.
        bars = frame(flat(29) + [(100.0, 100.5, 99.5, 100.0, 500_000)])
        result = build(bars, entry=20, breakout_date=bars.index[20].date())

        self.assertEqual(result["key_reversal"]["computable_criteria_met"], 0)

    def test_without_a_breakout_date_the_criteria_are_withheld(self) -> None:
        # The criteria are read since the breakout. An early or cheat entry has not broken out yet,
        # so measuring them from the entry session would apply post-breakout doctrine to a position
        # the doctrine has nothing to say about.
        bars = frame(flat(30))
        result = build(bars, entry=20)

        self.assertEqual(result["key_reversal"], {"state": "unavailable", "reason": "breakout_date_not_declared"})


class GapsSinceTheBreakout(unittest.TestCase):
    def test_gap_ups_are_counted_and_the_latest_is_described(self) -> None:
        rows = flat(22)
        rows += [(102.0, 103.0, 101.5, 102.5, 1_000_000)]  # gap over the prior high of 101
        rows += [(102.5, 103.5, 101.5, 102.5, 1_000_000)] * 5
        rows += [(104.5, 106.0, 104.0, 105.5, 1_000_000)]  # gap over 103.5, and it never traded back through
        rows += [(105.0, 106.0, 104.0, 105.0, 1_000_000)] * 2
        bars = frame(rows)
        result = build(bars, entry=20, breakout_date=bars.index[20].date())

        block = result["gaps_since_breakout"]
        self.assertEqual(block["gap_up_count"], 2)
        self.assertEqual(block["gap_dates"], [bars.index[22].date().isoformat(), bars.index[28].date().isoformat()])
        self.assertEqual(block["run_pct_since_breakout"], 6.0)
        latest = block["latest_gap"]
        self.assertIs(latest["filled"], False)
        self.assertEqual(latest["closing_range_pct"], 75.0)

    def test_a_gap_that_was_later_traded_back_through_is_filled(self) -> None:
        rows = flat(22) + [(102.0, 103.0, 101.5, 102.5, 1_000_000)] + [(102.0, 102.5, 100.5, 101.0, 1_000_000)] + flat(2, 101.0)
        bars = frame(rows)
        result = build(bars, entry=20, breakout_date=bars.index[20].date())

        self.assertIs(result["gaps_since_breakout"]["latest_gap"]["filled"], True)


class ClimaxFeatures(unittest.TestCase):
    def test_short_horizon_returns_and_the_last_session_s_volume_rank_are_reported(self) -> None:
        closes = [100.0] * 30 + [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 114.0, 116.0, 118.0, 120.0]
        rows = rising(closes)
        rows[-1] = rows[-1][:4] + (5_000_000,)
        result = build(frame(rows), entry=20)

        block = result["climax"]
        self.assertAlmostEqual(block["return_5_pct"], 9.0909090909)
        self.assertEqual(block["return_10_pct"], 20.0)
        self.assertEqual(block["return_20_pct"], 20.0)
        self.assertEqual(block["gap_ups_last_10_sessions"], 0)
        self.assertEqual(block["last_volume_percentile"], 100.0)
        self.assertEqual(block["last_closing_range_pct"], 50.0)
        self.assertIs(block["needs_chart"], True)


class FailedVolumeConfirmation(unittest.TestCase):
    def test_a_down_session_heavier_than_the_breakout_session_is_the_event(self) -> None:
        rows = flat(55) + [bar(105.0, 800_000)] + [bar(106.0)] + [bar(103.0, 2_000_000)] + flat(2, 103.0)
        bars = frame(rows)
        result = build(bars, entry=55, breakout_date=bars.index[55].date())

        block = result["failed_volume_confirmation"]
        self.assertEqual(block["breakout_date"], bars.index[55].date().isoformat())
        self.assertAlmostEqual(block["breakout_volume_ratio"], 0.8)
        self.assertEqual(block["heaviest_down_session"]["date"], bars.index[57].date().isoformat())
        self.assertAlmostEqual(block["heaviest_down_session"]["volume_ratio"], 2.0)
        self.assertIs(block["selling_volume_exceeded_breakout_volume"], True)
        self.assertEqual(block["breakout_volume_signal"]["role"], "marker")

    def test_light_selling_after_a_light_breakout_is_not_the_event(self) -> None:
        rows = flat(55) + [bar(105.0, 800_000)] + [bar(106.0)] + [bar(103.0, 500_000)] + flat(2, 103.0)
        bars = frame(rows)
        result = build(bars, entry=55, breakout_date=bars.index[55].date())

        self.assertIs(result["failed_volume_confirmation"]["selling_volume_exceeded_breakout_volume"], False)

    def test_without_a_breakout_date_there_is_no_breakout_volume(self) -> None:
        self.assertEqual(build(frame(flat(60)), entry=40)["failed_volume_confirmation"], {"state": "unavailable", "reason": "breakout_date_not_declared"})


if __name__ == "__main__":
    unittest.main()
