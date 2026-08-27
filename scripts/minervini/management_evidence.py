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
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from . import doctrine


_ROLES = "management.ema21_sma50_roles"
_TWENTY_DAY = "management.close_below_20_day_average_lowers_probability"
_LARGEST_DECLINE = "management.largest_decline_since_stage2_start"
_VOLUME_STATE = "setup.volume_state_convention"
_SINCE_ENTRY = ("base_extension", "key_reversal", "gaps_since_breakout")
_BLOCKS = (
    "moving_average_trail",
    "twenty_day_average",
    "largest_decline_since_stage2_start",
    "base_extension",
    "moving_average_extension",
    "key_reversal",
    "gaps_since_breakout",
    "climax",
    "failed_volume_confirmation",
)
_PAUSE_ZONE = "management.tl_base_extension_pause_zone"
_OWN_CHARACTER = "management.tl_extension_measured_against_own_character"
_KEY_REVERSAL = "management.tl_key_reversal_criteria"
_LATE_GAPS = "management.tl_late_gaps_fail_more_often"
_CLIMAX = "management.climax_run_ends_the_advance"
_FAILED_VOLUME = "management.low_volume_breakout_then_high_volume_selling"
_ATR = "convention.average_true_range"
_WINDOWS = "convention.momentum_review_windows"
_CLOSING_RANGE = "setup.closing_range_formula"
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
    # Two prints of one session can carry different clock times, so the comparison is the
    # session date -- the same rule the stop audit applies to the same frame.
    ordered = ordered[~ordered.index.normalize().duplicated(keep="last")]
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


def _latest_tie(series: pd.Series, value: float) -> Any:
    """The index label of the last element equal to ``value``."""

    positions = [position for position, element in enumerate(series) if float(element) == value]
    return series.index[positions[-1]]


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
    largest_end = _latest_tie(since, largest)
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
    # idxmin names the first occurrence. A later session that fell exactly as far is the
    # more recent evidence, and reporting the earlier date would date the decline before
    # the session a reader has to act on, so every tie resolves to the latest.
    stamp = _latest_tie(since, largest)
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
    declared = stage2_start
    if stage2_start.weekday() >= 5:
        # A stage begins in an analyst's reading of the chart, not in a trade, so a weekend
        # anchor is a real anchor: the advance starts at the first session that could open
        # after it. Comparing the raw Saturday with a Monday history would report the
        # sessions before it as missing when none of them exist.
        stage2_start = stage2_start + timedelta(days=7 - stage2_start.weekday())
    first_available = bars.index[0].date()
    if first_available > stage2_start:
        # A larger decline in the sessions the provider never returned is unknowable, so a
        # "largest since" measured from a later start would say more than the bars know.
        return {
            "state": "unavailable",
            "reason": "history_starts_after_stage2_start",
            "stage2_start": stage2_start.isoformat(),
            "first_available": first_available.isoformat(),
        }
    return {
        "doctrine_id": _LARGEST_DECLINE,
        "binds": doctrine.binds(_LARGEST_DECLINE),
        "state": "reported",
        "stage2_start": declared.isoformat(),
        "measured_from": stage2_start.isoformat(),
        "daily": _daily(bars, stage2_start=stage2_start),
        "weekly": _weekly(bars, stage2_start=stage2_start),
    }


def _unreadable(bars: pd.DataFrame) -> str | None:
    """The first session the harness cannot read, if there is one.

    A price of zero or NaN is not a cheap stock or a quiet session -- it is a bar the
    provider could not fill. Measuring structure through it produces percentages divided
    by nothing and comparisons that silently answer false, so the blocks that would have
    read it say unavailable and name the session instead.
    """

    for column, floor in (("Open", 0.0), ("High", 0.0), ("Low", 0.0), ("Close", 0.0), ("Volume", -1.0)):
        if column not in bars.columns:
            continue
        values = pd.to_numeric(bars[column], errors="coerce").to_numpy(dtype=float)
        bad = ~np.isfinite(values) | (values <= floor)
        if bool(bad.any()):
            return bars.index[int(bad.argmax())].date().isoformat()
    return None


def _positions_since(bars: pd.DataFrame, since: date) -> list[int]:
    return [position for position, timestamp in enumerate(bars.index) if timestamp.date() >= since]


