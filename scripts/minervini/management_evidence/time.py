"""Post-breakout and time-window behavior measurements."""

from __future__ import annotations

import math
from datetime import date
from typing import Any
import pandas as pd
from ..numbers import finite_or_none as _finite
from .. import doctrine

from .readings import _CLOSING_RANGE, _Readable, _VOLUME_CONVENTION, _VOLUME_STATE, _closing_range, _positions_since, _reported, _unread_claim_inputs


_LATE_GAPS = "management.tl_late_gaps_fail_more_often"
_FAILED_VOLUME = "management.low_volume_breakout_then_high_volume_selling"
_TENNIS_BALL = "management.tennis_ball_action_after_the_breakout"
_ACTS_AS_EXPECTED = "management.stock_that_does_not_act_as_expected"
_FIRST_SESSIONS = "management.zanger_first_two_days_out_of_the_base"


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
                **_closing_range(bars.iloc[position]),
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
    # Closes over the whole window, volume only where volume is reported: the baseline before
    # the breakout and the first sessions out of it. A NaN volume last Friday is read by
    # nothing here, and voiding the tennis-ball reading over it hides evidence that is fine.
    first_sessions_length = int(doctrine.parameter(_FIRST_SESSIONS, "window_sessions"))
    gap = (
        readable.gap(window[0], columns=("Close",))
        or readable.gap(max(0, window[0] - baseline_sessions), window[0] + first_sessions_length, columns=("Volume",))
        or readable.split(max(0, window[0] - baseline_sessions))
    )
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
        "claim_inputs_not_read": _unread_claim_inputs((_TENNIS_BALL, _ACTS_AS_EXPECTED, _FIRST_SESSIONS), ("price_history", "breakout_date", "entry_date")),
        "sessions_since_entry": len(_positions_since(bars, entry_date)) - 1,
        "sessions_since_new_high": (len(bars) - 1) - last_high,
        "last_new_closing_high": bars.index[last_high].date().isoformat(),
        "gain_since_first_session_pct": _reported((last_close / first_close - 1) * 100 if first_close > 0 else None),
        "first_sessions": _first_sessions(bars, window=window),
        "natural_reactions": _natural_reactions(bars, window=window),
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
    # Prices only: this block compares one session's Open with the session before it and
    # measures the run since the breakout. A broken Volume has nothing to do with either,
    # and neither does a close in the middle of the window -- the only close opened is the
    # breakout's, plus whichever sessions turn out to have gapped.
    gap = (
        readable.gap(max(0, window[0] - 1), columns=("Open", "High", "Low"))
        or readable.missing_at([window[0]], ("Close",))
        or readable.split(max(0, window[0] - 1))
    )
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
        latest = {"date": bars.index[gap].date().isoformat(), "filled": filled, **_closing_range(bars.iloc[gap])}
    breakout_close = float(closes.iloc[window[0]])
    return {
        "doctrine_id": _LATE_GAPS,
        "doctrine_ids": [_LATE_GAPS, _CLOSING_RANGE],
        "binds": doctrine.binds(_LATE_GAPS),
        "state": "reported",
        "since": since.isoformat(),
        "since_basis": basis,
        # The session bar is opened only by the latest gap's closing range. With no gap since
        # the breakout there is no such session, and citing the formula while naming nothing
        # unread would say this reading covered a claim it never reached.
        "claim_inputs_not_read": _unread_claim_inputs((_LATE_GAPS, _CLOSING_RANGE), ("price_history", "breakout_date", *(("daily_bar",) if latest is not None else ()))),
        "gap_up_count": len(gap_positions),
        "gap_dates": [bars.index[position].date().isoformat() for position in gap_positions],
        "run_pct_since_breakout": _reported((max(float(highs.iloc[position]) for position in window) / breakout_close - 1) * 100 if breakout_close > 0 else None),
        "latest_gap": latest,
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
    # The baseline is a population and is read whole; the closes start at the breakout,
    # because the first comparison is the session after it against it. A close before the
    # baseline is outside both.
    gap = (
        readable.gap(max(0, breakout - baseline_sessions), breakout + 1, columns=("Volume",))
        or readable.gap(breakout, columns=("Close",))
        or readable.split(max(0, breakout - baseline_sessions))
    )
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
    # Only the sessions that fell have their volume read, so those are the cells guarded --
    # a hole in an up session's volume is a bar this reading never opens.
    down_positions = [position for position in range(breakout + 1, len(bars)) if float(closes.iloc[position]) < float(closes.iloc[position - 1])]
    unreadable = readable.missing_at(down_positions, ("Volume",))
    if unreadable is not None:
        return {**unreadable, "doctrine_id": _FAILED_VOLUME}
    down = [(position, float(volumes.iloc[position]) / baseline) for position in down_positions]
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
        "claim_inputs_not_read": _unread_claim_inputs((_FAILED_VOLUME, _VOLUME_STATE), ("price_history", "volume_history", "breakout_date", "daily_volume")),
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
