"""An assertion says the position ended; the bars say when, and at which line.

Fetching the history for a verdict that is already settled looks wasteful until the bars
hold an exit that happened first. Then the record the caller reads names the wrong level on
the wrong day. The bars are consulted; their absence cannot downgrade a verdict that never
needed them.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "as_of": AS_OF}


def frame(rows: dict[str, tuple[float, float, float, float]], *, start: str = "2025-11-03", end: str = AS_OF) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(start=start, end=end)
    built = [rows.get(stamp.date().isoformat(), (100.0, 101.0, 99.0, 100.0)) for stamp in index]
    data = pd.DataFrame(built, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    data["Volume"] = np.full(len(data), 1_000_000)
    data["Stock Splits"] = np.zeros(len(data))
    return ProviderSnapshot(data, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(end), coverage={"completed_only": True}))


def run(rows: dict[str, tuple[float, float, float, float]], **request) -> dict:
    calls: list[str] = []

    def history(ticker: str, as_of: str):
        calls.append(ticker)
        return frame(rows)

    payload = execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=history))
    payload["_calls"] = calls
    return payload


LIVE = {"live_stop_check": True, "live_stop": {"state": "triggered", "partial_session": True}}


class TheBarsAreStillRead(unittest.TestCase):
    def test_a_live_assertion_does_not_hide_an_exit_the_bars_already_printed(self) -> None:
        payload = run(
            {"2025-12-23": (100.0, 101.0, 95.0, 96.0)},
            stop_price=94.0,
            invalidation={"price": 97.0, "condition": "completed close below base low"},
            **LIVE,
        )

        self.assertEqual(payload["_calls"], ["TEST"])
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["failed"], ["invalidation_breach"])
        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["governing_role"], "invalidation")
        self.assertEqual(path["breach_date"], "2025-12-23")
        self.assertEqual(path["breach_close"], 96.0)

    def test_a_live_assertion_with_nothing_earlier_still_names_itself(self) -> None:
        payload = run({}, stop_price=94.0, **LIVE)

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["failed"], ["live_stop_breach"])

    def test_bars_that_never_arrive_cannot_downgrade_a_settled_sell(self) -> None:
        def refuse(ticker: str, as_of: str):
            raise ProviderUnavailable(provider="fixture-prices", reason="unavailable", retryable=False)

        payload = execute("ticker.risk", {**POSITION, "stop_price": 94.0, **LIVE}, runtime=Runtime(price_history=refuse))

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["management_evidence"]["moving_average_trail"]["reason"], "price_history_unavailable")

    def test_a_supplied_price_path_is_the_record_and_is_not_re_derived(self) -> None:
        payload = run({}, stop_price=94.0, completed_price_path={"state": "breached"})

        self.assertEqual(payload["_calls"], [])
        self.assertEqual(payload["data"]["verdict"], "SELL")


class AnActionMustBePlaceableAndMeasured(unittest.TestCase):
    def test_the_tl_breakeven_stop_is_not_ordered_above_the_last_price(self) -> None:
        payload = run(
            {"2025-12-30": (100.0, 106.0, 98.0, 105.0), AS_OF: (100.0, 100.0, 98.0, 99.0)},
            stop_price=94.0,
            management_profile="tl_stage12",
        )

        actions = payload["data"]["management_actions"]
        self.assertEqual([action["action"] for action in actions if action["action"] == "RAISE_STOP"], [])
        self.assertIn("REDUCE", [action["action"] for action in actions])
        self.assertEqual(payload["data"]["risk_controls"]["breakeven_protection_not_placeable"]["reason"], "breakeven_is_above_the_current_price")

    def test_a_heavier_down_session_is_reported_as_the_comparison_it_is(self) -> None:
        index = pd.bdate_range(start="2025-09-01", end=AS_OF)
        rows: dict[str, tuple[float, float, float, float]] = {}
        breakout = "2025-12-15"
        rows[breakout] = (100.0, 106.0, 99.0, 105.0)
        rows["2025-12-16"] = (105.0, 105.0, 100.0, 101.0)

        def history(ticker: str, as_of: str):
            built = [rows.get(stamp.date().isoformat(), (100.0, 101.0, 99.0, 100.0)) for stamp in index]
            data = pd.DataFrame(built, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
            volumes = np.full(len(data), 1_000_000.0)
            volumes[list(index).index(pd.Timestamp(breakout))] = 2_000_000.0
            volumes[list(index).index(pd.Timestamp("2025-12-16"))] = 2_100_000.0
            data["Volume"] = volumes
            data["Stock Splits"] = np.zeros(len(data))
            return ProviderSnapshot(data, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))

        payload = execute(
            "ticker.risk",
            {**POSITION, "entry_price": 105.0, "entry_date": breakout, "stop_price": 94.0, "breakout_date": breakout},
            runtime=Runtime(price_history=history),
        )

        review = next(action for action in payload["data"]["management_actions"] if action.get("reason", "").startswith("selling_volume"))
        self.assertEqual(review["action"], "REVIEW")
        self.assertEqual(review["reason"], "selling_volume_exceeded_breakout_volume")
        self.assertNotIn("reduce_or_sell", review)
        self.assertEqual(review["evidence"]["resolved_by_bars"], False)


if __name__ == "__main__":
    unittest.main()
