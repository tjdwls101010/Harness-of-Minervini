from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
import unicodedata

import pandas as pd

from ..clock import resolve_as_of
from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


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
