"""A window must be the sessions it names, and a bar the harness cannot read is not measured."""

from __future__ import annotations

from datetime import date
import math
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence


def frame(rows: int, *, end: str = "2025-12-26", close: float = 100.0) -> pd.DataFrame:
    index = pd.bdate_range(end=end, periods=rows)
    closes = pd.Series([close] * rows, index=index, dtype=float)
    return pd.DataFrame({"Open": closes, "High": closes * 1.01, "Low": closes * 0.99, "Close": closes, "Volume": np.full(rows, 1_000_000)}, index=index)


def build(bars: pd.DataFrame, **kwargs: object) -> dict:
    entry = kwargs.pop("entry", None)
    if entry is not None:
        kwargs["entry_date"] = bars.index[int(entry)].date()
    kwargs.setdefault("entry_date", bars.index[max(0, len(bars) - 5)].date())
    return build_management_evidence(bars, as_of=bars.index[-1].date(), **kwargs)


WINDOWED = ("base_extension", "moving_average_extension", "key_reversal", "gaps_since_breakout", "climax", "failed_volume_confirmation")


class ADeclaredSessionMustBeASession(unittest.TestCase):
    def test_a_weekend_breakout_date_is_not_quietly_moved_to_monday(self) -> None:
        bars = frame(80)
        friday = next(timestamp for timestamp in bars.index[40:70] if timestamp.weekday() == 4)
        saturday = (friday + pd.Timedelta(days=1)).date()
        result = build(bars, breakout_date=saturday, base_top=100.0)

        for key in ("failed_volume_confirmation", "gaps_since_breakout", "key_reversal"):
            self.assertEqual(result[key]["state"], "unavailable", key)
            self.assertEqual(result[key]["reason"], "no_completed_bar_on_breakout_date", key)

    def test_an_entry_session_the_provider_never_printed_stops_every_measurement(self) -> None:
        bars = frame(80)
        missing = bars.index[60].date()
        result = build(bars.drop(bars.index[60]), entry_date=missing, base_top=100.0)

        for key in WINDOWED:
            self.assertEqual(result[key], {"state": "unavailable", "reason": "no_completed_bar_on_entry_date"}, key)


class AWindowCannotStartBeforeTheHistory(unittest.TestCase):
    def test_since_entry_measurements_say_so_when_the_history_begins_later(self) -> None:
        bars = frame(80)
        result = build(bars, entry_date=date(2024, 1, 3), base_top=100.0)

        for key in ("base_extension", "key_reversal", "gaps_since_breakout"):
            self.assertEqual(result[key]["state"], "unavailable", key)
            self.assertEqual(result[key]["reason"], "history_starts_after_entry_date", key)


class ABarTheHarnessCannotRead(unittest.TestCase):
    def test_a_nan_bar_makes_the_structure_unavailable_instead_of_nan(self) -> None:
        bars = frame(80)
        bars.iloc[-1] = [float("nan")] * 5
        result = build(bars, base_top=100.0, breakout_date=bars.index[60].date())

        for key in WINDOWED:
            self.assertEqual(result[key]["state"], "unavailable", key)
            self.assertEqual(result[key]["reason"], "invalid_ohlc_history", key)

    def test_a_zero_price_does_not_crash_the_capability(self) -> None:
        bars = frame(80)
        bars.iloc[-1] = [0.0, 0.0, 0.0, 0.0, 0.0]
        result = build(bars, base_top=100.0)

        for key in WINDOWED:
            self.assertEqual(result[key]["state"], "unavailable", key)

    def test_nothing_non_finite_reaches_the_published_blocks(self) -> None:
        bars = frame(80)
        result = build(bars, base_top=100.0, breakout_date=bars.index[60].date())

        def check(node: object, path: str) -> None:
            if isinstance(node, float):
                self.assertTrue(math.isfinite(node), path)
            elif isinstance(node, dict):
                for key, value in node.items():
                    check(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    check(value, f"{path}[{index}]")

        check(result, "management")


class WhatCannotBeCompared(unittest.TestCase):
    def test_a_lone_session_in_the_window_cannot_be_the_widest_or_heaviest(self) -> None:
        bars = frame(80)
        result = build(bars, breakout_date=bars.index[-1].date())

        features = result["key_reversal"]["features"]
        self.assertIsNone(features["widest_range_since"])
        self.assertIsNone(features["highest_volume_since"])


if __name__ == "__main__":
    unittest.main()


class ABadBarOnlySpoilsWhatReadsIt(unittest.TestCase):
    def test_an_ancient_broken_session_does_not_void_this_week_s_measurements(self) -> None:
        bars = frame(120)
        bars.iloc[0, bars.columns.get_loc("Open")] = float("nan")
        result = build(bars, entry=110, base_top=100.0, breakout_date=bars.index[110].date())

        for key in ("base_extension", "key_reversal", "gaps_since_breakout", "climax", "twenty_day_average", "post_breakout_behavior"):
            self.assertNotEqual(result[key].get("reason"), "invalid_ohlc_history", key)

    def test_a_broken_session_the_block_reads_still_voids_it(self) -> None:
        # The extension is the latest close against the base top, so that is the close whose
        # loss voids it. A close in the middle of the held window is spanned, never opened.
        bars = frame(120)
        bars.iloc[119, bars.columns.get_loc("Close")] = 0.0
        result = build(bars, entry=110, base_top=100.0)

        self.assertEqual(result["base_extension"]["reason"], "invalid_ohlc_history")
        self.assertEqual(result["base_extension"]["date"], bars.index[119].date().isoformat())

    def test_a_broken_session_the_block_only_spans_leaves_it_reported(self) -> None:
        bars = frame(120)
        bars.iloc[115, bars.columns.get_loc("Close")] = 0.0
        result = build(bars, entry=110, base_top=100.0)

        self.assertEqual(result["base_extension"]["state"], "reported")


class TheWeekendAnchorAdvancesToTheNextSession(unittest.TestCase):
    def test_sunday_advances_one_day_and_saturday_two(self) -> None:
        from datetime import timedelta

        bars = frame(60)
        monday = bars.index[0].date()
        self.assertEqual(monday.weekday(), 0, "fixture must start on a Monday")
        for back, label in ((1, "Sunday"), (2, "Saturday")):
            result = build_management_evidence(bars, entry_date=bars.index[40].date(), as_of=bars.index[-1].date(), stage2_start=monday - timedelta(days=back))

            block = result["largest_decline_since_stage2_start"]
            self.assertEqual(block["measured_from"], monday.isoformat(), label)


class TheWindowsComeFromTheRegistry(unittest.TestCase):
    def test_changing_the_registered_window_changes_the_measurement(self) -> None:
        from unittest import mock

        from scripts.minervini import doctrine as doctrine_module
        from scripts.minervini import management_evidence

        bars = frame(80)
        real = doctrine_module.parameter

        def shorter(claim_id: str, name: str) -> float:
            if claim_id == "convention.momentum_review_windows":
                return {"short_window_sessions": 3, "medium_window_sessions": 4, "long_window_sessions": 6}[name]
            return real(claim_id, name)

        with mock.patch.object(management_evidence.doctrine, "parameter", side_effect=shorter):
            climax = build(bars, entry=70)["climax"]

        self.assertEqual(climax["windows"], {"return_3_pct": 3, "return_4_pct": 4, "return_6_pct": 6, "gap_ups_last_10_sessions": 4})
