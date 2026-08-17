from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from ..clock import resolve_as_of
from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


def _index_dates(frame: pd.DataFrame) -> pd.Series:
    index = pd.to_datetime(frame.index, errors="coerce")
    if getattr(index, "tz", None) is not None:
        index = index.tz_convert("America/New_York").tz_localize(None)
    return pd.Series(index.date, index=frame.index)


def completed_daily_bars(
    symbol: str,
    *,
    as_of: str | date | None = None,
    ticker: Any | None = None,
    now: datetime | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[pd.DataFrame]:
    """Fetch completed daily bars only, with an exclusive provider end boundary."""

    clock = resolve_as_of(as_of, now=now)
    if ticker is None:
        try:
            import yfinance as yf
        except Exception as error:
            raise ProviderUnavailable("yfinance", "package_unavailable", operation="daily_bars") from error
        ticker = yf.Ticker(symbol)

    end = (clock.date + timedelta(days=1)).isoformat()
    frame = fetch_with_one_retry(
        "yfinance",
        "daily_bars",
        lambda: ticker.history(end=end, interval="1d", auto_adjust=False, actions=False),
    )
    if not isinstance(frame, pd.DataFrame):
        raise ProviderUnavailable("yfinance", "invalid_daily_bar_response", operation="daily_bars")

    completed = frame.copy()
    if not completed.empty:
        dates = _index_dates(completed)
        completed = completed.loc[dates <= clock.date]
    if completed.empty:
        raise ProviderUnavailable("yfinance", "no_completed_daily_bars", operation="daily_bars")

    observed_at = retrieved_at or datetime.now(timezone.utc)
    return ProviderSnapshot(
        data=completed,
        meta=SnapshotMeta(
            provider="yfinance",
            retrieved_at=observed_at,
            as_of=clock.date,
            coverage={"interval": "1d", "completed_only": True, "symbol": symbol.upper()},
        ),
    )
