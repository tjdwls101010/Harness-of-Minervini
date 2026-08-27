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


class AnEventCannotUndoWhatTheMarketAlreadyDid(unittest.TestCase):
    """A breach found before the event stands; the refusal begins at the event."""

    def rows(self, closes: list[tuple[float, float, float]]) -> pd.DataFrame:
        index = pd.bdate_range(end=AS_OF, periods=len(closes))
        frame = pd.DataFrame(
            {
                "Open": [row[0] for row in closes],
                "High": [row[2] * 1.01 for row in closes],
                "Low": [row[1] for row in closes],
                "Close": [row[2] for row in closes],
                "Volume": np.full(len(closes), 1_000_000),
            },
            index=index,
        )
        return frame

    def test_a_breach_before_the_discontinuity_still_sells(self) -> None:
        # The stop was taken out on the second session, in the trader's own coordinate
        # system, and the third session is a jump the history cannot explain. An event two
        # days later cannot un-take-out a stop the market took out.
        bars = self.rows([(100.0, 99.0, 100.0), (95.0, 89.0, 95.0), (76.0, 75.0, 76.0)])
        payload = run(bars, entry_date=bars.index[0].date().isoformat(), stop_price=90.0)

        data = payload["data"]
        self.assertEqual(data["verdict"], "SELL")
        path = data["completed_price_path"]
        self.assertEqual(path["state"], "breached")
        self.assertEqual(path["breach_date"], bars.index[1].date().isoformat())
        self.assertEqual(path["through"], bars.index[1].date().isoformat())
        self.assertAlmostEqual(path["breach_low"], 89.0)
        self.assertEqual(path["bars_checked"], 2)

    def test_the_refusal_names_the_sessions_it_did_read(self) -> None:
        # The audit ran to the event and those bars came through clear. A refusal that names
        # no bars reads as a window nothing was read in, which is not what happened.
        bars = self.rows([(100.0, 99.0, 100.0), (100.0, 99.0, 100.0), (50.0, 49.0, 50.0), (50.0, 49.0, 50.0)])
        payload = run(bars, entry_date=bars.index[0].date().isoformat(), stop_price=90.0)

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["state"], "unavailable")
        self.assertEqual(path["first_bar_checked"], bars.index[0].date().isoformat())
        self.assertEqual(path["last_bar_checked"], bars.index[1].date().isoformat())
        self.assertEqual(path["bars_checked"], 2)

    def test_no_breach_before_it_still_refuses_the_window(self) -> None:
        bars = self.rows([(100.0, 99.0, 100.0), (100.0, 99.0, 100.0), (76.0, 75.0, 76.0)])
        payload = run(bars, entry_date=bars.index[0].date().isoformat(), stop_price=90.0)

        data = payload["data"]
        self.assertEqual(data["verdict"], "INCOMPLETE")
        path = data["completed_price_path"]
        self.assertEqual(path["state"], "unavailable")
        self.assertEqual(path["reason"], "corporate_action_evidence_missing")
        self.assertEqual(path["date"], bars.index[2].date().isoformat())
        self.assertIsNone(data["current_price"])


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

    def test_a_declared_exit_triggered_before_the_split_still_sells(self) -> None:
        # Two closes below the declared average happened in the trader's own coordinate
        # system, so the position was closed then. A two-for-one three weeks later cannot
        # un-trigger the exit plan the trader declared.
        closes = [100.0] * 55 + [95.0, 95.0] + [100.0] * 3 + [50.0] * 20
        bars = frame(closes, splits={60: 2.0})
        result = build_management_evidence(bars, entry_date=bars.index[50].date(), as_of=bars.index[-1].date(), management_average="ema21")

        trail = result["moving_average_trail"]["ema21"]
        self.assertEqual(trail["state"], "breached")
        self.assertEqual(trail["breach_date"], bars.index[56].date().isoformat())

    def test_nothing_found_before_the_split_still_refuses_the_window(self) -> None:
        closes = [100.0] * 60 + [50.0] * 20
        bars = frame(closes, splits={60: 2.0})
        result = build_management_evidence(bars, entry_date=bars.index[50].date(), as_of=bars.index[-1].date(), management_average="ema21")

        self.assertEqual(result["moving_average_trail"]["reason"], "share_split_inside_window")

    def test_a_split_before_the_simple_average_s_window_does_not_void_it(self) -> None:
        # The split is a hundred sessions before the position and fifty before the first
        # value the SMA uses, so no average this audit reads spans it. Withholding it would
        # turn a readable HOLD into INCOMPLETE over an event outside every window in use.
        bars = frame([50.0] * 20 + [100.0] * 100, splits={20: 2.0})
        result = build_management_evidence(bars, entry_date=bars.index[100].date(), as_of=bars.index[-1].date(), management_average="sma50")

        trail = result["moving_average_trail"]
        self.assertEqual(trail["sma50"]["state"], "clear")
        # The recursive average runs from the first bar, so it does span the event.
        self.assertEqual(trail["ema21"]["reason"], "share_split_inside_window")

    def test_a_split_inside_the_simple_average_s_window_still_voids_the_block(self) -> None:
        bars = frame([50.0] * 80 + [100.0] * 40, splits={80: 2.0})
        result = build_management_evidence(bars, entry_date=bars.index[100].date(), as_of=bars.index[-1].date(), management_average="sma50")

        self.assertEqual(result["moving_average_trail"]["reason"], "share_split_inside_window")

    def test_the_bound_is_read_at_both_split_ratios_and_just_inside_them(self) -> None:
        # Five-for-four is the smallest split the harness recognizes, so a close at exactly
        # 80% or 125% of the one before it is split-sized and a hair inside either is a move.
        for factor, refused in ((0.8, True), (0.800001, False), (1.25, True), (1.249999, False)):
            with self.subTest(factor=factor):
                bars = frame([100.0] * 20 + [100.0 * factor] * 10, events=False)
                result = build_management_evidence(bars, entry_date=bars.index[15].date(), as_of=bars.index[-1].date(), management_average="ema21")

                block = result["moving_average_trail"]
                if refused:
                    self.assertEqual(block["reason"], "corporate_action_evidence_missing")
                    self.assertEqual(block["date"], bars.index[20].date().isoformat())
                else:
                    self.assertIn("ema21", block)

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
