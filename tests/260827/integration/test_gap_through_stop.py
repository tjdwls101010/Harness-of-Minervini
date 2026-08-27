"""A stop the market opened below was never available at its price, and the record says so."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "stop_price": 94.0, "as_of": AS_OF}


def bars(rows: list[tuple[float, float, float, float]]) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(end=AS_OF, periods=len(rows))
    frame = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    frame["Volume"] = np.full(len(frame), 1_000_000)
    return ProviderSnapshot(frame, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))


def quiet(sessions: int) -> list[tuple[float, float, float, float]]:
    return [(101.0, 102.0, 99.5, 101.0)] * sessions


class GapThroughTheStop(unittest.TestCase):
    def run_risk(self, rows: list[tuple[float, float, float, float]]) -> dict:
        return execute("ticker.risk", POSITION, runtime=Runtime(price_history=lambda ticker, as_of: bars(rows)))

    def test_a_session_that_opens_below_the_stop_is_recorded_as_a_gap_through(self) -> None:
        payload = self.run_risk(quiet(20) + [(90.0, 92.0, 88.0, 91.0)] + quiet(2))

        path = payload["data"]["completed_price_path"]
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(path["state"], "breached")
        self.assertIs(path["gap_through_stop"], True)
        self.assertEqual(path["breach_open"], 90.0)
        self.assertEqual(path["breach_low"], 88.0)

    def test_a_session_that_trades_down_through_the_stop_is_not_a_gap(self) -> None:
        payload = self.run_risk(quiet(20) + [(96.0, 97.0, 93.0, 95.0)] + quiet(2))

        path = payload["data"]["completed_price_path"]
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertIs(path["gap_through_stop"], False)
        self.assertEqual(path["breach_open"], 96.0)

    def test_the_gap_reading_travels_with_the_level_it_breached(self) -> None:
        request = {**POSITION, "invalidation": {"price": 97.0, "condition": "completed close below the base low"}}
        payload = execute("ticker.risk", request, runtime=Runtime(price_history=lambda ticker, as_of: bars(quiet(20) + [(96.0, 97.0, 95.0, 96.0)] + quiet(2))))

        path = payload["data"]["completed_price_path"]
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertIs(path["gap_through_stop"], True)
        by_role = {audit["role"]: audit for audit in path["audits"]}
        self.assertEqual(by_role["invalidation"]["state"], "breached")
        self.assertIs(by_role["invalidation"]["gap_through_stop"], True)
        self.assertEqual(by_role["stop"]["state"], "clear")
        self.assertNotIn("gap_through_stop", by_role["stop"])


if __name__ == "__main__":
    unittest.main()
