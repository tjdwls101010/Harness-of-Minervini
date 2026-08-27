"""Structure can deteriorate while the stop is untouched; these are the measurements that say so."""

from __future__ import annotations

from datetime import date
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence


FRIDAY = "2025-12-26"


def frame(closes: list[float], *, end: str = FRIDAY, volumes: list[int] | None = None, lows: dict[int, float] | None = None) -> pd.DataFrame:
    index = pd.bdate_range(end=end, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    low = close * 0.99
    for position, value in (lows or {}).items():
        low.iloc[position] = value
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": low, "Close": close, "Volume": volumes if volumes is not None else np.full(len(close), 1_000_000)},
        index=index,
    )


def evidence(closes: list[float], *, entry_offset: int = 40, **kwargs: object) -> dict:
    bars = frame(closes, **{key: value for key, value in kwargs.items() if key in {"end", "volumes", "lows"}})
    entry_date = bars.index[entry_offset].date()
    return build_management_evidence(
        bars,
        entry_date=entry_date,
        as_of=bars.index[-1].date(),
        management_average=kwargs.get("management_average"),
        stage2_start=kwargs.get("stage2_start"),
    )


def rising(sessions: int, start: float = 100.0, step: float = 0.5) -> list[float]:
    return [start + step * index for index in range(sessions)]


class TwoClosesBelowTheManagementAverage(unittest.TestCase):
    def test_two_closes_below_the_21_ema_after_entry_is_a_breach_dated_at_the_second_close(self) -> None:
        # Sixty rising sessions, then two closes well under the average.
        closes = rising(60) + [110.0, 108.0]
        result = evidence(closes)

        trail = result["moving_average_trail"]
        self.assertIsNone(trail["selected"])
        ema = trail["ema21"]
        self.assertEqual(ema["state"], "breached")
        self.assertEqual(ema["breach_date"], frame(closes).index[-1].date().isoformat())
        self.assertEqual(ema["closes_below_in_a_row"], 2)
        self.assertLess(ema["quality"]["close_distance_pct"], 0.0)
        # Open at the close and a symmetric wick leave the close exactly mid-range.
        self.assertEqual(ema["quality"]["closing_range_pct"], 50.0)
        self.assertIs(ema["quality"]["second_close_above_first_close"], False)
        self.assertIs(ema["quality"]["second_close_above_first_low"], False)

    def test_one_close_below_then_a_recovery_is_not_a_breach(self) -> None:
        result = evidence(rising(60) + [110.0, 131.0])

        ema = result["moving_average_trail"]["ema21"]
        self.assertEqual(ema["state"], "clear")
        self.assertIsNone(ema["breach_date"])
        self.assertEqual(ema["closes_below_in_a_row"], 0)
        self.assertIsNone(ema["quality"])

    def test_the_two_closes_must_both_fall_inside_the_position(self) -> None:
        # The first close below lands the session before entry; only the second is the position's.
        closes = rising(40) + [100.0, 99.0] + rising(20, start=130.0)
        result = evidence(closes, entry_offset=41)

        self.assertEqual(result["moving_average_trail"]["ema21"]["state"], "clear")

    def test_a_breach_is_irreversible_within_the_audit_window(self) -> None:
        closes = rising(50) + [100.0, 99.0] + rising(12, start=130.0)
        result = evidence(closes)

        ema = result["moving_average_trail"]["ema21"]
        self.assertEqual(ema["state"], "breached")
        self.assertEqual(ema["breach_date"], frame(closes).index[51].date().isoformat())
        self.assertEqual(ema["closes_below_in_a_row"], 0)

    def test_the_50_sma_needs_fifty_sessions_before_it_can_be_read(self) -> None:
        result = evidence(rising(45) + [100.0, 99.0], entry_offset=30)

        self.assertEqual(result["moving_average_trail"]["sma50"]["state"], "unavailable")
        self.assertEqual(result["moving_average_trail"]["ema21"]["state"], "breached")

    def test_the_selected_average_is_named_back(self) -> None:
        result = evidence(rising(62), entry_offset=50, management_average="sma50")

        self.assertEqual(result["moving_average_trail"]["selected"], "sma50")
        self.assertEqual(result["moving_average_trail"]["sma50"]["state"], "clear")


