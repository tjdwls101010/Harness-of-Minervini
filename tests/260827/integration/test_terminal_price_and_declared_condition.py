"""A price handed in says one thing about today; the history says what already happened.

Two findings live here. A terminal price at ``as_of`` is the latest date any exit can carry,
so it can never name the failure over an exit the bars already printed. And a structural
invalidation is a statement about where a session finished -- auditing it intraday sells a
position on a poke the declared condition never called an exit.
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


def frame(rows: dict[str, tuple[float, float, float, float]]) -> ProviderSnapshot[pd.DataFrame]:
    index = pd.bdate_range(start="2025-11-03", end=AS_OF)
    built = [rows.get(stamp.date().isoformat(), (100.0, 101.0, 99.0, 100.0)) for stamp in index]
    data = pd.DataFrame(built, columns=["Open", "High", "Low", "Close"], index=index, dtype=float)
    data["Volume"] = np.full(len(data), 1_000_000)
    data["Stock Splits"] = np.zeros(len(data))
    return ProviderSnapshot(data, SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))


def run(rows: dict[str, tuple[float, float, float, float]], **request) -> dict:
    calls: list[str] = []

    def history(ticker: str, as_of: str):
        calls.append(ticker)
        return frame(rows)

    payload = execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=history))
    payload["_calls"] = calls
    return payload


class AnExplicitPriceCannotOutrankAnEarlierExit(unittest.TestCase):
    def test_a_terminal_price_today_does_not_hide_an_invalidation_the_bars_already_broke(self) -> None:
        payload = run(
            {"2025-12-10": (100.0, 101.0, 89.0, 89.5), AS_OF: (96.0, 97.0, 93.0, 94.0)},
            stop_price=95.0,
            stop_effective_date="2025-12-20",
            invalidation={"price": 90.0},
            current_price=94.0,
        )

        self.assertEqual(payload["_calls"], ["TEST"])
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["failed"], ["invalidation_breach"])
        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["governing_role"], "invalidation")
        self.assertEqual(path["breach_date"], "2025-12-10")
        self.assertEqual(path["checked_level"], 90.0)

    def test_a_terminal_price_still_sells_when_the_bars_never_arrive(self) -> None:
        def refuse(ticker: str, as_of: str):
            raise ProviderUnavailable(provider="fixture-prices", reason="unavailable", retryable=False)

        payload = execute(
            "ticker.risk",
            {**POSITION, "stop_price": 95.0, "current_price": 94.0},
            runtime=Runtime(price_history=refuse),
        )

        self.assertEqual(payload["data"]["verdict"], "SELL")
        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["state"], "breached")
        self.assertEqual(path["basis"], "explicit_completed_price")

    def test_a_terminal_price_breach_is_not_reported_as_an_asserted_one(self) -> None:
        def refuse(ticker: str, as_of: str):
            raise ProviderUnavailable(provider="fixture-prices", reason="unavailable", retryable=False)

        payload = execute(
            "ticker.risk",
            {**POSITION, "stop_price": 95.0, "current_price": 94.0},
            runtime=Runtime(price_history=refuse),
        )

        trail = payload["data"]["management_evidence"]["moving_average_trail"]
        self.assertNotEqual(trail.get("reason"), "price_history_not_fetched_after_asserted_breach")


class AnInvalidationIsAboutWhereTheSessionFinished(unittest.TestCase):
    def test_a_low_under_the_level_that_closed_above_it_is_not_an_invalidation_breach(self) -> None:
        payload = run(
            {"2025-12-10": (100.0, 101.0, 94.0, 98.0)},
            stop_price=90.0,
            invalidation={"price": 95.0, "condition": "completed close below 95"},
        )

        self.assertNotIn("invalidation_breach", payload["data"]["failed"])
        audits = {audit["role"]: audit for audit in payload["data"]["completed_price_path"]["audits"]}
        self.assertEqual(audits["invalidation"]["state"], "clear")
        self.assertEqual(audits["invalidation"]["basis"], "completed_daily_close")

    def test_a_close_under_the_level_is_the_invalidation_breach(self) -> None:
        payload = run(
            {"2025-12-10": (100.0, 101.0, 94.0, 94.5)},
            stop_price=90.0,
            invalidation={"price": 95.0, "condition": "completed close below 95"},
        )

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["failed"], ["invalidation_breach"])
        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["basis"], "completed_daily_close")
        self.assertEqual(path["breach_close"], 94.5)
        self.assertEqual(path["breach_date"], "2025-12-10")

    def test_the_hard_stop_is_still_taken_out_intraday(self) -> None:
        payload = run(
            {"2025-12-10": (100.0, 101.0, 89.0, 98.0)},
            stop_price=90.0,
        )

        self.assertEqual(payload["data"]["verdict"], "SELL")
        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["basis"], "completed_daily_low")
        self.assertEqual(path["breach_low"], 89.0)


if __name__ == "__main__":
    unittest.main()
