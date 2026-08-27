"""A history that omits its corporate actions has not said there was no split."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-12"


def frame(closes: list[float], *, splits: dict[int, float] | None = None, events: bool = True) -> pd.DataFrame:
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    bars = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=index)
    if events:
        column = np.zeros(len(closes))
        for position, factor in (splits or {}).items():
            column[position] = factor
        bars["Stock Splits"] = column
    return bars


def run(bars: pd.DataFrame, **evidence: object) -> dict:
    snapshot = ProviderSnapshot(bars, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))
    request = {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": "2025-11-03", "stop_price": 94.0, **evidence}
    return execute("ticker.risk", request, runtime=Runtime(price_history=lambda ticker, as_of: snapshot))


def halved(sessions: int = 30, *, at: int = 20) -> list[float]:
    """A two-for-one that the frame may or may not carry the event for."""

    return [100.0] * at + [50.0] * (sessions - at)


class ATwoForOneWithNoEventColumn(unittest.TestCase):
    def test_the_apparent_fall_does_not_sell_the_position(self) -> None:
        payload = run(frame(halved(), events=False))

        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["state"], "unavailable")
        self.assertEqual(path["reason"], "corporate_action_evidence_missing")
        self.assertIsNone(payload["data"]["current_price"])

    def test_the_same_history_with_the_event_column_and_no_split_does_sell(self) -> None:
        # The column present and zero is evidence: nothing changed the share count, so the
        # fall is the tape and the stop it took out is a real one.
        payload = run(frame(halved()))

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "breached")

    def test_the_declared_split_is_still_named_as_a_split(self) -> None:
        payload = run(frame(halved(), splits={20: 2.0}))

        self.assertEqual(payload["data"]["completed_price_path"]["reason"], "share_split_inside_stop_window")


class TheExcursionAsksTheSameQuestion(unittest.TestCase):
    def test_a_declared_split_withholds_the_highest_high(self) -> None:
        # A three-for-one leaves the pre-split highs three times the post-split entry, and
        # three R measured across it raises a stop on a gain the position never had.
        doubled = [100.0] * 20 + [300.0] * 5 + [100.0] * 5
        payload = run(frame(doubled, splits={25: 3.0}), stop_price=80.0)

        data = payload["data"]
        self.assertIsNone(data["max_high_since_entry"])
        self.assertEqual(data["max_high_withheld_reason"], "share_split_inside_excursion_window")

    def test_the_same_jump_without_the_event_column_is_withheld_too(self) -> None:
        doubled = [100.0] * 20 + [300.0] * 5 + [100.0] * 5
        payload = run(frame(doubled, events=False), stop_price=80.0)

        self.assertEqual(payload["data"]["max_high_withheld_reason"], "corporate_action_evidence_missing_inside_excursion_window")


class ARepeatedSessionIsNotADiscontinuity(unittest.TestCase):
    def test_a_superseded_print_does_not_withhold_the_highest_high(self) -> None:
        # The morning print and the closing print of one session are one session's two
        # prices, not two sessions a third of the way apart. The stop audit deduplicates
        # before it looks, and the excursion has to reach the same reading of the frame.
        index = pd.bdate_range(end=AS_OF, periods=10).tolist()
        index[-1] = pd.Timestamp(f"{index[-1].date()} 16:00")
        index.insert(len(index) - 1, pd.Timestamp(f"{index[-1].date()} 09:30"))
        closes = [100.0] * 9 + [70.0, 105.0]
        close = pd.Series(closes, index=pd.DatetimeIndex(index), dtype=float)
        bars = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=close.index)
        payload = run(bars, entry_date=close.index[0].date().isoformat())

        data = payload["data"]
        self.assertIsNone(data["max_high_withheld_reason"])
        self.assertAlmostEqual(data["max_high_since_entry"], 106.05)
        self.assertEqual(data["completed_price_path"]["state"], "clear")


class TheMeasurementsRefuseTheSameWindow(unittest.TestCase):
    def test_the_management_average_does_not_read_two_coordinate_systems(self) -> None:
        bars = frame(halved(60, at=40), events=False)
        result = build_management_evidence(bars, entry_date=bars.index[35].date(), as_of=bars.index[-1].date(), management_average="sma50")

        block = result["moving_average_trail"]
        self.assertEqual(block["state"], "unavailable")
        self.assertEqual(block["reason"], "corporate_action_evidence_missing")
        self.assertEqual(block["date"], bars.index[40].date().isoformat())

    def test_a_move_smaller_than_the_smallest_ordinary_split_is_a_move(self) -> None:
        # Five-for-four is the smallest split the harness recognizes, so a nineteen percent
        # session is read as the market moving, not as a share count changing.
        bars = frame([100.0] * 40 + [81.0] * 20, events=False)
        result = build_management_evidence(bars, entry_date=bars.index[35].date(), as_of=bars.index[-1].date(), management_average="ema21")

        self.assertEqual(result["moving_average_trail"]["ema21"]["state"], "breached")


class WhichEventFactorsCountAsSplits(unittest.TestCase):
    """The event column carries a factor, and not every factor is a share count changing."""

    def test_a_reverse_split_is_refused_the_same_way_a_forward_one_is(self) -> None:
        # One-for-ten multiplies the printed price by ten. The arithmetic across it is as
        # wrong as a two-for-one's, and in the direction that invents a gain.
        tenfold = [10.0] * 20 + [100.0] * 10
        payload = run(frame(tenfold, splits={20: 0.1}), stop_price=8.0, entry_price=10.0)

        self.assertEqual(payload["data"]["completed_price_path"]["reason"], "share_split_inside_stop_window")
        self.assertEqual(payload["data"]["max_high_withheld_reason"], "share_split_inside_excursion_window")

    def test_a_factor_of_one_changed_no_share_count(self) -> None:
        # Providers stamp 1.0 on a session where an event was recorded but the ratio was
        # one for one. Nothing moved between coordinate systems, so nothing is refused.
        payload = run(frame([100.0] * 30, splits={20: 1.0}))

        self.assertEqual(payload["data"]["completed_price_path"]["state"], "clear")
        self.assertEqual(payload["data"]["verdict"], "HOLD")

    def test_a_split_before_the_position_started_is_not_in_its_window(self) -> None:
        # The audit runs from the entry session. An event two weeks before it is in a
        # window this position never had, and refusing on it would withhold a live verdict.
        bars = frame([50.0] * 10 + [100.0] * 20, splits={10: 0.5})
        payload = run(bars, entry_date=bars.index[15].date().isoformat())

        self.assertEqual(payload["data"]["completed_price_path"]["state"], "clear")
        self.assertEqual(payload["data"]["max_high_since_entry"], 101.0)

    def test_a_split_on_the_entry_session_is_inside_the_stop_window_and_not_the_excursion(self) -> None:
        # The two windows begin one session apart on purpose, and the boundary is where
        # that shows: the stop audit reads the entry session, the excursion starts after it.
        bars = frame([100.0] * 15 + [50.0] * 15, splits={15: 2.0})
        payload = run(bars, entry_date=bars.index[15].date().isoformat())

        self.assertEqual(payload["data"]["completed_price_path"]["reason"], "share_split_inside_stop_window")
        self.assertIsNone(payload["data"]["max_high_withheld_reason"])

    def test_a_split_on_the_as_of_session_is_still_inside_both_windows(self) -> None:
        bars = frame([100.0] * 29 + [50.0], splits={29: 2.0})
        payload = run(bars)

        self.assertEqual(payload["data"]["completed_price_path"]["reason"], "share_split_inside_stop_window")
        self.assertEqual(payload["data"]["max_high_withheld_reason"], "share_split_inside_excursion_window")


if __name__ == "__main__":
    unittest.main()
