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
_SINCE_ENTRY = ("base_extension", "key_reversal", "gaps_since_breakout", "post_breakout_behavior")
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
    "post_breakout_behavior",
    "stage3_transition",
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
_TENNIS_BALL = "management.tennis_ball_action_after_the_breakout"
_ACTS_AS_EXPECTED = "management.stock_that_does_not_act_as_expected"
_FIRST_SESSIONS = "management.zanger_first_two_days_out_of_the_base"
_STAGE3 = "stage.stage3_characteristics"
_SLOPE = "convention.long_average_slope_window"
_SPLIT_COLUMN = SPLIT_COLUMN = "Stock Splits"
_DISCONTINUITY = "convention.unexplained_price_discontinuity"
# Where this convention's numbers are published inside a canonical block, they carry their
# own claim and their own non-binding stamp: the baseline length and the low/high ratios
# are TraderLion's, not Minervini's, and a reader must be able to see whose they are.
_VOLUME_CONVENTION = {"doctrine_id": _VOLUME_STATE, "binds": False, "source": "[TL]"}
_CLOSING_RANGE = "setup.closing_range_formula"
# Enough places to strip binary-float noise from a reported figure and far too many to
# soften any limit the registry states.
_REPORTED_PRECISION = 10
AVERAGES = ("ema21", "sma50")


BLOCKS = _BLOCKS


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


def _moving_average_trail(bars: pd.DataFrame, *, entry_date: date, as_of: date, selected: str | None, readable: _Readable) -> dict[str, Any]:
    # An EMA is recursive from the first bar, so an unreadable close anywhere is inside its
    # computation; the simple average only reads its own window plus the audit's.
    gap = readable.gap(0, columns=("Close",)) or readable.split(0)
    if gap is not None:
        return {**gap, "selected": selected}
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


def _twenty_day_average(bars: pd.DataFrame, *, readable: _Readable) -> dict[str, Any]:
    length = int(doctrine.threshold(_TWENTY_DAY, "average_length_sessions"))
    gap = readable.gap(len(bars) - length, columns=("Close",)) or readable.split(len(bars) - length)
    if gap is not None:
        return {**gap, "doctrine_id": _TWENTY_DAY}
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
    # A weekly change spans from the previous week's close, so the week whose predecessor
    # ended before the advance began measures a decline that partly happened before it.
    previous_ends = list(weekly.index[:-1])
    inside = {end: previous for end, previous in zip(weekly.index[1:], previous_ends) if previous >= stage2_start}
    since = changes[[end in inside for end in changes.index]].dropna()
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
    # The first session of the advance measures its change from the session before it,
    # which is outside the advance; the decline of the advance starts one session later.
    previous_dates = [None, *dates[:-1]]
    since = changes[[previous is not None and previous >= stage2_start for previous in previous_dates]].dropna()
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
        "volume_convention": dict(_VOLUME_CONVENTION),
        "missing_inputs": [] if "Volume" in bars.columns else ["volume_history"],
        "largest_pct": _reported(largest),
        "date": stamp.date().isoformat(),
        "last_session_is_largest": stamp == bars.index[-1],
        "volume_ratio": _reported(ratio),
        "volume_baseline_sessions": baseline_sessions,
        "volume_signal": doctrine.evaluate_marker(_VOLUME_STATE, "high_volume_ratio", ratio),
    }


def _largest_decline(bars: pd.DataFrame, *, stage2_start: date | None, readable: _Readable) -> dict[str, Any]:
    if stage2_start is None:
        return {"state": "unavailable", "reason": "stage2_start_not_declared"}
    declared = stage2_start
    if stage2_start.weekday() >= 5:
        # A stage begins in an analyst's reading of the chart, not in a trade, so a weekend
        # anchor is a real anchor: the advance starts at the first session that could open
        # after it. Comparing the raw Saturday with a Monday history would report the
        # sessions before it as missing when none of them exist.
        stage2_start = stage2_start + timedelta(days=7 - stage2_start.weekday())
    anchored = [position for position, timestamp in enumerate(bars.index) if timestamp.date() >= stage2_start]
    gap = readable.gap(max(0, (anchored[0] if anchored else 0) - 1), columns=("Close",)) or readable.split(max(0, (anchored[0] if anchored else 0) - 1))
    if gap is not None:
        return {**gap, "doctrine_id": _LARGEST_DECLINE}
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


