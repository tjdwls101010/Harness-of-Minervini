"""Time is evidence: the first sessions out of the base, the reactions since, and the topping vector."""

from __future__ import annotations

from tests.frames import frame

import unittest
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence


def flat(sessions: int, close: float = 100.0, volume: int = 1_000_000) -> list[tuple[float, float, float, float, int]]:
    return [(close, close * 1.01, close * 0.99, close, volume)] * sessions


def bar(close: float, volume: int = 1_000_000, *, open_: float | None = None, high: float | None = None, low: float | None = None) -> tuple[float, float, float, float, int]:
    return (close if open_ is None else open_, high if high is not None else close * 1.01, low if low is not None else close * 0.99, close, volume)


def build(bars: pd.DataFrame, *, entry: int, **kwargs: object) -> dict:
    return build_management_evidence(bars, entry_date=bars.index[entry].date(), as_of=bars.index[-1].date(), **kwargs)


class TheFirstSessionsOutOfTheBase(unittest.TestCase):
    """Zanger's window: the first two sessions, reported as contrast and never as an action."""

    def test_both_sessions_are_reported_with_their_own_volume_and_close(self) -> None:
        rows = flat(50) + [bar(105.0, 3_000_000), bar(107.0, 2_000_000), bar(106.0)]
        bars = frame(rows)
        result = build(bars, entry=50, breakout_date=bars.index[50].date())

        block = result["post_breakout_behavior"]["first_sessions"]
        self.assertEqual(block["window_sessions"], 2)
        self.assertEqual(block["source"], "Zanger")
        self.assertIs(block["binds"], False)
        self.assertEqual([session["date"] for session in block["sessions"]], [bars.index[50].date().isoformat(), bars.index[51].date().isoformat()])
        self.assertEqual(block["sessions"][0]["volume_ratio"], 3.0)
        self.assertAlmostEqual(block["sessions"][1]["close_vs_first_session_pct"], 1.9047619048)

    def test_a_window_the_history_does_not_reach_yet_says_how_many_it_has(self) -> None:
        rows = flat(50) + [bar(105.0, 3_000_000)]
        bars = frame(rows)
        result = build(bars, entry=50, breakout_date=bars.index[50].date())

        block = result["post_breakout_behavior"]["first_sessions"]
        self.assertEqual(len(block["sessions"]), 1)
        self.assertEqual(block["sessions_available"], 1)


class NaturalReactionsAndTennisBallAction(unittest.TestCase):
    def test_a_brief_pullback_that_recovered_to_a_new_high_is_measured(self) -> None:
        # Out of the base at 100, a high at 110, three sessions down to 104.5, then a new high.
        rows = flat(50) + [bar(102.0), bar(110.0), bar(108.0), bar(106.0), bar(104.5), bar(109.0), bar(112.0)]
        bars = frame(rows)
        result = build(bars, entry=50, breakout_date=bars.index[50].date())

        reactions = result["post_breakout_behavior"]["natural_reactions"]
        self.assertEqual(len(reactions), 1)
        reaction = reactions[0]
        self.assertEqual(reaction["peak_date"], bars.index[51].date().isoformat())
        self.assertEqual(reaction["low_date"], bars.index[54].date().isoformat())
        self.assertAlmostEqual(reaction["depth_pct"], -5.0)
        self.assertEqual(reaction["sessions_to_low"], 3)
        self.assertEqual(reaction["recovered_in_sessions"], 5)

    def test_a_pullback_still_unrecovered_says_so_instead_of_guessing(self) -> None:
        rows = flat(50) + [bar(102.0), bar(110.0), bar(108.0), bar(104.0), bar(105.0)]
        bars = frame(rows)
        result = build(bars, entry=50, breakout_date=bars.index[50].date())

        reaction = result["post_breakout_behavior"]["natural_reactions"][-1]
        self.assertIsNone(reaction["recovered_in_sessions"])
        self.assertEqual(reaction["sessions_since_peak"], 3)


class TimeSinceTheStockLastActed(unittest.TestCase):
    def test_the_block_counts_sessions_since_entry_and_since_the_last_new_high(self) -> None:
        rows = flat(50) + [bar(102.0), bar(110.0)] + [bar(105.0)] * 4
        bars = frame(rows)
        result = build(bars, entry=50, breakout_date=bars.index[50].date())

        block = result["post_breakout_behavior"]
        self.assertEqual(block["sessions_since_entry"], 5)
        self.assertEqual(block["sessions_since_new_high"], 4)
        self.assertAlmostEqual(block["gain_since_first_session_pct"], 2.9411764706)  # measured from the entry session close of 102, not from the base
        self.assertEqual(block["doctrine_ids"], ["management.tennis_ball_action_after_the_breakout", "management.stock_that_does_not_act_as_expected", "management.zanger_first_two_days_out_of_the_base"])


class TheToppingVector(unittest.TestCase):
    def test_volatility_expansion_and_the_two_hundred_day_slope_are_reported(self) -> None:
        rows = [bar(100.0, low=99.5, high=100.5)] * 210 + [bar(100.0, low=95.0, high=105.0)] * 14
        bars = frame(rows)
        result = build(bars, entry=200)

        block = result["stage3_transition"]
        self.assertEqual(block["doctrine_id"], "stage.stage3_characteristics")
        self.assertGreater(block["volatility_ratio"], 5.0)
        self.assertIs(block["needs_chart"], True)
        self.assertEqual(block["sma200_slope_pct"], 0.0)

    def test_without_two_hundred_sessions_the_slope_is_unavailable_not_zero(self) -> None:
        result = build(frame(flat(60)), entry=50)

        self.assertIsNone(result["stage3_transition"]["sma200_slope_pct"])
        self.assertEqual(result["stage3_transition"]["sma200_state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