def _base_extension(bars: pd.DataFrame, *, entry_date: date, base_top: float | None) -> dict[str, Any]:
    if base_top is None:
        return {"state": "unavailable", "reason": "base_top_not_declared"}
    closes = bars["Close"].astype(float)
    highs = bars["High"].astype(float)
    last_close = _finite(closes.iloc[-1])
    held = [position for position, timestamp in enumerate(bars.index) if timestamp.date() >= entry_date]
    max_high = _finite(highs.iloc[held].max()) if held else None
    if last_close is None or base_top <= 0:
        return {"state": "unavailable", "reason": "invalid_close_or_base_top"}
    extension_pct = (last_close / base_top - 1) * 100
    return {
        "doctrine_id": _PAUSE_ZONE,
        "binds": doctrine.binds(_PAUSE_ZONE),
        "state": "reported",
        "base_top": base_top,
        "extension_pct": _reported(extension_pct),
        "max_extension_pct": _reported((max_high / base_top - 1) * 100 if max_high is not None else None),
        "band": doctrine.evaluate_band(_PAUSE_ZONE, "pause_zone_pct", extension_pct),
    }


def _average_true_range(bars: pd.DataFrame) -> dict[str, Any]:
    length = int(doctrine.parameter(_ATR, "atr_length_sessions"))
    highs = bars["High"].astype(float)
    lows = bars["Low"].astype(float)
    closes = bars["Close"].astype(float)
    if len(bars) < length + 1:
        return {"doctrine_id": _ATR, "state": "unavailable", "reason": "insufficient_history_for_average_true_range", "length_sessions": length}
    previous_close = closes.shift(1)
    true_range = pd.concat([highs - lows, (highs - previous_close).abs(), (previous_close - lows).abs()], axis=1).max(axis=1)
    value = float(true_range.iloc[-length:].mean())
    if not math.isfinite(value) or value <= 0:
        return {"doctrine_id": _ATR, "state": "unavailable", "reason": "invalid_true_range", "length_sessions": length}
    return {"doctrine_id": _ATR, "length_sessions": length, "value": _reported(value)}


def _moving_average_extension(bars: pd.DataFrame) -> dict[str, Any]:
    ema_length = int(doctrine.threshold(_ROLES, "ema_length_sessions"))
    sma_length = int(doctrine.threshold(_ROLES, "sma_length_sessions"))
    closes = bars["Close"].astype(float)
    atr = _average_true_range(bars)
    atr_value = atr.get("value")
    ema = closes.ewm(span=ema_length, adjust=False).mean()
    ema.iloc[: ema_length - 1] = float("nan")
    sma = closes.rolling(sma_length).mean()
    block: dict[str, Any] = {"doctrine_id": _OWN_CHARACTER, "binds": doctrine.binds(_OWN_CHARACTER), "atr": atr, "needs_chart": True}
    for name, series, length in (("ema21", ema, ema_length), ("sma50", sma, sma_length)):
        if len(bars) < length or not math.isfinite(float(series.iloc[-1])):
            block[name] = {"state": "unavailable", "reason": "insufficient_history_for_average", "sessions_required": length}
            continue
        average = float(series.iloc[-1])
        close = float(closes.iloc[-1])
        extension_pct = (close - average) / average * 100
        # The stock's own habit: how the current stretch ranks among every prior session
        # whose average existed. The last session is excluded from its own ranking.
        prior = [
            (float(closes.iloc[position]) - float(series.iloc[position])) / float(series.iloc[position]) * 100
            for position in range(length - 1, len(bars) - 1)
            if math.isfinite(float(series.iloc[position]))
        ]
        percentile = (sum(1 for value in prior if value <= extension_pct) / len(prior) * 100) if prior else None
        block[name] = {
            "extension_pct": _reported(extension_pct),
            "extension_atr": _reported((close - average) / atr_value if atr_value else None),
            "historical_percentile": _reported(percentile),
            "history_sessions": len(prior),
        }
    return block


