"""Shared fixtures for provider contracts."""

from __future__ import annotations

from datetime import date
from importlib import resources
import pandas as pd


FIXTURES = resources.files("tests.fixtures.providers")


def close_only(index: "pd.DatetimeIndex", closes: list[float]) -> "pd.DataFrame":
    """A frame carrying every OHLCV column, varying only the closes.

    The provider requires the price columns to be present, because a frame missing them was
    passing as a completed session and the multiple then reported the close as its missing
    input while the envelope called the evidence whole. These fixtures care about the closes,
    so the rest are filled in rather than left out.
    """

    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": [1_000_000] * len(closes)},
        index=index,
    )


class FakeTicker:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    def history(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(kwargs)
        return self.frame


class FakeClock:
    """A monotonic clock separating time the test passes from time a sleep costs."""

    def __init__(self, start: float, *, oversleep: float = 1.0) -> None:
        self.value = start
        self.waits: list[float] = []
        self.oversleep = oversleep

    def now(self) -> float:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value += seconds

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.value += seconds * self.oversleep


class FakeRS:
    def __init__(self) -> None:
        self.get_calls: list[tuple[str, str | None]] = []

    def dates(self) -> dict[str, str]:
        return {"first": "2026-08-01", "last": "2026-08-14"}

    def get(self, ticker: str, date: str | None = None) -> dict[str, object] | None:
        self.get_calls.append((ticker, date))
        if date == "2026-08-12":
            return {"ticker": ticker, "date": date, "rs_rating": 91}
        if date == "2026-08-14":
            return {"ticker": ticker, "date": date, "rs_rating": 93}
        return None