SMALLEST_RECOGNIZED_SPLIT_RATIO = float(doctrine.parameter(_DISCONTINUITY, "smallest_recognized_split_ratio"))


def split_sized_discontinuities(closes: Any) -> Any:
    """Which sessions moved too far from the session before them to be a move.

    A split is a discontinuity, so a history that omits its corporate actions still shows
    what one did: the close changes by the split ratio overnight. The harness cannot tell
    that from a fall the market actually made, and the two call for opposite answers -- one
    is arithmetic between two different shares, the other is a stop the tape took out. It
    refuses the window rather than guessing, at the ratio of the smallest ordinary split.
    """

    if closes is None:
        return None
    values = pd.to_numeric(closes, errors="coerce").to_numpy(dtype=float)
    if values.size < 2:
        return np.zeros(values.size, dtype=bool)
    previous, current = values[:-1], values[1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = current / previous
    usable = np.isfinite(ratio) & (previous > 0) & (current > 0)
    jumped = usable & ((ratio >= SMALLEST_RECOGNIZED_SPLIT_RATIO) | (ratio <= 1.0 / SMALLEST_RECOGNIZED_SPLIT_RATIO))
    # Marked on the session that printed the new coordinate system, the way a split event
    # is stamped on the session it took effect.
    return np.concatenate(([False], jumped))


class _Readable:
    """Which sessions the harness can read, asked one window at a time.

    A price of zero or NaN is not a cheap stock or a quiet session -- it is a bar the
    provider could not fill, and a measurement computed through it divides by nothing or
    silently compares false. But a bad bar only spoils the measurements that read it: a
    broken session from two years ago has nothing to do with the twenty-day average or
    with a position opened last week, and voiding those would hide evidence that is fine.
    So every block asks about its own lookback and no other.
    """

    def __init__(self, bars: pd.DataFrame) -> None:
        self._discontinuity_reason = "corporate_action_evidence_missing"
        self._bad: dict[str, Any] = {}
        for column, floor in (("Open", 0.0), ("High", 0.0), ("Low", 0.0), ("Close", 0.0), ("Volume", -1.0)):
            if column not in bars.columns:
                continue
            values = pd.to_numeric(bars[column], errors="coerce").to_numpy(dtype=float)
            self._bad[column] = ~np.isfinite(values) | (values <= floor)
        self._length = len(bars)
        self._bars = bars
        if _SPLIT_COLUMN in bars.columns:
            events = pd.to_numeric(bars[_SPLIT_COLUMN], errors="coerce").fillna(0).to_numpy(dtype=float)
            self._splits = (events != 0) & (events != 1)
            self._split_reason = "share_split_inside_window"
        else:
            # A history without the event column has not said there was no split. What a
            # hidden split does to these measurements is print a discontinuity, so the
            # closes are asked for one directly and the window is refused the same way.
            self._splits = split_sized_discontinuities(bars.get("Close"))
            self._split_reason = self._discontinuity_reason

    def split(self, start: int = 0, end: int | None = None) -> dict[str, Any] | None:
        """The unavailable block for a window a share split falls inside, or None.

        The provider returns the prices the tape printed, unadjusted, with the split events
        beside them. Across a split those prices are two coordinate systems: the entry and
        the stop the trader declared are in the old one and the closes are in the new one,
        so an average, a percentage or a level comparison spanning the event is arithmetic
        between two different shares. The harness does not restate the trade, so it names
        the session it cannot measure across instead of selling on the arithmetic.
        """

        if self._splits is None:
            return None
        window = self._splits[max(0, start) : self._length if end is None else end]
        if not bool(window.any()):
            return None
        position = max(0, start) + int(window.argmax())
        return {"state": "unavailable", "reason": self._split_reason, "date": self._bars.index[position].date().isoformat()}

    def gap(self, start: int = 0, end: int | None = None, columns: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")) -> dict[str, Any] | None:
        """The unavailable block for a window holding a session this reading cannot use, or None.

        Columns as well as sessions: a broken Volume has nothing to do with an average of
        closes, and voiding one because of the other hides a measurement that is fine.
        """

        first: int | None = None
        for column in columns:
            mask = self._bad.get(column)
            if mask is None:
                continue
            window = mask[max(0, start) : self._length if end is None else end]
            if bool(window.any()):
                position = max(0, start) + int(window.argmax())
                first = position if first is None else min(first, position)
        if first is None:
            return None
        return {"state": "unavailable", "reason": "invalid_ohlc_history", "date": self._bars.index[first].date().isoformat()}

    def clean_positions(self, positions: list[int], columns: tuple[str, ...] = ("Close",)) -> list[int]:
        return [position for position in positions if all(not self._bad.get(column, np.zeros(self._length, dtype=bool))[position] for column in columns)]


def _positions_since(bars: pd.DataFrame, since: date) -> list[int]:
    return [position for position, timestamp in enumerate(bars.index) if timestamp.date() >= since]


def _first_sessions(bars: pd.DataFrame, *, window: list[int]) -> dict[str, Any]:
    """The sessions the practitioner reads first, reported and never acted on."""

    length = int(doctrine.parameter(_FIRST_SESSIONS, "window_sessions"))
    start = window[0]
    baseline_sessions = int(doctrine.threshold(_VOLUME_STATE, "position_baseline_sessions"))
    baseline: float | None = None
    if "Volume" in bars.columns and start >= baseline_sessions:
        mean = float(bars["Volume"].iloc[start - baseline_sessions : start].mean())
        baseline = mean if math.isfinite(mean) and mean > 0 else None
    first_close = float(bars["Close"].iloc[start])
    sessions = []
    for position in window[:length]:
        close = float(bars["Close"].iloc[position])
        volume = _finite(bars["Volume"].iloc[position]) if "Volume" in bars.columns else None
        sessions.append(
            {
                "date": bars.index[position].date().isoformat(),
                "close": _reported(close),
                "close_vs_first_session_pct": _reported((close / first_close - 1) * 100 if first_close > 0 else None),
                "closing_range_pct": _reported(_closing_range_pct(bars.iloc[position])),
                "volume_ratio": _reported(volume / baseline if baseline and volume is not None else None),
            }
        )
    missing_inputs: list[str] = []
    if "Volume" not in bars.columns:
        missing_inputs.append("volume_history")
    elif baseline is None:
        missing_inputs.append("volume_baseline")
    return {
        "doctrine_id": _FIRST_SESSIONS,
        "binds": doctrine.binds(_FIRST_SESSIONS),
        "source": "Zanger",
        "window_sessions": length,
        "sessions_available": min(len(window), length),
        "volume_baseline_sessions": baseline_sessions if baseline is not None else None,
        "volume_convention": dict(_VOLUME_CONVENTION),
        "missing_inputs": missing_inputs,
        "volume_baseline_reason": None if baseline is not None else ("volume_history_unavailable" if "Volume" not in bars.columns else "insufficient_history_for_volume_baseline"),
        "sessions": sessions,
    }


def _natural_reactions(bars: pd.DataFrame, *, window: list[int]) -> list[dict[str, Any]]:
    """Every pullback from a closing high since the window opened, and how it ended.

    A reaction runs from the session that made a closing high to the lowest close before
    the next one. "Within just days" is the source's whole measurement, so each reaction
    carries its depth, how long it took to bottom, and how long recovery took -- or that
    it has not recovered -- and no threshold decides anything.
    """

    closes = bars["Close"].astype(float)
    reactions: list[dict[str, Any]] = []
    peak_position = window[0]
    peak = float(closes.iloc[peak_position])
    trough_position: int | None = None
    for position in window[1:]:
        close = float(closes.iloc[position])
        if close > peak:
            # Strictly above: a close that matches the peak is the stock failing to make a
            # new high, which is the opposite of the tennis ball bouncing back to one.
            if trough_position is not None:
                trough = float(closes.iloc[trough_position])
                reactions.append(
                    {
                        "peak_date": bars.index[peak_position].date().isoformat(),
                        "peak_close": _reported(peak),
                        "low_date": bars.index[trough_position].date().isoformat(),
                        "low_close": _reported(trough),
                        "depth_pct": _reported((trough / peak - 1) * 100),
                        "sessions_to_low": trough_position - peak_position,
                        "recovered_in_sessions": position - peak_position,
                        "sessions_since_peak": position - peak_position,
                    }
                )
            peak_position, peak, trough_position = position, close, None
            continue
        if close < peak and (trough_position is None or close < float(closes.iloc[trough_position])):
            # A session that closed level with the peak did not pull back, so it opens no
            # reaction: a flat stretch is not a zero-percent decline.
            trough_position = position
    if trough_position is not None:
        trough = float(closes.iloc[trough_position])
        reactions.append(
            {
                "peak_date": bars.index[peak_position].date().isoformat(),
                "peak_close": _reported(peak),
                "low_date": bars.index[trough_position].date().isoformat(),
                "low_close": _reported(trough),
                "depth_pct": _reported((trough / peak - 1) * 100),
                "sessions_to_low": trough_position - peak_position,
                "recovered_in_sessions": None,
                "sessions_since_peak": (len(bars) - 1) - peak_position,
            }
        )
    return reactions


def _post_breakout_behavior(bars: pd.DataFrame, *, entry_date: date, breakout_date: date | None, readable: _Readable) -> dict[str, Any]:
    # Every claim in this block is about what happens after a breakout -- the tennis ball
    # bouncing back to new highs, the first two sessions out of the base. Reading them from
    # the entry session instead would apply post-breakout doctrine to an early or cheat
    # entry that has not broken out yet, which is the same leak the 20-day rule had.
    if breakout_date is None:
        return {"state": "unavailable", "reason": "breakout_date_not_declared"}
    since, basis = breakout_date, "breakout_date"
    window = _positions_since(bars, since)
    if not window:
        return {"state": "unavailable", "reason": "insufficient_history_since_window_start"}
    baseline_sessions = int(doctrine.threshold(_VOLUME_STATE, "position_baseline_sessions"))
    gap = readable.gap(max(0, window[0] - baseline_sessions), columns=("Close", "Volume")) or readable.split(max(0, window[0] - baseline_sessions))
    if gap is not None:
        return {**gap, "doctrine_id": _TENNIS_BALL}
    closes = bars["Close"].astype(float)
    first_close = float(closes.iloc[window[0]])
    last_close = float(closes.iloc[-1])
    # Strictly higher than everything before it, for the same reason the reaction scan uses:
    # an equal retest is not a new high, and letting it reset the clock would report a stock
    # that has gone nowhere for a month as having made a new high today.
    last_high = window[0]
    running = float(closes.iloc[window[0]])
    for position in window[1:]:
        close = float(closes.iloc[position])
        if close > running:
            running, last_high = close, position
    return {
        "doctrine_id": _TENNIS_BALL,
        "doctrine_ids": [_TENNIS_BALL, _ACTS_AS_EXPECTED, _FIRST_SESSIONS],
        "binds": doctrine.binds(_TENNIS_BALL),
        "state": "reported",
        "since": since.isoformat(),
        "since_basis": basis,
        "sessions_since_entry": len(_positions_since(bars, entry_date)) - 1,
        "sessions_since_new_high": (len(bars) - 1) - last_high,
        "last_new_closing_high": bars.index[last_high].date().isoformat(),
        "gain_since_first_session_pct": _reported((last_close / first_close - 1) * 100 if first_close > 0 else None),
        "first_sessions": _first_sessions(bars, window=window),
        "natural_reactions": _natural_reactions(bars, window=window),
        "needs_chart": True,
    }


def _stage3_transition(bars: pd.DataFrame, *, readable: _Readable) -> dict[str, Any]:
    """Rising volatility and a flattening long average, measured; the reading stays the analyst's."""

    length = int(doctrine.parameter(_ATR, "atr_length_sessions"))
    sma_length = int(doctrine.parameter(_SLOPE, "long_average_sessions"))
    lookback = int(doctrine.parameter(_SLOPE, "slope_lookback_sessions"))
    gap = readable.gap(len(bars) - (sma_length + lookback), columns=("High", "Low", "Close")) or readable.split(len(bars) - (sma_length + lookback))
    if gap is not None:
        return {**gap, "doctrine_id": _STAGE3}
    recent = _average_true_range(bars)
    earlier = _average_true_range(bars.iloc[: len(bars) - length]) if len(bars) > 2 * length + 1 else {"state": "unavailable", "reason": "insufficient_history_for_comparison"}
    ratio: float | None = None
    if recent.get("value") and earlier.get("value"):
        ratio = float(recent["value"]) / float(earlier["value"])
    closes = bars["Close"].astype(float)
    slope: float | None = None
    state = "unavailable"
    if len(bars) >= sma_length + lookback:
        average = closes.rolling(sma_length).mean()
        now, before = float(average.iloc[-1]), float(average.iloc[-1 - lookback])
        if math.isfinite(now) and math.isfinite(before) and before > 0:
            slope = (now / before - 1) * 100
            state = "reported"
    return {
        "doctrine_id": _STAGE3,
        "doctrine_ids": [_STAGE3, _ATR, _SLOPE],
        "binds": doctrine.binds(_STAGE3),
        "state": "reported",
        "average_true_range": recent,
        "earlier_average_true_range": earlier,
        "volatility_ratio": _reported(ratio),
        "sma200_slope_pct": _reported(slope),
        "sma200_average_sessions": sma_length,
        "sma200_lookback_sessions": lookback,
        "sma200_state": state,
        "needs_chart": True,
    }


def _base_extension(bars: pd.DataFrame, *, entry_date: date, base_top: float | None, readable: _Readable) -> dict[str, Any]:
    if base_top is None:
        return {"state": "unavailable", "reason": "base_top_not_declared"}
    held_positions = _positions_since(bars, entry_date)
    gap = readable.gap(held_positions[0] if held_positions else 0, columns=("High", "Close")) or readable.split(held_positions[0] if held_positions else 0)
    if gap is not None:
        return {**gap, "doctrine_id": _PAUSE_ZONE}
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


def _moving_average_extension(bars: pd.DataFrame, *, readable: _Readable) -> dict[str, Any]:
    ema_length = int(doctrine.threshold(_ROLES, "ema_length_sessions"))
    sma_length = int(doctrine.threshold(_ROLES, "sma_length_sessions"))
    atr_length = int(doctrine.parameter(_ATR, "atr_length_sessions"))
    gap = readable.gap(0, columns=("Close",)) or readable.gap(len(bars) - (sma_length + atr_length + 1), columns=("High", "Low", "Close")) or readable.split(0)
    if gap is not None:
        return {**gap, "doctrine_id": _OWN_CHARACTER}
    closes = bars["Close"].astype(float)
    atr = _average_true_range(bars)
    atr_value = atr.get("value")
    # No warm-up mask here: the length guard below already refuses a history shorter than
    # the average, and every position this block reads starts at the average's own warm-up.
    # A mutation probe proved a mask changes nothing, which makes it a line that looks like
    # a rule and is not one.
    ema = closes.ewm(span=ema_length, adjust=False).mean()
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
            for position in readable.clean_positions(list(range(length - 1, len(bars) - 1)))
            if math.isfinite(float(series.iloc[position])) and float(series.iloc[position]) > 0
        ]
        percentile = (sum(1 for value in prior if value <= extension_pct) / len(prior) * 100) if prior else None
        block[name] = {
            "extension_pct": _reported(extension_pct),
            "extension_atr": _reported((close - average) / atr_value if atr_value else None),
            "historical_percentile": _reported(percentile),
            "history_sessions": len(prior),
        }
    return block


def _key_reversal(bars: pd.DataFrame, *, entry_date: date, breakout_date: date | None, readable: _Readable) -> dict[str, Any]:
    if breakout_date is None:
        return {"state": "unavailable", "reason": "breakout_date_not_declared"}
    since, basis = breakout_date, "breakout_date"
    window = _positions_since(bars, since)
    if len(bars) < 2 or not window:
        return {"state": "unavailable", "reason": "insufficient_history_since_window_start"}
    # The prior session is part of the reading: the gap and the prior low come from it.
    gap = readable.gap(max(0, window[0] - 1)) or readable.split(max(0, window[0] - 1))
    if gap is not None:
        return {**gap, "doctrine_id": _KEY_REVERSAL}
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
        # The source asks for one thing here: reversed below the prior low AND closed low in
        # the range. "Low in the range" has no boundary in the source, so the pair stays
        # unresolved and is not counted among the criteria met.
        "reversed_below_prior_low_and_closed_low_in_range": None,
        "closing_range_pct": _reported(_closing_range_pct(bars.iloc[last])),
        "visually_extended": None,
        "trend_line_of_highs_breached": None,
    }
    computable = sum(1 for name in ("gap_up_filled_and_reversed", "highest_volume_since", "widest_range_since") if features[name] is True)
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
        "computable_criteria": 3,
        "unresolved_criteria": ["visually_extended", "trend_line_of_highs_breached", "reversed_below_prior_low_and_closed_low_in_range"],
        "needs_chart": True,
    }