def _key_reversal(bars: pd.DataFrame, *, entry_date: date, breakout_date: date | None) -> dict[str, Any]:
    since = breakout_date or entry_date
    basis = "breakout_date" if breakout_date is not None else "entry_date"
    window = _positions_since(bars, since)
    if len(bars) < 2 or not window:
        return {"state": "unavailable", "reason": "insufficient_history_since_window_start"}
    last = len(bars) - 1
    previous = last - 1
    opens = bars["Open"].astype(float) if "Open" in bars.columns else None
    highs = bars["High"].astype(float)
    lows = bars["Low"].astype(float)
    closes = bars["Close"].astype(float)
    volumes = bars["Volume"].astype(float) if "Volume" in bars.columns else None
    others = [position for position in window if position != last]
    gap_up = opens is not None and float(opens.iloc[last]) > float(highs.iloc[previous])
    features = {
        "gap_up_filled_and_reversed": bool(gap_up and float(lows.iloc[last]) <= float(highs.iloc[previous]) and float(closes.iloc[last]) < float(opens.iloc[last])) if opens is not None else None,
        # With no other session inside the window there is nothing to be highest or widest
        # than, and answering false there would read as a criterion checked and missed.
        # A tied maximum is still the maximum: the session traded as heavily, and as widely,
        # as anything since the window opened.
        "highest_volume_since": None if (volumes is None or not others) else bool(float(volumes.iloc[last]) >= max(float(volumes.iloc[position]) for position in others)),
        "widest_range_since": None if not others else bool((float(highs.iloc[last]) - float(lows.iloc[last])) >= max(float(highs.iloc[position]) - float(lows.iloc[position]) for position in others)),
        "closed_below_prior_low": bool(float(closes.iloc[last]) < float(lows.iloc[previous])),
        "closing_range_pct": _reported(_closing_range_pct(bars.iloc[last])),
        "visually_extended": None,
        "trend_line_of_highs_breached": None,
    }
    computable = sum(1 for name in ("gap_up_filled_and_reversed", "highest_volume_since", "widest_range_since", "closed_below_prior_low") if features[name] is True)
    missing_inputs = [name for name, present in (("open_history", opens is not None), ("volume_history", volumes is not None)) if not present]
    return {
        "doctrine_id": _KEY_REVERSAL,
        "doctrine_ids": [_KEY_REVERSAL, _CLOSING_RANGE],
        "binds": doctrine.binds(_KEY_REVERSAL),
        "since": since.isoformat(),
        "since_basis": basis,
        "missing_inputs": missing_inputs,
        "date": bars.index[last].date().isoformat(),
        "features": features,
        "computable_criteria_met": computable,
        "needs_chart": True,
    }


def _gaps_since_breakout(bars: pd.DataFrame, *, entry_date: date, breakout_date: date | None) -> dict[str, Any]:
    since = breakout_date or entry_date
    basis = "breakout_date" if breakout_date is not None else "entry_date"
    if "Open" not in bars.columns:
        return {"state": "unavailable", "reason": "open_history_unavailable"}
    window = _positions_since(bars, since)
    if not window:
        return {"state": "unavailable", "reason": "insufficient_history_since_window_start"}
    opens = bars["Open"].astype(float)
    highs = bars["High"].astype(float)
    lows = bars["Low"].astype(float)
    closes = bars["Close"].astype(float)
    gap_positions = [position for position in window if position >= 1 and float(opens.iloc[position]) > float(highs.iloc[position - 1])]
    latest: dict[str, Any] | None = None
    if gap_positions:
        gap = gap_positions[-1]
        prior_high = float(highs.iloc[gap - 1])
        # The gap session itself can close its own gap: it opened above the prior high and
        # traded back down through it before the bell.
        filled = any(float(lows.iloc[position]) <= prior_high for position in range(gap, len(bars)))
        latest = {"date": bars.index[gap].date().isoformat(), "filled": filled, "closing_range_pct": _reported(_closing_range_pct(bars.iloc[gap]))}
    breakout_close = float(closes.iloc[window[0]])
    return {
        "doctrine_id": _LATE_GAPS,
        "doctrine_ids": [_LATE_GAPS, _CLOSING_RANGE],
        "binds": doctrine.binds(_LATE_GAPS),
        "state": "reported",
        "since": since.isoformat(),
        "since_basis": basis,
        "gap_up_count": len(gap_positions),
        "gap_dates": [bars.index[position].date().isoformat() for position in gap_positions],
        "run_pct_since_breakout": _reported((max(float(highs.iloc[position]) for position in window) / breakout_close - 1) * 100 if breakout_close > 0 else None),
        "latest_gap": latest,
        "needs_chart": True,
    }


