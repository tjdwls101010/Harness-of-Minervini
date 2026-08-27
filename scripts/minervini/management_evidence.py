"""Measurements of a held position's structure, from completed bars, for ``ticker.risk``.

A hard stop answers one question: did price reach the level. Structure can deteriorate
while the stop is untouched -- two closes under the average the trader manages by, a close
under the 20-day average after a breakout, the largest decline of the whole advance -- and
those are the measurements here. Nothing in this module decides. Each block reports what
the bars show and which claim the reading belongs to; the reducer turns them into a SELL
only where the trader declared the rule as their own exit plan, and into REVIEW actions
otherwise.

Bars are completed sessions only, so ``as_of`` bounds every window. The moving averages are
computed over the whole history the provider returned, because an average needs its warm-up
before the entry session, and a bar whose average has not warmed up is reported as such
rather than measured against a shorter average that would read differently.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd

from . import doctrine


_ROLES = "management.ema21_sma50_roles"
_TWENTY_DAY = "management.close_below_20_day_average_lowers_probability"
_LARGEST_DECLINE = "management.largest_decline_since_stage2_start"
_VOLUME_STATE = "setup.volume_state_convention"
_CLOSING_RANGE = "setup.closing_range_formula"
# Enough places to strip binary-float noise from a reported figure and far too many to
# soften any limit the registry states.
_REPORTED_PRECISION = 10
AVERAGES = ("ema21", "sma50")


def _reported(value: float | None) -> float | None:
    return None if value is None else round(value, _REPORTED_PRECISION)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _completed(frame: Any, as_of: date) -> pd.DataFrame | None:
    """The provider's bars, normalised the way the stop audit normalises them, through as_of."""

    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"Close", "High", "Low"}.issubset(frame.columns):
        return None
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    if timestamps.isna().any():
        return None
    if timestamps.tz is not None:
        timestamps = timestamps.tz_convert("America/New_York").tz_localize(None)
    ordered = frame.copy()
    ordered.index = timestamps
    ordered = ordered.sort_index()
    ordered = ordered[[timestamp.date() <= as_of for timestamp in ordered.index]]
    if ordered.empty:
        return None
    # A repeated session is one bar, and the last print of it is the one that completed.
    ordered = ordered[~ordered.index.duplicated(keep="last")]
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in ordered.columns:
            ordered[column] = pd.to_numeric(ordered[column], errors="coerce")
    return ordered


def _closing_range_pct(row: pd.Series) -> float | None:
    high, low, close = _finite(row["High"]), _finite(row["Low"]), _finite(row["Close"])
    if high is None or low is None or close is None or high <= low:
        return None
    return (close - low) / (high - low) * 100


def _trail(bars: pd.DataFrame, average: pd.Series, *, length: int, entry_date: date, as_of: date) -> dict[str, Any]:
    """Two completed closes below one management average, audited from the entry session.

    Both closes have to be the position's own: a close under the average the session before
    entry is the bar the trader bought into, not a violation of the plan they bought with. A
    breach, once found, stands for the rest of the window the way a stop breach does -- the
    source's rule is that the position is closed at that moment, and a later recovery is
    something a position that no longer exists cannot benefit from.
    """

    dates = [timestamp.date() for timestamp in bars.index]
    window = [position for position, day in enumerate(dates) if entry_date <= day <= as_of]
    if not window:
        return {"state": "unavailable", "reason": "no_completed_bars_since_entry"}
    if window[0] < length - 1 or any(not math.isfinite(float(average.iloc[position])) for position in window):
        return {"state": "unavailable", "reason": "insufficient_history_for_average", "sessions_required": length}
    closes = bars["Close"]
    lows = bars["Low"]
    run = 0
    breach: int | None = None
    for position in window:
        close = _finite(closes.iloc[position])
        if close is None:
            return {"state": "unavailable", "reason": "invalid_close_since_entry", "date": dates[position].isoformat()}
        run = run + 1 if close < float(average.iloc[position]) else 0
        # The count that ends the position is TraderLion's number, read through the gate so
        # it is stamped as the contrast it is; a contrast_pass here is the rule's own event.
        if breach is None and doctrine.evaluate_gate(_ROLES, "management_closes_below_average", run)["state"] == "contrast_pass":
            breach = position
    last = window[-1]
    last_average = float(average.iloc[last])
    quality: dict[str, Any] | None = None
    if breach is not None:
        first = breach - 1
        second_close = float(closes.iloc[breach])
        quality = {
            "close_distance_pct": _reported((second_close - float(average.iloc[breach])) / float(average.iloc[breach]) * 100),
            "closing_range_pct": _reported(_closing_range_pct(bars.iloc[breach])),
            "second_close_above_first_close": second_close > float(closes.iloc[first]),
            "second_close_above_first_low": second_close > float(lows.iloc[first]),
        }
    return {
        "state": "breached" if breach is not None else "clear",
        "audited_from": dates[window[0]].isoformat(),
        "through": dates[last].isoformat(),
        "average": _reported(last_average),
        "last_close": _reported(float(closes.iloc[last])),
        "last_close_distance_pct": _reported((float(closes.iloc[last]) - last_average) / last_average * 100),
        "closes_below_in_a_row": run,
        "breach_date": dates[breach].isoformat() if breach is not None else None,
        "quality": quality,
    }