def _gaps_since_breakout(bars: pd.DataFrame, *, entry_date: date, breakout_date: date | None, readable: _Readable) -> dict[str, Any]:
    if breakout_date is None:
        return {"state": "unavailable", "reason": "breakout_date_not_declared"}
    since, basis = breakout_date, "breakout_date"
    if "Open" not in bars.columns:
        return {"state": "unavailable", "reason": "open_history_unavailable"}
    window = _positions_since(bars, since)
    if not window:
        return {"state": "unavailable", "reason": "insufficient_history_since_window_start"}
    gap = readable.gap(max(0, window[0] - 1)) or readable.split(max(0, window[0] - 1))
    if gap is not None:
        return {**gap, "doctrine_id": _LATE_GAPS}
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


def _climax(bars: pd.DataFrame, *, readable: _Readable) -> dict[str, Any]:
    closes = bars["Close"].astype(float)
    lengths = [int(doctrine.parameter(_WINDOWS, name)) for name in ("short_window_sessions", "medium_window_sessions", "long_window_sessions")]
    gap_window = int(doctrine.parameter(_WINDOWS, "medium_window_sessions"))
    gap = readable.gap(len(bars) - (max(lengths) + 1)) or readable.split(len(bars) - (max(lengths) + 1))
    if gap is not None:
        return {**gap, "doctrine_id": _CLIMAX}
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