def _climax(bars: pd.DataFrame) -> dict[str, Any]:
    closes = bars["Close"].astype(float)
    lengths = [int(doctrine.parameter(_WINDOWS, name)) for name in ("short_window_sessions", "medium_window_sessions", "long_window_sessions")]
    gap_window = int(doctrine.parameter(_WINDOWS, "medium_window_sessions"))
    if len(bars) <= max(lengths):
        return {"state": "unavailable", "reason": "insufficient_history_for_return_windows", "sessions_required": max(lengths) + 1}
    returns = {f"return_{window}_pct": _reported((float(closes.iloc[-1]) / float(closes.iloc[-1 - window]) - 1) * 100) for window in lengths}
    opens = bars["Open"].astype(float) if "Open" in bars.columns else None
    highs = bars["High"].astype(float)
    gap_ups = (
        sum(1 for position in range(len(bars) - gap_window, len(bars)) if position >= 1 and float(opens.iloc[position]) > float(highs.iloc[position - 1]))
        if opens is not None
        else None
    )
    percentile: float | None = None
    if "Volume" in bars.columns:
        volumes = bars["Volume"].astype(float)
        prior = [float(volumes.iloc[position]) for position in range(len(bars) - 1)]
        percentile = (sum(1 for value in prior if value <= float(volumes.iloc[-1])) / len(prior) * 100) if prior else None
    return {
        "doctrine_id": _CLIMAX,
        "doctrine_ids": [_CLIMAX, _WINDOWS, _CLOSING_RANGE],
        "binds": doctrine.binds(_CLIMAX),
        "state": "reported",
        "windows": {**{f"return_{window}_pct": window for window in lengths}, "gap_ups_last_10_sessions": gap_window},
        "missing_inputs": [name for name, present in (("open_history", opens is not None), ("volume_history", "Volume" in bars.columns)) if not present],
        **returns,
        "gap_ups_last_10_sessions": gap_ups,
        "last_volume_percentile": _reported(percentile),
        "last_closing_range_pct": _reported(_closing_range_pct(bars.iloc[-1])),
        "needs_chart": True,
    }


def _failed_volume_confirmation(bars: pd.DataFrame, *, breakout_date: date | None, sessions: set[date], first_session: date) -> dict[str, Any]:
    if breakout_date is None:
        return {"state": "unavailable", "reason": "breakout_date_not_declared"}
    if "Volume" not in bars.columns:
        return {"state": "unavailable", "reason": "volume_history_unavailable"}
    if breakout_date not in sessions:
        return {"state": "unavailable", "reason": "history_starts_after_breakout_date" if first_session > breakout_date else "no_completed_bar_on_breakout_date"}
    window = _positions_since(bars, breakout_date)
    if not window:
        return {"state": "unavailable", "reason": "no_completed_bar_on_or_after_breakout_date"}
    breakout = window[0]
    baseline_sessions = int(doctrine.threshold(_VOLUME_STATE, "position_baseline_sessions"))
    if breakout < baseline_sessions:
        return {"state": "unavailable", "reason": "insufficient_history_for_volume_baseline", "sessions_required": baseline_sessions}
    volumes = bars["Volume"].astype(float)
    closes = bars["Close"].astype(float)
    baseline = float(volumes.iloc[breakout - baseline_sessions : breakout].mean())
    if not math.isfinite(baseline) or baseline <= 0:
        return {"state": "unavailable", "reason": "invalid_volume_baseline"}
    breakout_ratio = float(volumes.iloc[breakout]) / baseline
    # Every ratio uses the pre-breakout baseline, so the breakout session and the selling
    # after it are measured against the same yardstick and the comparison is between the
    # stock's own two sessions rather than two different averages.
    down = [
        (position, float(volumes.iloc[position]) / baseline)
        for position in range(breakout + 1, len(bars))
        if float(closes.iloc[position]) < float(closes.iloc[position - 1])
    ]
    heaviest = max(down, key=lambda item: item[1]) if down else None
    return {
        "doctrine_id": _FAILED_VOLUME,
        "binds": doctrine.binds(_FAILED_VOLUME),
        "state": "reported",
        "breakout_date": bars.index[breakout].date().isoformat(),
        "volume_baseline_sessions": baseline_sessions,
        "breakout_volume_ratio": _reported(breakout_ratio),
        "breakout_volume_signal": doctrine.evaluate_marker(_VOLUME_STATE, "low_volume_ratio", breakout_ratio),
        "heaviest_down_session": {"date": bars.index[heaviest[0]].date().isoformat(), "volume_ratio": _reported(heaviest[1])} if heaviest else None,
        "selling_volume_exceeded_breakout_volume": bool(heaviest is not None and heaviest[1] > breakout_ratio),
    }


