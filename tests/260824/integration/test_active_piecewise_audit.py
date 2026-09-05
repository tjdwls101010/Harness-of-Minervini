"""Each protective level is audited from the date it actually became effective."""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot


AS_OF = "2025-12-31"


def price_snapshot(*, dip_date: str | None = None, dip_low: float = 0.0) -> ProviderSnapshot[pd.DataFrame]:
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
    if dip_date is not None:
        frame.loc[frame.loc[dip_date:].index[0], "Low"] = dip_low
    return rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})


class PiecewiseAuditTests(unittest.TestCase):
    def test_a_stop_raised_later_does_not_hide_an_earlier_invalidation_breach(self) -> None:
        # The invalidation was in force from entry; the stop only from November 3.
        snapshot = price_snapshot(dip_date="2025-10-15", dip_low=124.0)
        payload = execute(
            "ticker.risk",
            {
                "ticker": "TEST",
                "mode": "active",
                "entry_price": 100.0,
                "entry_date": "2025-10-01",
                "stop_price": 94.0,
                "stop_effective_date": "2025-11-03",
                "invalidation": {"price": 125.0, "condition": "completed close below the base low"},
                "as_of": AS_OF,
            },
            runtime=Runtime(price_history=lambda ticker, as_of: snapshot),
        )

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "breached")

    def test_each_level_reports_its_own_effective_window(self) -> None:
        snapshot = price_snapshot()
        payload = execute(
            "ticker.risk",
            {
                "ticker": "TEST",
                "mode": "active",
                "entry_price": 100.0,
                "entry_date": "2025-10-01",
                "stop_price": 94.0,
                "stop_effective_date": "2025-11-03",
                "invalidation": {"price": 100.0, "condition": "completed close below the base low"},
                "as_of": AS_OF,
            },
            runtime=Runtime(price_history=lambda ticker, as_of: snapshot),
        )

        audits = {audit["role"]: audit for audit in payload["data"]["completed_price_path"]["audits"]}
        self.assertEqual(audits["invalidation"]["effective_from"], "2025-10-01")
        self.assertEqual(audits["stop"]["effective_from"], "2025-11-03")
        self.assertEqual(payload["data"]["verdict"], "HOLD")

    def test_an_unusable_invalidation_price_is_a_request_error(self) -> None:
        with self.assertRaises(Exception) as raised:
            execute(
                "ticker.risk",
                {
                    "ticker": "TEST",
                    "mode": "active",
                    "entry_price": 100.0,
                    "entry_date": "2025-10-01",
                    "invalidation": {"price": -5.0, "condition": "completed close below the base low"},
                    "as_of": AS_OF,
                },
                runtime=Runtime(price_history=lambda ticker, as_of: price_snapshot()),
            )

        self.assertIn("invalidation_price", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
