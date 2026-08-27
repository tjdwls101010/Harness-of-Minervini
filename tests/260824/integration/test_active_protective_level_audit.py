"""The completed-price audit must cover whichever protective level is crossed first."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-10-01", "as_of": AS_OF}


def price_snapshot() -> ProviderSnapshot[pd.DataFrame]:
    values = np.linspace(50, 150, 260)
    index = pd.bdate_range(end=AS_OF, periods=len(values))
    close = pd.Series(values, index=index)
    frame = pd.DataFrame(
        {
            "Open": close * 0.995,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000),
        },
        index=index,
    )
    return ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date.fromisoformat(AS_OF),
            coverage={"completed_only": True},
        ),
    )


def run(**request: object) -> dict:
    return execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=lambda ticker, as_of: price_snapshot()))


class ProtectiveLevelAuditTests(unittest.TestCase):
    def test_the_audit_level_is_the_tighter_of_the_stop_and_the_invalidation(self) -> None:
        # Every completed low from the entry date onward sits above 94 but below 130, so
        # the verdict flips only when the audit uses the tighter invalidation level.
        payload = run(stop_price=94.0, invalidation={"price": 130.0, "condition": "completed close below the base low"})

        self.assertEqual(payload["data"]["completed_price_path"]["checked_level"], 130.0)
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "breached")
        self.assertEqual(payload["data"]["verdict"], "SELL")

    def test_an_invalidation_only_position_still_gets_an_audited_path(self) -> None:
        payload = run(invalidation={"price": 94.0, "condition": "completed close below the base low"})

        self.assertEqual(payload["data"]["completed_price_path"]["checked_level"], 94.0)
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "clear")
        self.assertEqual(payload["data"]["verdict"], "HOLD")

    def test_a_stop_tighter_than_the_invalidation_remains_the_audit_level(self) -> None:
        # Below the entry price, because a stop in force from the entry session that sits at
        # or above it leaves the trade no risk for the stop to bound.
        payload = run(stop_price=96.0, invalidation={"price": 94.0, "condition": "completed close below the base low"})

        self.assertEqual(payload["data"]["completed_price_path"]["checked_level"], 96.0)


if __name__ == "__main__":
    unittest.main()
