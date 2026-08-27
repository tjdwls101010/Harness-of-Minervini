"""The plan's golden case, end to end: the stop never touched, the structure gone bad."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-11-03", "stop_price": 90.0, "as_of": AS_OF}


def bars(closes: list[float]) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=index)
    return ProviderSnapshot(frame, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))


def deteriorating() -> list[float]:
    """A long rise to ~130, then a slide to 96: under the 21 EMA and the 20-day, above the stop at 90."""

    return list(np.linspace(80.0, 130.0, 120)) + list(np.linspace(129.0, 96.0, 12))


class StopUntouchedStructureDeteriorating(unittest.TestCase):
    def test_the_position_is_held_with_review_actions_not_a_bare_hold(self) -> None:
        payload = execute("ticker.risk", POSITION, runtime=Runtime(price_history=lambda ticker, as_of: bars(deteriorating())))

        data = payload["data"]
        self.assertEqual(data["verdict"], "HOLD")
        self.assertEqual(data["completed_price_path"]["state"], "clear")
        reasons = [action.get("reason") for action in data["management_actions"]]
        self.assertIn("two_closes_below_ema21", reasons)
        self.assertIn("close_below_20_day_average", reasons)
        self.assertEqual(data["management_evidence"]["moving_average_trail"]["ema21"]["state"], "breached")
        self.assertIn("management.ema21_sma50_roles", payload["doctrine_ids"])

    def test_with_the_ema_declared_as_the_exit_plan_the_same_bars_sell(self) -> None:
        payload = execute("ticker.risk", {**POSITION, "management_average": "ema21"}, runtime=Runtime(price_history=lambda ticker, as_of: bars(deteriorating())))

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["failed"], ["management_average_exit"])
        self.assertEqual(payload["status"], "ok")

    def test_a_healthy_position_carries_the_measurements_and_no_actions(self) -> None:
        payload = execute("ticker.risk", POSITION, runtime=Runtime(price_history=lambda ticker, as_of: bars(list(np.linspace(80.0, 130.0, 132)))))

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        # The run reached three R, so protection is due; nothing structural is.
        self.assertEqual([action["action"] for action in payload["data"]["management_actions"]], ["RAISE_STOP"])
        self.assertEqual(payload["data"]["management_evidence"]["twenty_day_average"]["state"], "above")
        self.assertEqual(payload["data"]["management_evidence"]["moving_average_trail"]["ema21"]["state"], "clear")


if __name__ == "__main__":
    unittest.main()
