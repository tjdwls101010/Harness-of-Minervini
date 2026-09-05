"""Behavior checks for provider contracts yfinance."""

from __future__ import annotations

from datetime import date
import unittest
import pandas as pd
from scripts.minervini.providers import ProviderUnavailable, SnapshotMeta
from scripts.minervini.providers.yfinance import completed_daily_bars
from tests.integration.providers._provider_fixtures import FakeTicker, close_only


class ProviderContractTests(unittest.TestCase):
    def test_yfinance_never_returns_a_partial_or_future_daily_bar(self) -> None:
        index = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17"])
        ticker = FakeTicker(close_only(index, [10.0, 11.0, 12.0, 99.0]))

        snapshot = completed_daily_bars("ACME", as_of="2026-08-14", ticker=ticker)

        self.assertEqual(snapshot.data.index[-1].date().isoformat(), "2026-08-14")
        self.assertEqual(list(snapshot.data["Close"]), [10.0, 11.0, 12.0])
        self.assertEqual(ticker.calls[0]["end"], "2026-08-15")
        self.assertEqual(ticker.calls[0]["start"], "2023-08-10")
        self.assertFalse(ticker.calls[0]["auto_adjust"])
        # Actions on, adjustment still off. The prices stay the ones the tape printed, and the
        # split events come with them: without the events a one-for-two reverse split is
        # indistinguishable from a hundred percent overnight advance.
        self.assertTrue(ticker.calls[0]["actions"])
        # Requested here; whether they arrived is a separate fact this frame does not carry, and
        # coverage reports the frame rather than the request.
        self.assertIs(snapshot.meta.coverage["corporate_actions"], False)
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertIsInstance(snapshot.meta, SnapshotMeta)

    def test_a_blank_corporate_action_cell_is_an_incomplete_row_like_any_other(self) -> None:
        """The measurement boundary refuses a non-finite value in any column it carries.

        Checked here for OHLCV alone, one blank split cell reached that boundary and took the
        whole history down -- for the setup and the chart too, neither of which reads the column.
        """
        index = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14"])
        frame = pd.DataFrame(
            {
                "Open": [10.0, 11.0, 12.0],
                "High": [10.5, 11.5, 12.5],
                "Low": [9.5, 10.5, 11.5],
                "Close": [10.0, 11.0, 12.0],
                "Volume": [100.0, 100.0, 100.0],
                "Stock Splits": [0.0, 0.0, float("nan")],
            },
            index=index,
        )

        snapshot = completed_daily_bars("ACME", as_of="2026-08-14", ticker=FakeTicker(frame))

        self.assertEqual(snapshot.data.index[-1].date().isoformat(), "2026-08-13")

    def test_an_unfinished_final_bar_is_dropped_and_the_session_gap_is_declared(self) -> None:
        index = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-17"])
        frame = pd.DataFrame(
            {
                "Open": [10.0, 11.0, 12.0],
                "High": [10.5, 11.5, 12.5],
                "Low": [9.5, 10.5, 11.5],
                "Close": [10.2, 11.2, float("nan")],
                "Volume": [100, 200, 300],
            },
            index=index,
        )

        snapshot = completed_daily_bars("ACME", as_of="2026-08-17", ticker=FakeTicker(frame))

        self.assertEqual(snapshot.data.index[-1].date().isoformat(), "2026-08-14")
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertTrue(snapshot.meta.stale)
        self.assertEqual(snapshot.meta.coverage["requested_session"], "2026-08-17")
        self.assertEqual(snapshot.meta.coverage["last_completed_bar"], "2026-08-14")

    def test_a_complete_history_through_the_requested_session_is_not_stale(self) -> None:
        index = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-17"])
        frame = close_only(index, [10.2, 11.2, 12.2])

        snapshot = completed_daily_bars("ACME", as_of="2026-08-17", ticker=FakeTicker(frame))

        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 17))
        self.assertFalse(snapshot.meta.stale)

    def test_an_infinite_price_is_not_a_completed_bar(self) -> None:
        index = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-17"])
        frame = close_only(index, [10.2, 11.2, float("inf")])

        snapshot = completed_daily_bars("ACME", as_of="2026-08-17", ticker=FakeTicker(frame))

        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertTrue(snapshot.meta.stale)

    def test_a_repeated_session_never_truncates_the_history_to_the_wrong_bar(self) -> None:
        index = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-14", "2026-08-17"])
        frame = close_only(index, [10.2, 11.2, 11.3, float("nan")])

        snapshot = completed_daily_bars("ACME", as_of="2026-08-17", ticker=FakeTicker(frame))

        self.assertEqual(len(snapshot.data), 3)
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))

    def test_blank_rows_before_a_listing_started_are_trimmed_not_called_a_gap(self) -> None:
        index = pd.to_datetime(["2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"])
        frame = close_only(index, [float("nan"), float("nan"), 11.2, 12.0])

        snapshot = completed_daily_bars("ACME", as_of="2026-08-14", ticker=FakeTicker(frame))

        self.assertEqual(len(snapshot.data), 2)
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertFalse(snapshot.meta.stale)

    def test_a_gap_inside_the_history_is_unavailable_rather_than_silently_compressed(self) -> None:
        index = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14"])
        frame = close_only(index, [10.0, float("nan"), 12.0])

        with self.assertRaises(ProviderUnavailable) as raised:
            completed_daily_bars("ACME", as_of="2026-08-14", ticker=FakeTicker(frame))

        self.assertEqual(raised.exception.reason, "incomplete_daily_bars")


class CoverageReportsWhatTheFrameActuallyCarries(unittest.TestCase):
    """Asking for the events and receiving them are different facts.

    `actions=True` is a request. A feed that answers without the columns leaves a frame that
    cannot say whether a split or a distribution happened, and a coverage flag hardcoded to true
    tells every consumer the opposite.
    """

    def test_a_frame_without_the_event_columns_does_not_claim_them(self) -> None:
        index = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14"])
        frame = pd.DataFrame(
            {
                "Open": [10.0, 11.0, 12.0],
                "High": [10.5, 11.5, 12.5],
                "Low": [9.5, 10.5, 11.5],
                "Close": [10.0, 11.0, 12.0],
                "Volume": [100.0, 100.0, 100.0],
            },
            index=index,
        )

        snapshot = completed_daily_bars("ACME", as_of="2026-08-14", ticker=FakeTicker(frame))

        self.assertIs(snapshot.meta.coverage["corporate_actions"], False)
        self.assertIs(snapshot.meta.coverage["distributions"], False)