def build_management_evidence(
    frame: Any,
    *,
    entry_date: date,
    as_of: date,
    management_average: str | None = None,
    stage2_start: date | None = None,
    base_top: float | None = None,
    breakout_date: date | None = None,
) -> dict[str, Any]:
    """Every structural measurement ``ticker.risk`` reads for a held position.

    ``management_average`` names the average the trader manages by, if they declared one;
    it is echoed back as ``selected`` and both averages are measured either way, so the one
    not chosen is still visible as review evidence.
    """

    bars = _completed(frame, as_of)
    if bars is None:
        unavailable = {"state": "unavailable", "reason": "completed_ohlc_history_unavailable"}
        return {
            "moving_average_trail": {**unavailable, "selected": management_average},
            "twenty_day_average": unavailable,
            "largest_decline_since_stage2_start": unavailable,
            "base_extension": unavailable,
            "moving_average_extension": unavailable,
            "key_reversal": unavailable,
            "gaps_since_breakout": unavailable,
            "climax": unavailable,
            "failed_volume_confirmation": unavailable,
        }
    unreadable = _unreadable(bars)
    if unreadable is not None:
        broken = {"state": "unavailable", "reason": "invalid_ohlc_history", "date": unreadable}
        return {key: dict(broken) for key in _BLOCKS}

    sessions = {timestamp.date() for timestamp in bars.index}
    first_session = bars.index[0].date()
    # A window anchored on a session the frame never printed is not a window. Whether the
    # provider dropped that bar or the caller named a day the market was shut, the sessions
    # inside are unknown, and starting at the next bar would re-anchor the measurement
    # onto a session the trader did not name.
    if entry_date not in sessions:
        entry_gap = {"state": "unavailable", "reason": "history_starts_after_entry_date" if first_session > entry_date else "no_completed_bar_on_entry_date"}
        held_blocks = {key: dict(entry_gap) for key in _SINCE_ENTRY}
        if entry_gap["reason"] == "no_completed_bar_on_entry_date":
            # Nothing about this position's history can be trusted to the session level, so
            # even the measurements that do not look back to entry stay silent.
            return {key: dict(entry_gap) for key in _BLOCKS}
        return {
            "moving_average_trail": {**entry_gap, "selected": management_average},
            "twenty_day_average": _twenty_day_average(bars),
            "largest_decline_since_stage2_start": _largest_decline(bars, stage2_start=stage2_start),
            **held_blocks,
            "moving_average_extension": _moving_average_extension(bars),
            "climax": _climax(bars),
            "failed_volume_confirmation": _failed_volume_confirmation(bars, breakout_date=breakout_date, sessions=sessions, first_session=first_session),
        }
    breakout_gap: dict[str, Any] | None = None
    if breakout_date is not None and breakout_date not in sessions:
        breakout_gap = {"state": "unavailable", "reason": "history_starts_after_breakout_date" if first_session > breakout_date else "no_completed_bar_on_breakout_date"}
    return {
        "moving_average_trail": _moving_average_trail(bars, entry_date=entry_date, as_of=as_of, selected=management_average),
        "twenty_day_average": _twenty_day_average(bars),
        "largest_decline_since_stage2_start": _largest_decline(bars, stage2_start=stage2_start),
        "base_extension": _base_extension(bars, entry_date=entry_date, base_top=base_top),
        "moving_average_extension": _moving_average_extension(bars),
        "key_reversal": dict(breakout_gap) if breakout_gap else _key_reversal(bars, entry_date=entry_date, breakout_date=breakout_date),
        "gaps_since_breakout": dict(breakout_gap) if breakout_gap else _gaps_since_breakout(bars, entry_date=entry_date, breakout_date=breakout_date),
        "climax": _climax(bars),
        "failed_volume_confirmation": _failed_volume_confirmation(bars, breakout_date=breakout_date, sessions=sessions, first_session=first_session),
    }


__all__ = ["AVERAGES", "build_management_evidence"]