def _moving_average_trail(bars: pd.DataFrame, *, entry_date: date, as_of: date, selected: str | None) -> dict[str, Any]:
    ema_length = int(doctrine.threshold(_ROLES, "ema_length_sessions"))
    sma_length = int(doctrine.threshold(_ROLES, "sma_length_sessions"))
    closes = bars["Close"].astype(float)
    # The recursive form (adjust=False) is the exponential average charts draw; the
    # adjusted form weights a short history differently and would disagree with the chart.
    ema = closes.ewm(span=ema_length, adjust=False).mean()
    ema.iloc[: ema_length - 1] = float("nan")
    sma = closes.rolling(sma_length).mean()
    return {
        "doctrine_id": _ROLES,
        "binds": doctrine.binds(_ROLES),
        "selected": selected,
        "ema21": _trail(bars, ema, length=ema_length, entry_date=entry_date, as_of=as_of),
        "sma50": _trail(bars, sma, length=sma_length, entry_date=entry_date, as_of=as_of),
    }


def _twenty_day_average(bars: pd.DataFrame) -> dict[str, Any]:
    length = int(doctrine.threshold(_TWENTY_DAY, "average_length_sessions"))
    closes = bars["Close"].astype(float)
    if len(closes) < length:
        return {"doctrine_id": _TWENTY_DAY, "state": "unavailable", "reason": "insufficient_history_for_average", "sessions_required": length}
    average = float(closes.rolling(length).mean().iloc[-1])
    close = _finite(closes.iloc[-1])
    if close is None or not math.isfinite(average) or average <= 0:
        return {"doctrine_id": _TWENTY_DAY, "state": "unavailable", "reason": "invalid_close"}
    return {
        "doctrine_id": _TWENTY_DAY,
        "state": "below" if close < average else "above",
        "date": bars.index[-1].date().isoformat(),
        "average": _reported(average),
        "close": _reported(close),
        "close_distance_pct": _reported((close - average) / average * 100),
    }


