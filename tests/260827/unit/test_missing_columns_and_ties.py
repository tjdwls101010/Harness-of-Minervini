"""What a missing column, a tie, and a same-session fill must say."""

from __future__ import annotations

from tests.frames import frame

import unittest
import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence


def flat(sessions: int, close: float = 100.0, volume: int = 1_000_000) -> list[tuple[float, float, float, float, int]]:
    return [(close, close * 1.01, close * 0.99, close, volume)] * sessions


def build(bars: pd.DataFrame, *, entry: int, **kwargs: object) -> dict:
    return build_management_evidence(bars, entry_date=bars.index[entry].date(), as_of=bars.index[-1].date(), **kwargs)


class AColumnTheProviderDidNotSend(unittest.TestCase):
    def test_without_opens_the_gap_measurements_name_what_is_missing(self) -> None:
        bars = frame(flat(70)).drop(columns=["Open"])
        result = build(bars, entry=60, breakout_date=bars.index[60].date())

        self.assertEqual(result["gaps_since_breakout"], {"state": "unavailable", "reason": "open_history_unavailable"})
        self.assertIn("open_history", result["key_reversal"]["missing_inputs"])
        self.assertIn("open_history", result["climax"]["missing_inputs"])

    def test_without_volume_the_volume_readings_name_what_is_missing(self) -> None:
        bars = frame(flat(70)).drop(columns=["Volume"])
        result = build(bars, entry=60, breakout_date=bars.index[60].date())

        self.assertEqual(result["failed_volume_confirmation"], {"state": "unavailable", "reason": "volume_history_unavailable"})
        self.assertIn("volume_history", result["key_reversal"]["missing_inputs"])
        self.assertIn("volume_history", result["climax"]["missing_inputs"])


class ATieIsStillTheHighest(unittest.TestCase):
    def test_a_latest_session_that_matches_the_heaviest_and_widest_meets_both_criteria(self) -> None:
        rows = flat(60) + [(100.0, 106.0, 100.0, 101.0, 3_000_000), (101.0, 103.0, 100.0, 102.0, 1_000_000), (102.0, 106.0, 100.0, 101.0, 3_000_000)]
        bars = frame(rows)
        result = build(bars, entry=60, breakout_date=bars.index[60].date())

        features = result["key_reversal"]["features"]
        self.assertIs(features["highest_volume_since"], True)
        self.assertIs(features["widest_range_since"], True)


class AGapFilledInsideItsOwnSession(unittest.TestCase):
    def test_a_session_that_opened_above_and_traded_back_through_filled_its_gap(self) -> None:
        rows = flat(60) + [(100.0, 101.0, 99.0, 100.0, 1_000_000), (103.0, 104.0, 100.0, 103.0, 1_000_000)]
        bars = frame(rows)
        result = build(bars, entry=60, breakout_date=bars.index[60].date())

        self.assertIs(result["gaps_since_breakout"]["latest_gap"]["filled"], True)


class TheWindowsAreReadFromTheRegistry(unittest.TestCase):
    def test_the_climax_block_names_the_windows_it_used_and_the_claim_that_holds_them(self) -> None:
        result = build(frame(flat(70)), entry=60)

        climax = result["climax"]
        self.assertEqual(climax["windows"], {"return_5_pct": 5, "return_10_pct": 10, "return_20_pct": 20, "gap_ups_last_10_sessions": 10})
        self.assertIn("convention.momentum_review_windows", climax["doctrine_ids"])

    def test_the_average_true_range_block_cites_its_own_convention(self) -> None:
        result = build(frame(flat(70)), entry=60)

        self.assertEqual(result["moving_average_extension"]["atr"]["doctrine_id"], "convention.average_true_range")


class WhatTheReviewProbeLeftAlive(unittest.TestCase):
    """Boundaries a mutant walked through while every test still passed."""

    def test_the_extension_average_is_readable_on_the_exact_session_it_warms_up(self) -> None:
        warm = build(frame(flat(21)), entry=0)["moving_average_extension"]["ema21"]
        cold = build(frame(flat(20)), entry=0)["moving_average_extension"]["ema21"]

        self.assertIn("extension_pct", warm)
        self.assertEqual(cold["state"], "unavailable")

    def test_a_breakout_with_exactly_fifty_prior_sessions_has_a_baseline(self) -> None:
        rows = flat(50) + [(100.0, 105.0, 99.0, 105.0, 800_000)] + flat(2, 103.0)
        enough = build(frame(rows), entry=50, breakout_date=frame(rows).index[50].date())
        short = build(frame(rows[1:]), entry=49, breakout_date=frame(rows[1:]).index[49].date())

        self.assertEqual(enough["failed_volume_confirmation"]["breakout_volume_ratio"], 0.8)
        self.assertEqual(short["failed_volume_confirmation"]["reason"], "insufficient_history_for_volume_baseline")

    def test_a_gap_on_the_first_session_of_the_window_is_counted(self) -> None:
        rows = flat(60) + [(103.0, 104.0, 102.5, 103.5, 1_000_000)] + flat(2, 103.5)
        bars = frame(rows)
        result = build(bars, entry=60, breakout_date=bars.index[60].date())

        self.assertEqual(result["gaps_since_breakout"]["gap_up_count"], 1)
        self.assertEqual(result["gaps_since_breakout"]["gap_dates"], [bars.index[60].date().isoformat()])

    def test_the_last_print_of_a_repeated_session_is_the_one_the_gap_count_reads(self) -> None:
        rows = flat(60) + [(100.0, 101.0, 99.0, 100.0, 1_000_000), (103.0, 104.0, 102.5, 103.5, 1_000_000)]
        bars = frame(rows)
        superseded = bars.iloc[[-2]].copy()
        superseded.index = bars.index[-1:]
        with_duplicate = pd.concat([bars.iloc[:-1], superseded, bars.iloc[-1:]])
        result = build_management_evidence(with_duplicate, entry_date=bars.index[60].date(), as_of=bars.index[-1].date(), breakout_date=bars.index[60].date())

        self.assertEqual(result["gaps_since_breakout"]["gap_up_count"], 1)

    def test_a_band_measurement_is_compared_at_the_precision_it_publishes(self) -> None:
        from scripts.minervini import doctrine

        signal = doctrine.evaluate_band("management.tl_base_extension_pause_zone", "pause_zone_pct", 19.99999999996)

        self.assertEqual(signal["measured"], 20.0)
        self.assertEqual(signal["state"], "within_source_range")


if __name__ == "__main__":
    unittest.main()
