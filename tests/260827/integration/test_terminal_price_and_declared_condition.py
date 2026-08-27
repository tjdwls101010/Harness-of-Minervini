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

    def test_the_bars_own_a_level_they_broke_first_even_when_the_price_crosses_it_too(self) -> None:
        payload = run(
            {"2025-12-10": (100.0, 101.0, 89.0, 100.0), AS_OF: (96.0, 97.0, 93.0, 94.0)},
            stop_price=95.0,
            current_price=94.0,
        )

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["breach_date"], "2025-12-10")
        self.assertEqual(path["basis"], "completed_daily_low")

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


class WithNoBarsThePriceIsTheWholeRecord(unittest.TestCase):
    """What one price can and cannot say, when nothing else is available to say it."""

    def refused(self, **request) -> dict:
        def refuse(ticker: str, as_of: str):
            raise ProviderUnavailable(provider="fixture-prices", reason="unavailable", retryable=False)

        return execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=refuse))

    def test_a_level_under_the_price_is_unaudited_rather_than_clear(self) -> None:
        payload = self.refused(stop_price=90.0, invalidation={"price": 95.0}, current_price=94.0)

        audits = {audit["role"]: audit for audit in payload["data"]["completed_price_path"]["audits"]}
        self.assertEqual(audits["stop"]["state"], "unavailable")
        self.assertEqual(audits["stop"]["reason"], "not_audited_after_explicit_breach")

    def test_the_record_is_about_the_level_the_price_crossed_first(self) -> None:
        # Two levels, one price under both. The stop is a resting order, so a close that low
        # means the session already filled it; the invalidation is read from the close.
        payload = self.refused(stop_price=90.0, invalidation={"price": 95.0}, current_price=88.0)

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["governing_role"], "stop")
        self.assertEqual(path["checked_level"], 90.0)
        self.assertEqual(payload["data"]["failed"], ["completed_stop_breach"])

    def test_a_price_exactly_at_the_invalidation_crosses_nothing_at_all(self) -> None:
        # With no bars to fall back on, whether the price crossed anything is the whole
        # question. A threshold stopped exactly on has not been gone below, so there is no
        # record here and the position is unresolved rather than sold.
        payload = self.refused(stop_price=90.0, invalidation={"price": 95.0}, current_price=95.0)

        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertEqual(payload["data"]["failed"], [])

    def test_two_close_read_levels_are_named_by_the_higher(self) -> None:
        payload = self.refused(stop_price=80.0, invalidation={"price": 95.0}, current_price=88.0)

        path = payload["data"]["completed_price_path"]
        self.assertEqual(path["governing_role"], "invalidation")
        self.assertEqual(path["checked_level"], 95.0)


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