def _failed_volume_confirmation(bars: pd.DataFrame, *, breakout_date: date | None, sessions: set[date], first_session: date, readable: _Readable) -> dict[str, Any]:
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
    gap = readable.gap(max(0, breakout - baseline_sessions), columns=("Close", "Volume")) or readable.split(max(0, breakout - baseline_sessions))
    if gap is not None:
        return {**gap, "doctrine_id": _FAILED_VOLUME}
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
    breakout_signal = doctrine.evaluate_marker(_VOLUME_STATE, "low_volume_ratio", breakout_ratio)
    selling_signal = doctrine.evaluate_marker(_VOLUME_STATE, "high_volume_ratio", heaviest[1]) if heaviest else None
    # The source names two qualities in one sentence -- the breakout came on low volume, the
    # selling afterwards came on high volume -- and neither has a boundary anywhere in the
    # corpus. The only value here the bars can settle is the comparison between the two
    # sessions, measured against one baseline; "low" and "high" stay the reader's, with the
    # practice-layer marker's distance printed beside each so they have something to read.
    heavier_than_the_breakout = bool(heaviest is not None and heaviest[1] > breakout_ratio)
    return {
        "doctrine_id": _FAILED_VOLUME,
        "binds": doctrine.binds(_FAILED_VOLUME),
        "state": "reported",
        "breakout_date": bars.index[breakout].date().isoformat(),
        "volume_baseline_sessions": baseline_sessions,
        "volume_convention": dict(_VOLUME_CONVENTION),
        "breakout_volume_ratio": _reported(breakout_ratio),
        "breakout_volume_signal": breakout_signal,
        "heaviest_down_session": {"date": bars.index[heaviest[0]].date().isoformat(), "volume_ratio": _reported(heaviest[1]), "signal": selling_signal} if heaviest else None,
        "selling_volume_exceeded_breakout_volume": heavier_than_the_breakout,
        "qualitative_conditions_unresolved": ["breakout_was_on_low_volume", "selling_was_on_high_volume"],
        "resolved_by_bars": False,
        "needs_chart": True,
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
    readable = _Readable(bars)
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
            "twenty_day_average": _twenty_day_average(bars, readable=readable),
            "largest_decline_since_stage2_start": _largest_decline(bars, stage2_start=stage2_start, readable=readable),
            **held_blocks,
            "moving_average_extension": _moving_average_extension(bars, readable=readable),
            "climax": _climax(bars, readable=readable),
            "stage3_transition": _stage3_transition(bars, readable=readable),
            "failed_volume_confirmation": _failed_volume_confirmation(bars, breakout_date=breakout_date, sessions=sessions, first_session=first_session, readable=readable),
        }
    breakout_gap: dict[str, Any] | None = None
    if breakout_date is not None and breakout_date not in sessions:
        breakout_gap = {"state": "unavailable", "reason": "history_starts_after_breakout_date" if first_session > breakout_date else "no_completed_bar_on_breakout_date"}
    return {
        "moving_average_trail": _moving_average_trail(bars, entry_date=entry_date, as_of=as_of, selected=management_average, readable=readable),
        "twenty_day_average": _twenty_day_average(bars, readable=readable),
        "largest_decline_since_stage2_start": _largest_decline(bars, stage2_start=stage2_start, readable=readable),
        "base_extension": _base_extension(bars, entry_date=entry_date, base_top=base_top, readable=readable),
        "moving_average_extension": _moving_average_extension(bars, readable=readable),
        "key_reversal": dict(breakout_gap) if breakout_gap else _key_reversal(bars, entry_date=entry_date, breakout_date=breakout_date, readable=readable),
        "gaps_since_breakout": dict(breakout_gap) if breakout_gap else _gaps_since_breakout(bars, entry_date=entry_date, breakout_date=breakout_date, readable=readable),
        "climax": _climax(bars, readable=readable),
        "failed_volume_confirmation": _failed_volume_confirmation(bars, breakout_date=breakout_date, sessions=sessions, first_session=first_session, readable=readable),
        "post_breakout_behavior": dict(breakout_gap) if breakout_gap else _post_breakout_behavior(bars, entry_date=entry_date, breakout_date=breakout_date, readable=readable),
        "stage3_transition": _stage3_transition(bars, readable=readable),
    }


__all__ = ["AVERAGES", "build_management_evidence"]
