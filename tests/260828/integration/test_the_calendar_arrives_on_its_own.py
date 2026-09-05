"""The coming report, fetched rather than typed -- and only when the question is about today.

Two claims already read a held position's next earnings date, and both could only fire when a
caller happened to type one. The harness can look it up, so it does: an unstated date is a gap
in what the analyst typed, not a gap in what is knowable.

What it must never do is date today's calendar to a past session. A forecast is not a
point-in-time fact, so a request with an explicit `--as-of` declines the lookup outright rather
than answering a March question with May's schedule.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timedelta, timezone
import unittest
import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable


TODAY = date.today()


SESSIONS = pd.bdate_range(end=pd.Timestamp(TODAY), periods=200)
ENTRY = SESSIONS[-40].date()


def bars() -> ProviderSnapshot[pd.DataFrame]:
    index = SESSIONS
    close = pd.Series(np.linspace(80.0, 130.0, 200), index=index, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=index)
    return rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime.now(timezone.utc), as_of=index[-1].date(), coverage={"completed_only": True})


def calendar_snapshot(days_out: int, confirmation: str = "confirmed") -> ProviderSnapshot[dict]:
    when = (pd.Timestamp(TODAY) + pd.Timedelta(days=days_out)).date()
    return rows_snapshot({"symbol": "TEST", "earnings_date": when.isoformat(), "confirmation": confirmation, "window": None if confirmation == "confirmed" else [when.isoformat(), (when + timedelta(days=4)).isoformat()]}, provider="yfinance", retrieved_at=datetime.now(timezone.utc), as_of=TODAY, coverage={"kind": "forward_looking_current_only", "historical": False})


def run(calendar=None, **request) -> dict:
    base = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": ENTRY.isoformat(), "stop_price": 90.0}
    runtime = Runtime(
        price_history=lambda ticker, as_of: bars(),
        earnings_calendar=calendar or (lambda ticker: calendar_snapshot(10)),
    )
    return execute("ticker.risk", {**base, **request}, runtime=runtime)


def block(payload: dict) -> dict:
    return payload["data"]["management_evidence"]["earnings"]


class TheHarnessLooksItUp(unittest.TestCase):
    def test_an_undeclared_date_is_fetched_and_marked_as_fetched(self) -> None:
        payload = run()

        reading = block(payload)
        self.assertEqual(reading["state"], "reported")
        self.assertIs(reading["ahead"], True)
        self.assertEqual(reading["source"], "provider")
        self.assertEqual(reading["confirmation"], "confirmed")

    def test_a_declared_date_is_not_overwritten_by_the_feed(self) -> None:
        declared = (pd.Timestamp(TODAY) + pd.Timedelta(days=3)).date().isoformat()
        payload = run(earnings_date=declared)

        reading = block(payload)
        self.assertEqual(reading["earnings_date"], declared)
        self.assertEqual(reading["source"], "declared")
        self.assertEqual(reading["confirmation"], "declared_by_caller")

    def test_a_guessed_window_reaches_the_reader_as_a_guess(self) -> None:
        payload = run(calendar=lambda ticker: calendar_snapshot(10, "estimated_range"))

        reading = block(payload)
        self.assertEqual(reading["confirmation"], "estimated_range")
        self.assertEqual(len(reading["window"]), 2)

    def test_a_feed_with_nothing_to_say_leaves_the_gap_where_it_was(self) -> None:
        def refuse(ticker):
            raise ProviderUnavailable("yfinance", "earnings_date_missing", operation="next_earnings")

        payload = run(calendar=refuse)

        reading = block(payload)
        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "earnings_date_missing")
        self.assertEqual([item["id"] for item in payload["missing"] if item["id"] == "next_earnings"], ["next_earnings"])
        self.assertIs(next(item for item in payload["missing"] if item["id"] == "next_earnings")["required"], False)


class AForecastIsNotAHistoricalFact(unittest.TestCase):
    def test_an_explicit_as_of_declines_the_lookup(self) -> None:
        def explode(ticker):
            raise AssertionError("the calendar must not be consulted for a historical request")

        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "mode": "active", "as_of": "2025-12-31", "entry_price": 100.0, "entry_date": "2025-11-03", "stop_price": 90.0},
            runtime=Runtime(price_history=lambda ticker, as_of: bars(), earnings_calendar=explode),
        )

        reading = block(payload)
        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "earnings_calendar_is_current_only")


if __name__ == "__main__":
    unittest.main()