class TheTwentyDayAverage(unittest.TestCase):
    def test_a_last_close_under_the_20_day_average_is_reported_with_its_distance(self) -> None:
        # Nineteen closes at 100 and one at 81: the average is 99.05 and the close sits 18.2% under it.
        result = evidence([100.0] * 59 + [81.0])

        twenty = result["twenty_day_average"]
        self.assertEqual(twenty["state"], "below")
        self.assertAlmostEqual(twenty["average"], 99.05)
        self.assertAlmostEqual(twenty["close_distance_pct"], (81.0 - 99.05) / 99.05 * 100)

    def test_a_last_close_over_it_is_above(self) -> None:
        self.assertEqual(evidence(rising(60))["twenty_day_average"]["state"], "above")


class TheLargestDeclineSinceTheStageTwoAdvanceBegan(unittest.TestCase):
    def test_without_a_declared_stage_two_start_there_is_nothing_to_measure(self) -> None:
        result = evidence(rising(60))

        self.assertEqual(result["largest_decline_since_stage2_start"], {"state": "unavailable", "reason": "stage2_start_not_declared"})

    def test_the_last_session_is_the_largest_daily_decline_of_the_advance(self) -> None:
        closes = [100.0] * 20 + rising(60, start=100.0, step=1.0) + [147.075]  # 159 -> 147.075 is -7.5%
        volumes = [1_000_000] * 80 + [3_000_000]
        bars = frame(closes, volumes=volumes)
        result = build_management_evidence(bars, entry_date=bars.index[70].date(), as_of=bars.index[-1].date(), management_average=None, stage2_start=bars.index[20].date())

        daily = result["largest_decline_since_stage2_start"]["daily"]
        self.assertAlmostEqual(daily["largest_pct"], -7.5)
        self.assertEqual(daily["date"], bars.index[-1].date().isoformat())
        self.assertIs(daily["last_session_is_largest"], True)
        self.assertAlmostEqual(daily["volume_ratio"], 3.0)
        self.assertEqual(daily["volume_signal"]["role"], "marker")

    def test_an_earlier_larger_decline_means_the_last_session_is_not_it(self) -> None:
        closes = rising(40) + [100.0] + rising(19, start=110.0) + [116.0]  # -1.6% at the end; the drop to 100 earlier was larger
        bars = frame(closes)
        result = build_management_evidence(bars, entry_date=bars.index[45].date(), as_of=bars.index[-1].date(), management_average=None, stage2_start=bars.index[0].date())

        self.assertIs(result["largest_decline_since_stage2_start"]["daily"]["last_session_is_largest"], False)

    def test_the_latest_completed_week_can_be_the_largest_weekly_decline(self) -> None:
        # Ten flat weeks, then a week that closes 8% lower on its Friday.
        closes = [100.0] * 50 + [100.0, 100.0, 100.0, 100.0, 92.0]
        bars = frame(closes)
        result = build_management_evidence(bars, entry_date=bars.index[30].date(), as_of=bars.index[-1].date(), management_average=None, stage2_start=bars.index[0].date())

        weekly = result["largest_decline_since_stage2_start"]["weekly"]
        self.assertAlmostEqual(weekly["largest_pct"], -8.0)
        self.assertIs(weekly["latest_completed_week_is_largest"], True)
        self.assertEqual(weekly["week_ending"], FRIDAY)

    def test_a_week_still_in_progress_is_not_a_completed_weekly_bar(self) -> None:
        closes = [100.0] * 50 + [100.0, 100.0, 100.0, 100.0, 100.0, 92.0]  # the drop lands on the Monday after
        bars = frame(closes, end="2025-12-29")
        result = build_management_evidence(bars, entry_date=bars.index[30].date(), as_of=bars.index[-1].date(), management_average=None, stage2_start=bars.index[0].date())

        weekly = result["largest_decline_since_stage2_start"]["weekly"]
        self.assertIs(weekly["latest_completed_week_is_largest"], False)
        self.assertEqual(weekly["week_ending"], FRIDAY)


if __name__ == "__main__":
    unittest.main()
