from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
import unicodedata

import numpy as np
import pandas as pd

from ..clock import resolve_as_of
from ..setup_structure import _CORPORATE_ACTION_COLUMN, _DISTRIBUTION_COLUMN
from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


def _complete_rows(frame: pd.DataFrame) -> np.ndarray:
    """Mark the rows whose every present value the measurements read is a finite number.

    Positional rather than label-indexed: a provider may repeat a session, and a
    label slice would then keep or drop every row sharing that timestamp.

    The corporate-action column counts because the measurement boundary refuses a frame with a
    non-finite value in any column it carries. Checked here only for OHLCV, a single blank split
    cell reached that boundary and took the whole history down -- for the setup and the chart as
    well, neither of which reads the column.
    """

    complete = np.ones(len(frame), dtype=bool)
    for column in (*OHLCV_COLUMNS, _CORPORATE_ACTION_COLUMN, _DISTRIBUTION_COLUMN):
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
        # Actions on, adjustment off: the prices stay the ones the tape printed, and the split
        # events arrive beside them. Without the events a reverse split is indistinguishable from
        # a hundred percent overnight advance, which is the exact size the Power Play criteria
        # ask about, and the frame alone cannot tell a caller that it does not know.
        lambda: ticker.history(start=start, end=end, interval="1d", auto_adjust=False, actions=True),
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
                # What the frame carries, not what was asked for. `actions=True` is a request,
                # and a feed that answers without the columns leaves a history that cannot say
                # whether a split or a distribution happened.
                "corporate_actions": _CORPORATE_ACTION_COLUMN in completed,
                "distributions": _DISTRIBUTION_COLUMN in completed,
                "requested_session": clock.date.isoformat(),
                "last_completed_bar": last_completed_bar.isoformat(),
            },
            stale=last_completed_bar != clock.date,
        ),
    )


def next_earnings_snapshot(
    symbol: str,
    *,
    as_of: str | date | None = None,
    ticker: Any | None = None,
    calendar: Any | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[dict[str, Any]]:
    """Fetch the next scheduled earnings report as a current, forward-looking snapshot only.

    A calendar entry is mutable the way a sector label is mutable, and no feed can say what it
    held on a past date. Dating today's answer to a past session would put a forecast nobody
    made then inside a point-in-time verdict, so a historical request is refused rather than
    answered.

    Whether anybody confirmed the date travels with it. Two dates is the feed naming a window it
    guessed at, and the earlier edge is the one published: a holder asking whether a report is
    still ahead needs the first session it could land on, and the later edge would report a
    position as clear on a day the company might already have reported.
    """

    observed_at = retrieved_at or datetime.now(timezone.utc)
    requested_date = _current_date(as_of, observed_at)
    if requested_date != observed_at.date():
        raise ProviderUnavailable("yfinance", "historical_earnings_calendar_unavailable", operation="next_earnings")

    if calendar is None:
        if ticker is None:
            try:
                import yfinance as yf
            except Exception as error:
                raise ProviderUnavailable("yfinance", "package_unavailable", operation="next_earnings") from error
            ticker = yf.Ticker(symbol)
        calendar = fetch_with_one_retry("yfinance", "next_earnings", lambda: ticker.calendar)

    if not isinstance(calendar, Mapping):
        raise ProviderUnavailable("yfinance", "invalid_earnings_calendar_response", operation="next_earnings")
    entries = calendar.get("Earnings Date")
    if isinstance(entries, (str, bytes)) or not isinstance(entries, (list, tuple)):
        entries = [entries] if entries is not None else []
    if not entries:
        raise ProviderUnavailable("yfinance", "earnings_date_missing", operation="next_earnings")
    dates = sorted(_calendar_date(entry) for entry in entries)
    if dates[0] < observed_at.date():
        # A calendar still showing the last report is not answering the question that was
        # asked. Publishing it would put a date behind the holder into a block whose whole
        # meaning is whether a report is ahead of them.
        raise ProviderUnavailable("yfinance", "earnings_date_not_ahead", operation="next_earnings")

    return ProviderSnapshot(
        data={
            "symbol": symbol.upper(),
            "earnings_date": dates[0].isoformat(),
            "confirmation": "confirmed" if len(dates) == 1 else "estimated_range",
            "window": None if len(dates) == 1 else [dates[0].isoformat(), dates[-1].isoformat()],
        },
        meta=SnapshotMeta(
            provider="yfinance",
            retrieved_at=observed_at,
            as_of=observed_at.date(),
            coverage={
                "kind": "forward_looking_current_only",
                "historical": False,
                "source": "ticker.calendar",
                "source_fields": {"earnings_date": "Earnings Date"},
                "symbol": symbol.upper(),
            },
        ),
    )


def _calendar_date(value: Any) -> date:
    """One calendar entry as a date, refusing anything the feed wrote as something else."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as error:
            raise ProviderUnavailable("yfinance", "invalid_earnings_date", operation="next_earnings") from error
    raise ProviderUnavailable("yfinance", "invalid_earnings_date", operation="next_earnings")
