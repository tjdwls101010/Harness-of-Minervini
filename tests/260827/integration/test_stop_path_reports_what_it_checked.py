"""What the stop audit says it checked must be what it checked."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-05"


def snapshot(bars: pd.DataFrame) -> ProviderSnapshot[pd.DataFrame]:
    return ProviderSnapshot(bars, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))


def frame(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(stamp) for stamp, _, _ in rows])
    # The provider always hands the event column over; a frame without it says something
    # different, and the histories that omit it have their own tests.
    return pd.DataFrame({"Open": [close for _, _, close in rows], "High": [close * 1.01 for _, _, close in rows], "Low": [low for _, low, _ in rows], "Close": [close for _, _, close in rows], "Volume": [1_000_000] * len(rows), "Stock Splits": [0.0] * len(rows)}, index=index)


def run(bars: pd.DataFrame, **evidence: object) -> dict:
    request = {"ticker": "TEST", "mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": "2025-12-01", "stop_price": 94.0, **evidence}
    return execute("ticker.risk", request, runtime=Runtime(price_history=lambda ticker, as_of: snapshot(bars)))


class ASessionPrintedTwice(unittest.TestCase):
    """The same session at two timestamps is one session, and the later print is the one that stands."""

    def test_a_superseded_intraday_low_does_not_sell_the_position(self) -> None:
        bars = frame([
            ("2025-12-01", 99.0, 100.0),
            ("2025-12-02", 99.0, 100.0),
            ("2025-12-03 00:00", 80.0, 100.0),
            ("2025-12-03 16:00", 99.0, 100.0),
            ("2025-12-04", 99.0, 100.0),
            ("2025-12-05", 99.0, 100.0),
        ])
        payload = run(bars)

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["state"], "clear")
        self.assertEqual(path["bars_checked"], 5)


class ABreachEndsTheWindow(unittest.TestCase):
    def test_the_record_stops_where_the_audit_stopped(self) -> None:
        bars = frame([
            ("2025-12-01", 99.0, 100.0),
            ("2025-12-02", 99.0, 100.0),
            ("2025-12-03", 93.0, 95.0),
            ("2025-12-04", 99.0, 100.0),
            ("2025-12-05", 99.0, 100.0),
        ])
        payload = run(bars)

        path = payload["data"]["completed_price_path"]
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(path["state"], "breached")
        self.assertEqual(path["breach_date"], "2025-12-03")
        self.assertEqual(path["through"], "2025-12-03")
        self.assertEqual(path["bars_checked"], 3)


class TheWindowNamesTheBarsThatSpoke(unittest.TestCase):
    """A requested window is a date the caller named; the record says which bars answered."""

    def test_a_clear_audit_names_its_first_and_last_bar(self) -> None:
        bars = frame([
            ("2025-11-28", 99.0, 100.0),
            ("2025-12-01", 99.0, 100.0),
            ("2025-12-02", 99.0, 100.0),
            ("2025-12-03", 99.0, 100.0),
            ("2025-12-04", 99.0, 100.0),
            ("2025-12-05", 99.0, 100.0),
        ])
        payload = run(bars)

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["from"], "2025-12-01")
        self.assertEqual(path["first_bar_checked"], "2025-12-01")
        self.assertEqual(path["last_bar_checked"], "2025-12-05")
        self.assertEqual(path["bars_checked"], 5)
        # The bar before entry exists and was deliberately not audited: the position did not.
        self.assertEqual(payload["data"]["verdict"], "HOLD")


if __name__ == "__main__":
    unittest.main()


class TheFurthestTheTradeGot(unittest.TestCase):
    """The favorable excursion reads the same bar the stop audit reads."""

    def test_an_out_of_order_repeated_session_is_resolved_by_date_not_by_row_order(self) -> None:
        # The session's later print comes first in row order, so keeping the last row
        # rather than the last session picks the print the market superseded.
        rows = [
            ("2025-12-01", 99.0, 100.0),
            ("2025-12-02", 99.0, 100.0),
            ("2025-12-03", 99.0, 100.0),
            ("2025-12-04", 99.0, 100.0),
            ("2025-12-05 16:00", 99.0, 130.0),
            ("2025-12-05 09:30", 99.0, 105.0),
        ]
        payload = run(frame(rows))

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertAlmostEqual(payload["data"]["max_high_since_entry"], 131.3)
        self.assertEqual(payload["data"]["max_high_date"], "2025-12-05")
