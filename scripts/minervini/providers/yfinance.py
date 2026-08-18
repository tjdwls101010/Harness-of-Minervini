from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
import unicodedata

import numpy as np
import pandas as pd

from ..clock import resolve_as_of
from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


def _complete_rows(frame: pd.DataFrame) -> np.ndarray:
    """Mark the rows whose every present OHLCV value is a finite number.

    Positional rather than label-indexed: a provider may repeat a session, and a
    label slice would then keep or drop every row sharing that timestamp.
    """

    complete = np.ones(len(frame), dtype=bool)
    for column in OHLCV_COLUMNS:
        if column in frame:
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
            complete &= np.isfinite(values)
    return complete


def _index_dates(frame: pd.DataFrame) -> pd.Series:
    index = pd.to_datetime(frame.index, errors="coerce")
    if getattr(index, "tz", None) is not None:
        index = index.tz_convert("America/New_York").tz_localize(None)
    return pd.Series(index.date, index=frame.index)


def _current_date(as_of: str | date | None, observed_at: datetime) -> date:
    if as_of is None:
        return observed_at.date()
    return as_of if isinstance(as_of, date) else date.fromisoformat(as_of)


def _taxonomy_name(info: Mapping[str, Any], field: str) -> str | None:
    value = info.get(field)
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _taxonomy_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


def current_classification_snapshot(
    symbol: str,
    *,
    as_of: str | date | None = None,
    ticker: Any | None = None,
    info: Mapping[str, Any] | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[dict[str, str]]:
    """Fetch yfinance's mutable taxonomy only as a current classification snapshot."""

    observed_at = retrieved_at or datetime.now(timezone.utc)
    requested_date = _current_date(as_of, observed_at)
    if requested_date != observed_at.date():
        raise ProviderUnavailable("yfinance", "historical_classification_unavailable", operation="current_classification")

    if info is None:
        if ticker is None:
            try:
                import yfinance as yf
            except Exception as error:
                raise ProviderUnavailable("yfinance", "package_unavailable", operation="current_classification") from error
            ticker = yf.Ticker(symbol)
        info = fetch_with_one_retry("yfinance", "current_classification", lambda: ticker.info)

    if not isinstance(info, Mapping):
        raise ProviderUnavailable("yfinance", "invalid_classification_response", operation="current_classification")
    sector = _taxonomy_name(info, "sector")
    industry = _taxonomy_name(info, "industry")
    if sector is None or industry is None:
        raise ProviderUnavailable("yfinance", "classification_missing", operation="current_classification")

    return ProviderSnapshot(
        data={
            "symbol": symbol.upper(),
            "sector": sector,
            "industry": industry,
            "industry_id": f"yfinance:{_taxonomy_slug(sector)}:{_taxonomy_slug(industry)}",
        },
        meta=SnapshotMeta(
            provider="yfinance",
            retrieved_at=observed_at,
            as_of=observed_at.date(),
            coverage={
                "kind": "current_classification_only",
                "historical": False,
                "taxonomy": "mutable_current_only",
                "source": "ticker.info",
                "source_fields": {"sector": "sector", "industry": "industry"},
            },
        ),
    )


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
    start = (clock.date - timedelta(days=1100)).isoformat()
    frame = fetch_with_one_retry(
        "yfinance",
        "daily_bars",
        lambda: ticker.history(start=start, end=end, interval="1d", auto_adjust=False, actions=False),
    )
    if not isinstance(frame, pd.DataFrame):
        raise ProviderUnavailable("yfinance", "invalid_daily_bar_response", operation="daily_bars")

    completed = frame.copy()
    if not completed.empty:
        dates = _index_dates(completed)
        completed = completed.loc[dates <= clock.date]
    if completed.empty:
        raise ProviderUnavailable("yfinance", "no_completed_daily_bars", operation="daily_bars")

    # A session the provider has not finished writing arrives with the price fields
    # blank. Treating it as completed is what let two different sessions be mixed
    # into one verdict, so completion is decided here rather than by each consumer.
    complete = _complete_rows(completed)
    if not complete.any():
        raise ProviderUnavailable("yfinance", "no_completed_daily_bars", operation="daily_bars")
    # Blank rows before a listing began are not the history's problem; blank rows
    # between real sessions are, because they silently shorten every average.
    filled = np.flatnonzero(complete)
    first_complete, last_complete = int(filled[0]), int(filled[-1])
    completed = completed.iloc[first_complete : last_complete + 1]
    if not complete[first_complete : last_complete + 1].all():
        raise ProviderUnavailable("yfinance", "incomplete_daily_bars", operation="daily_bars")

    last_completed_bar = _index_dates(completed).iloc[-1]
    observed_at = retrieved_at or datetime.now(timezone.utc)
    return ProviderSnapshot(
        data=completed,
        meta=SnapshotMeta(
            provider="yfinance",
            retrieved_at=observed_at,
            as_of=last_completed_bar,
            coverage={
                "interval": "1d",
                "completed_only": True,
                "symbol": symbol.upper(),
                "requested_start": start,
                "requested_end_exclusive": end,
                "adjusted": False,
                "requested_session": clock.date.isoformat(),
                "last_completed_bar": last_completed_bar.isoformat(),
            },
            stale=last_completed_bar != clock.date,
        ),
    )