def _weekly(bars: pd.DataFrame, *, stage2_start: date) -> dict[str, Any]:
    closes = bars["Close"].astype(float)
    # A week is a completed bar once its Friday has printed or a later week has begun;
    # the week as_of falls inside is still being drawn and is not compared.
    periods = closes.index.to_period("W-FRI")
    last_of_week = closes.groupby(periods).tail(1)
    week_ends = [period.end_time.normalize().date() for period in last_of_week.index.to_period("W-FRI")]
    completed = [
        index < len(last_of_week) - 1 or timestamp.weekday() == 4
        for index, timestamp in enumerate(last_of_week.index)
    ]
    weekly = pd.Series(last_of_week.to_numpy(), index=pd.Index(week_ends))
    weekly = weekly[completed]
    if len(weekly) < 2:
        return {"state": "unavailable", "reason": "fewer_than_two_completed_weeks"}
    changes = weekly.pct_change() * 100
    since = changes[[end >= stage2_start for end in changes.index]].dropna()
    if since.empty:
        return {"state": "unavailable", "reason": "no_completed_week_since_stage2_start"}
    largest = float(since.min())
    latest_end = weekly.index[-1]
    if largest >= 0:
        return {"state": "reported", "largest_pct": None, "week_ending": latest_end.isoformat(), "latest_completed_week_is_largest": False}
    largest_end = since.idxmin()
    return {
        "state": "reported",
        "largest_pct": _reported(largest),
        "largest_week_ending": largest_end.isoformat(),
        "week_ending": latest_end.isoformat(),
        "latest_completed_week_is_largest": largest_end == latest_end,
    }


def _daily(bars: pd.DataFrame, *, stage2_start: date) -> dict[str, Any]:
    closes = bars["Close"].astype(float)
    changes = closes.pct_change() * 100
    dates = [timestamp.date() for timestamp in changes.index]
    since = changes[[day >= stage2_start for day in dates]].dropna()
    if since.empty:
        return {"state": "unavailable", "reason": "no_completed_session_since_stage2_start"}
    largest = float(since.min())
    if largest >= 0:
        return {"state": "reported", "largest_pct": None, "date": None, "last_session_is_largest": False, "volume_ratio": None, "volume_signal": None}
    stamp = since.idxmin()
    position = int(bars.index.get_loc(stamp))
    baseline_sessions = int(doctrine.threshold(_VOLUME_STATE, "position_baseline_sessions"))
    ratio: float | None = None
    if "Volume" in bars.columns and position >= baseline_sessions:
        baseline = float(bars["Volume"].iloc[position - baseline_sessions : position].mean())
        volume = _finite(bars["Volume"].iloc[position])
        if volume is not None and math.isfinite(baseline) and baseline > 0:
            ratio = volume / baseline
    return {
        "state": "reported",
        "largest_pct": _reported(largest),
        "date": stamp.date().isoformat(),
        "last_session_is_largest": stamp == bars.index[-1],
        "volume_ratio": _reported(ratio),
        "volume_baseline_sessions": baseline_sessions,
        "volume_signal": doctrine.evaluate_marker(_VOLUME_STATE, "high_volume_ratio", ratio),
    }


def _largest_decline(bars: pd.DataFrame, *, stage2_start: date | None) -> dict[str, Any]:
    if stage2_start is None:
        return {"state": "unavailable", "reason": "stage2_start_not_declared"}
    return {
        "doctrine_id": _LARGEST_DECLINE,
        "binds": doctrine.binds(_LARGEST_DECLINE),
        "state": "reported",
        "stage2_start": stage2_start.isoformat(),
        "daily": _daily(bars, stage2_start=stage2_start),
        "weekly": _weekly(bars, stage2_start=stage2_start),
    }


def build_management_evidence(
    frame: Any,
    *,
    entry_date: date,
    as_of: date,
    management_average: str | None = None,
    stage2_start: date | None = None,
) -> dict[str, Any]:
    """Every structural measurement ``ticker.risk`` reads for a held position.

    ``management_average`` names the average the trader manages by, if they declared one;
    it is echoed back as ``selected`` and both averages are measured either way, so the one
    not chosen is still visible as review evidence.
    """

    bars = _completed(frame, as_of)
    if bars is None:
        unavailable = {"state": "unavailable", "reason": "completed_ohlc_history_unavailable"}
        return {"moving_average_trail": {**unavailable, "selected": management_average}, "twenty_day_average": unavailable, "largest_decline_since_stage2_start": unavailable}
    return {
        "moving_average_trail": _moving_average_trail(bars, entry_date=entry_date, as_of=as_of, selected=management_average),
        "twenty_day_average": _twenty_day_average(bars),
        "largest_decline_since_stage2_start": _largest_decline(bars, stage2_start=stage2_start),
    }


__all__ = ["AVERAGES", "build_management_evidence"]
