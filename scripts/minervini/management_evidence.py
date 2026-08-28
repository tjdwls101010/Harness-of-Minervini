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
# Enough places to strip binary-float noise from a reported figure and far too many to
# soften any limit the registry states.
_REPORTED_PRECISION = 10
AVERAGES = ("ema21", "sma50")


BLOCKS = _BLOCKS


def _unread_claim_inputs(claim_ids: tuple[str, ...], consumed: tuple[str, ...]) -> list[str]:
    """Which of the cited claims' required inputs this reading never consumes.

    Derived rather than written down beside each block, because a hand-kept list is the one
    thing that can disagree with the claim it is describing -- and a citation that reads as
    covering the whole claim while measuring half of it is exactly the contradiction this
    evidence pack exists to prevent. A block names what it opened; this names the rest.
    """

    required = {name for claim_id in claim_ids for name in doctrine.required_inputs(claim_id)}
    return sorted(required - set(consumed))


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
        # The zone is dropped and the wall clock kept, which is what `setup_structure.read_bars`
        # does and therefore what every session date in this harness means. Converting instead
        # renamed a UTC-stamped session to the day before, and a breach was recorded against a
        # session nothing else agrees exists.
        timestamps = timestamps.tz_localize(None)
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


def _closing_range(row: pd.Series) -> dict[str, Any]:
    """The closing range with the marker the source named beside it.

    The registry records the midpoint as a marker: a value named for comparison and never
    bounded, so what it produces is the measurement and its distance from that value. A
    bare percentage published under this claim would be a number citing a limit it never
    reported against.
    """

    measured = _closing_range_pct(row)
    return {
        "closing_range_pct": _reported(measured),
        "closing_range_marker": doctrine.evaluate_marker(_CLOSING_RANGE, "closing_range_midpoint_pct", measured),
        # Which of the session's own values the range could not be computed from. A null
        # beside no reason reads as a session with no range, which is not what happened.
        "closing_range_missing_inputs": [name for name, value in (("session_high", row["High"]), ("session_low", row["Low"]), ("session_close", row["Close"])) if _finite(value) is None],
    }


def _first_trouble(readable: _Readable, start: int) -> tuple[int | None, dict[str, Any] | None]:
    """The first session an average cannot be computed through, and how to say so.

    Two kinds of trouble bound an audit the same way. A split makes the closes on either
    side of it two coordinate systems; an unreadable close leaves the average nothing to be
    an average of from that session on. Neither reaches backwards -- the values before it
    were computed from readable closes in one coordinate system -- so both are a session
    the audit stops at rather than a reason to void the window and lose a declared exit
    that had already triggered.
    """

    split = readable.split_position(start)
    hole = readable.gap_position(start, columns=("Close",))
    if split is None and hole is None:
        return None, None
    if hole is None or (split is not None and split <= hole):
        return split, readable.split(start)
    return hole, readable.gap(start, columns=("Close",))


def _trail(bars: pd.DataFrame, average: pd.Series, *, length: int, entry_date: date, as_of: date, refuse_from: int | None = None, refusal: dict[str, Any] | None = None) -> dict[str, Any]:
    """Two completed closes below one management average, audited from the entry session.

    Both closes have to be the position's own: a close under the average the session before
    entry is the bar the trader bought into, not a violation of the plan they bought with. A
    breach, once found, stands for the rest of the window the way a stop breach does -- the
    source's rule is that the position is closed at that moment, and a later recovery is
    something a position that no longer exists cannot benefit from.
    """

    dates = [timestamp.date() for timestamp in bars.index]
    window = [position for position, day in enumerate(dates) if entry_date <= day <= as_of]
    # A session the averages cannot be read across ends the audit there. The sessions before
    # it were read in the trader's own coordinate system, and an exit those closes already
    # triggered is an exit that happened: a split three weeks later cannot un-trigger it.
    if refuse_from is not None:
        window = [position for position in window if position < refuse_from]
    if not window:
        return refusal if refusal is not None else {"state": "unavailable", "reason": "no_completed_bars_since_entry"}
    if window[0] < length - 1 or any(not math.isfinite(float(average.iloc[position])) for position in window):
        return refusal if refusal is not None else {"state": "unavailable", "reason": "insufficient_history_for_average", "sessions_required": length}
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
    if breach is None and refusal is not None:
        # Nothing had happened yet when the audit had to stop, and what came after is in
        # another coordinate system: the reading is refused rather than called clear. The
        # sessions that were read are named, so a refusal is not mistaken for a window
        # nothing was examined in.
        return {**refusal, "audited_from": dates[window[0]].isoformat(), "through": dates[window[-1]].isoformat(), "bars_checked": len(window)}
    last = window[-1]
    last_average = float(average.iloc[last])
    quality: dict[str, Any] | None = None
    if breach is not None:
        first = breach - 1
        second_close = float(closes.iloc[breach])
        quality = {
            "close_distance_pct": _reported((second_close - float(average.iloc[breach])) / float(average.iloc[breach]) * 100),
            **_closing_range(bars.iloc[breach]),
            "second_close_above_first_close": second_close > float(closes.iloc[first]),
            # A Low the provider never filled answers nothing. Comparing against NaN returns
            # False, which reads as "the second close did not hold the first session's low"
            # -- a finding about the stock, from a bar that was never there.
            "second_close_above_first_low": None if _finite(lows.iloc[first]) is None else second_close > float(lows.iloc[first]),
        }
        missing = ["first_session_low"] if _finite(lows.iloc[first]) is None else []
        missing += [f"breach_{name}" for name in quality["closing_range_missing_inputs"]]
        if missing:
            quality["missing_inputs"] = missing
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
    ema_length = int(doctrine.threshold(_ROLES, "ema_length_sessions"))
    sma_length = int(doctrine.threshold(_ROLES, "sma_length_sessions"))
    # An EMA is recursive from the first bar, so an unreadable close anywhere is inside its
    # computation. The simple average reads only its own window: the sessions the audit
    # covers plus the length it averages over, and a split two years before the position
    # is outside every value it uses. Asking one question for both would withhold a
    # measurement that is fine and turn a readable HOLD into INCOMPLETE.
    audited = [position for position, timestamp in enumerate(bars.index) if timestamp.date() >= entry_date]
    sma_start = max(0, (audited[0] if audited else len(bars)) - sma_length + 1)
    # Where the trouble starts, so each audit can read the sessions before it: a declared
    # exit those closes already triggered is an exit that happened, and neither an event
    # nor a hole three weeks later can take it back.
    ema_stop, ema_gap = _first_trouble(readable, 0)
    sma_stop, sma_gap = _first_trouble(readable, sma_start)
    closes = bars["Close"].astype(float)
    # The recursive form (adjust=False) is the exponential average charts draw; the
    # adjusted form weights a short history differently and would disagree with the chart.
    ema = closes.ewm(span=ema_length, adjust=False).mean()
    ema.iloc[: ema_length - 1] = float("nan")
    sma = closes.rolling(sma_length).mean()
    ema21 = _trail(bars, ema, length=ema_length, entry_date=entry_date, as_of=as_of, refuse_from=ema_stop, refusal=ema_gap)
    sma50 = _trail(bars, sma, length=sma_length, entry_date=entry_date, as_of=as_of, refuse_from=sma_stop, refusal=sma_gap)
    def refused(result: dict[str, Any], record: dict[str, Any] | None) -> bool:
        return record is not None and result.get("state") == "unavailable" and result.get("reason") == record.get("reason")

    if sma_gap is not None and refused(sma50, sma_gap) and (ema_gap is None or refused(ema21, ema_gap)):
        # Nothing was found before the event on either average, so the block has nothing to
        # report and says so once, in the shape a reader of an unreadable block expects --
        # carrying the sessions the audit did read before it stopped.
        return {**sma50, "selected": selected}
    return {
        "doctrine_id": _ROLES,
        "binds": doctrine.binds(_ROLES),
        "selected": selected,
        "claim_inputs_not_read": _unread_claim_inputs((_ROLES,), ("daily_ema_21", "sma_50", "management_mode")),
        "ema21": ema21,
        "sma50": sma50,
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
        "claim_inputs_not_read": _unread_claim_inputs((_TWENTY_DAY,), ("price_history", "sma_20")),
        "state": "below" if close < average else "above",
        "date": bars.index[-1].date().isoformat(),
        "average": _reported(average),
        "close": _reported(close),
        "close_distance_pct": _reported((close - average) / average * 100),
    }


def _latest_tie(series: pd.Series, value: float) -> Any:
    """The index label of the last element that publishes as ``value``.

    Equality is asked of the reported figure rather than the raw binary one. Two declines
    that are the same decline can land on adjacent floats -- the same ratio reached by
    different multiplications -- and both print as the same percentage. Dating the finding
    at the earlier of them because their last bits differ is a tie the reader can see and
    the code could not.
    """

    reported = _reported(value)
    positions = [position for position, element in enumerate(series) if _reported(float(element)) == reported]
    return series.index[positions[-1]]


def _weekly(bars: pd.DataFrame, *, stage2_start: date, readable: _Readable) -> dict[str, Any]:
    closes = bars["Close"].astype(float)
    # A week is a completed bar once its Friday has printed or a later week has begun;
    # the week as_of falls inside is still being drawn and is not compared.
    periods = closes.index.to_period("W-FRI")
    # The weekly reading opens one session per week: the last one in it. The first week it
    # weighs is the first whose Friday falls on or after the advance began -- which a
    # holiday can leave ending on a session before that date, so the start is asked of the
    # weeks themselves rather than assumed to be the anchor.
    last_of = {period: position for position, period in enumerate(periods)}
    first_read = min((position for period, position in last_of.items() if period.end_time.date() >= stage2_start), default=0)
    gap = readable.missing_at([position for position in last_of.values() if position >= first_read], ("Close",))
    if gap is not None:
        return gap
    last_of_week = closes.groupby(periods).tail(1)
    week_ends = [period.end_time.normalize().date() for period in last_of_week.index.to_period("W-FRI")]
    completed = [
        index < len(last_of_week) - 1 or timestamp.weekday() == 4
        for index, timestamp in enumerate(last_of_week.index)
    ]
    weekly = pd.Series(last_of_week.to_numpy(), index=pd.Index(week_ends))
    # The week left out and what it did. Without a trading calendar the harness cannot tell
    # a week that ended early on a holiday from one whose Friday has not printed yet, so it
    # does not promote the trailing week to completed. Publishing it beside the finding is
    # the difference between a week that was weighed and found smaller and one that was
    # never weighed: a reader comparing "the latest completed week is not the largest" with
    # a twenty percent week the block dropped needs to see that week here.
    pending: dict[str, Any] = {}
    if completed and not completed[-1] and len(weekly) >= 2:
        change = (float(weekly.iloc[-1]) - float(weekly.iloc[-2])) / float(weekly.iloc[-2]) * 100 if float(weekly.iloc[-2]) > 0 else None
        pending = {
            "pending_week_ending": weekly.index[-1].isoformat(),
            "pending_week_pct": None if change is None else _reported(change),
            "pending_week_reason": "no_friday_session_and_no_later_week",
        }
    weekly = weekly[completed]
    if len(weekly) < 2:
        return {"state": "unavailable", "reason": "fewer_than_two_completed_weeks", **pending}
    changes = weekly.pct_change() * 100
    # A weekly change spans from the previous week's close, so the week whose predecessor
    # ended before the advance began measures a decline that partly happened before it.
    previous_ends = list(weekly.index[:-1])
    inside = {end: previous for end, previous in zip(weekly.index[1:], previous_ends) if previous >= stage2_start}
    since = changes[[end in inside for end in changes.index]].dropna()
    if since.empty:
        return {"state": "unavailable", "reason": "no_completed_week_since_stage2_start", **pending}
    largest = float(since.min())
    latest_end = weekly.index[-1]
    if largest >= 0:
        return {"state": "reported", "largest_pct": None, "week_ending": latest_end.isoformat(), "latest_completed_week_is_largest": False, **pending}
    largest_end = _latest_tie(since, largest)
    return {
        "state": "reported",
        "largest_pct": _reported(largest),
        "largest_week_ending": largest_end.isoformat(),
        "week_ending": latest_end.isoformat(),
        "latest_completed_week_is_largest": largest_end == latest_end,
        **pending,
    }


def _daily(bars: pd.DataFrame, *, stage2_start: date, readable: _Readable) -> dict[str, Any]:
    closes = bars["Close"].astype(float)
    # The advance's first change is measured from its own first session, so the close before
    # the anchor is outside every reading here.
    anchored = [position for position, timestamp in enumerate(bars.index) if timestamp.date() >= stage2_start]
    gap = readable.gap(anchored[0] if anchored else len(bars), columns=("Close",))
    if gap is not None:
        return gap
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
    # Which absence this is. The column missing is a history that never carried volume; a
    # position too early, a hole among the fifty, or a split inside them is a baseline that
    # cannot be averaged -- pandas would skip the hole and divide by the sessions that were
    # there, publishing a ratio against a yardstick nobody can reproduce, and across a split
    # it would compare share counts. A baseline is a population, so it is read whole or not
    # at all, and the two absences are named apart.
    missing_input = "volume_history" if "Volume" not in bars.columns else None
    if missing_input is None:
        if position < baseline_sessions:
            missing_input = "volume_baseline"
        elif readable.gap(position - baseline_sessions, position, columns=("Volume",)) is not None or readable.split(position - baseline_sessions, position + 1) is not None:
            missing_input = "volume_baseline"
        else:
            baseline = float(bars["Volume"].iloc[position - baseline_sessions : position].mean())
            volume = _finite(bars["Volume"].iloc[position])
            if volume is None:
                missing_input = "volume_history"
            elif not math.isfinite(baseline) or baseline <= 0:
                missing_input = "volume_baseline"
            else:
                ratio = volume / baseline
    return {
        "state": "reported",
        "volume_convention": dict(_VOLUME_CONVENTION),
        # The column being present is not the same as this session's volume being readable,
        # and neither is the same as the fifty sessions behind it being averageable. A block
        # reporting no missing inputs beside a null ratio says the volume was read and had
        # nothing to say, which is a third thing again.
        "missing_inputs": [] if missing_input is None else [missing_input],
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
    # A percentage across a split is arithmetic between two different shares, so the event
    # refuses the whole block. Which closes each reading opens is the readings' own
    # question, asked below -- the daily one starts at the advance's first session and the
    # weekly one at the last session of its first week, and neither is the other's window.
    gap = readable.split(anchored[0] if anchored else 0)
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
    daily = _daily(bars, stage2_start=stage2_start, readable=readable)
    weekly = _weekly(bars, stage2_start=stage2_start, readable=readable)
    if daily.get("state") == "unavailable" and weekly.get("state") == "unavailable":
        # Neither timeframe produced a decline, so the block measured nothing. Saying
        # "reported" over two holes publishes a reading a reader can compare against a
        # depth band when no depth was read, and an empty answer is not a shallow one.
        return {
            "state": "unavailable",
            "reason": "no_readable_timeframe_since_stage2_start",
            "doctrine_id": _LARGEST_DECLINE,
            "stage2_start": declared.isoformat(),
            "measured_from": stage2_start.isoformat(),
            "daily": daily,
            "weekly": weekly,
        }
    return {
        "doctrine_id": _LARGEST_DECLINE,
        "binds": doctrine.binds(_LARGEST_DECLINE),
        "state": "reported",
        "stage2_start": declared.isoformat(),
        "measured_from": stage2_start.isoformat(),
        "daily": daily,
        "weekly": weekly,
        "claim_inputs_not_read": _unread_claim_inputs((_LARGEST_DECLINE, _VOLUME_STATE), ("price_history", "volume_history", "stage2_start", "daily_volume")),
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


def impossible_bar_relations(bars: pd.DataFrame) -> Any:
    """Which sessions report a price outside the range that session claims to have had.

    A close under its own low, an open above its own high, a high beneath its own low --
    none of these is a session that happened, and no reading can decide which of the four
    numbers is the wrong one. The point is not tidiness. The audits read Lows and the
    current price is the Close, so a bar like this hands one reader a window that came
    through clear and the other a price far under the stop, and the verdict then contradicts
    the record printed beside it. So the whole bar is unusable, the way a NaN is.
    """

    columns = {name: pd.to_numeric(bars[name], errors="coerce").to_numpy(dtype=float) for name in ("Open", "High", "Low", "Close") if name in bars.columns}
    if "High" not in columns or "Low" not in columns:
        return None
    # Only prices that are prices take part. A zero or a NaN in one column is already that
    # column's own unreadable value, and letting it fail the relation test as well would
    # make one broken cell void the whole bar -- the opposite of the rule that a bad Volume
    # does not spoil a count of Opens. What is left is a genuine contradiction: four usable
    # numbers that cannot all be true of one session.
    usable = {name: (np.isfinite(value) & (value > 0)) for name, value in columns.items()}
    high, low = columns["High"], columns["Low"]
    broken = np.zeros(len(bars), dtype=bool)
    # A high beneath its own low needs no separate test: any close inside the frame is then
    # either above that high or below that low, so the containment test below catches it.
    for name in ("Open", "Close"):
        value = columns.get(name)
        if value is None:
            continue
        inside = usable[name]
        broken = broken | (inside & usable["High"] & (value > high)) | (inside & usable["Low"] & (value < low))
    return broken


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
        relations = impossible_bar_relations(bars)
        if relations is not None:
            for column in self._bad:
                self._bad[column] = self._bad[column] | relations
        self._length = len(bars)
        self._bars = bars
        if _SPLIT_COLUMN in bars.columns:
            events = pd.to_numeric(bars[_SPLIT_COLUMN], errors="coerce").to_numpy(dtype=float)
            # A blank event cell has not said there was no split. Left as NaN it fails both
            # comparisons below and so is uncrossable already; filling it with a zero would
            # turn missing evidence into an assertion of absence, and the session beside it
            # can carry a split-sized fall the window would then measure across. Which of
            # the two it was is kept separately, because they are refused under different
            # reasons -- a declared event, or evidence the provider never gave.
            self._splits = (events != 0) & (events != 1)
            self._unreadable_events = ~np.isfinite(events)
            self._split_reason = "share_split_inside_window"
        else:
            # A history without the event column has not said there was no split. What a
            # hidden split does to these measurements is print a discontinuity, so the
            # closes are asked for one directly and the window is refused the same way.
            self._splits = split_sized_discontinuities(bars.get("Close"))
            self._unreadable_events = None
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

        found = self.split_position(start, end)
        if found is None:
            return None
        blank = self._unreadable_events is not None and bool(self._unreadable_events[found])
        reason = self._discontinuity_reason if blank else self._split_reason
        return {"state": "unavailable", "reason": reason, "date": self._bars.index[found].date().isoformat()}

    def split_position(self, start: int = 0, end: int | None = None) -> int | None:
        """Where in the frame the window's first uncrossable session sits, or None.

        An audit that must refuse a window can still have read the sessions before the
        event honestly, so the position is published as well as the refusal.
        """

        if self._splits is None:
            return None
        # From the session after the window opens. The event is stamped on the session that
        # printed the new coordinate system, so a window starting there is entirely inside
        # that system and nothing in it spans the change. The stop audit reads the boundary
        # this way, and one frame must not be two different frames to two readers.
        first = max(0, start) + 1
        window = self._splits[first : self._length if end is None else end]
        if not bool(window.any()):
            return None
        return first + int(window.argmax())

    def gap(self, start: int = 0, end: int | None = None, columns: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")) -> dict[str, Any] | None:
        """The unavailable block for a window holding a session this reading cannot use, or None.

        Columns as well as sessions: a broken Volume has nothing to do with an average of
        closes, and voiding one because of the other hides a measurement that is fine.
        """

        first = self.gap_position(start, end, columns)
        if first is None:
            return None
        return {"state": "unavailable", "reason": "invalid_ohlc_history", "date": self._bars.index[first].date().isoformat()}

    def gap_position(self, start: int = 0, end: int | None = None, columns: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")) -> int | None:
        """Where in the frame the window's first unusable session sits, or None.

        A reading that must refuse a window still read the sessions before the hole, and a
        finding among them already happened. The position is what lets an audit stop there
        instead of throwing away what it had.
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
        return first

    def missing_at(self, positions: list[int], columns: tuple[str, ...]) -> dict[str, Any] | None:
        """The unavailable block for a reading that opens named cells rather than a span.

        Some readings are not a window at all: a return over twenty sessions opens two
        closes, and a volume ratio opens the sessions that fell. Guarding the span between
        them would refuse the reading over a bar it never touched.
        """

        found = [
            position
            for position in sorted(set(positions))
            if 0 <= position < self._length
            and any(self._bad.get(column) is not None and bool(self._bad[column][position]) for column in columns)
        ]
        if not found:
            return None
        return {"state": "unavailable", "reason": "invalid_ohlc_history", "date": self._bars.index[found[0]].date().isoformat()}

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


def _stage3_transition(bars: pd.DataFrame, *, readable: _Readable) -> dict[str, Any]:
    """Rising volatility and a flattening long average, measured; the reading stays the analyst's."""

    length = int(doctrine.parameter(_ATR, "atr_length_sessions"))
    sma_length = int(doctrine.parameter(_SLOPE, "long_average_sessions"))
    lookback = int(doctrine.parameter(_SLOPE, "slope_lookback_sessions"))
    # The slope reads closes back to the average's own length; the two true ranges read High
    # and Low over their own windows, which end well inside it.
    gap = (
        readable.gap(len(bars) - (sma_length + lookback), columns=("Close",))
        or readable.gap(len(bars) - 2 * length, columns=("High", "Low"))
        or readable.split(len(bars) - (sma_length + lookback))
    )
    if gap is not None:
        return {**gap, "doctrine_id": _STAGE3}
    recent, recent_value = _average_true_range(bars)
    # The earlier average reads its own length of ranges plus the session the first range is
    # measured from, and it starts where the recent one leaves off: two lengths and one bar.
    earlier, earlier_value = _average_true_range(bars.iloc[: len(bars) - length]) if len(bars) >= 2 * length + 1 else ({"state": "unavailable", "reason": "insufficient_history_for_comparison"}, None)
    ratio = recent_value / earlier_value if recent_value and earlier_value else None
    closes = bars["Close"].astype(float)
    slope: float | None = None
    state = "unavailable"
    if len(bars) >= sma_length + lookback:
        average = closes.rolling(sma_length).mean()
        now, before = float(average.iloc[-1]), float(average.iloc[-1 - lookback])
        if math.isfinite(now) and math.isfinite(before) and before > 0:
            slope = (now / before - 1) * 100
            state = "reported"
    if recent.get("value") is None and earlier.get("value") is None and state == "unavailable":
        # Neither true range and no slope: there is no Stage 3 vector here, and publishing
        # one as reported beside three unavailable constituents says a reading was made.
        return {
            "doctrine_id": _STAGE3,
            "state": "unavailable",
            "reason": "insufficient_history_for_stage3_vector",
            "average_true_range": recent,
            "earlier_average_true_range": earlier,
            "sma200_state": state,
        }
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
        # The claim this block cites describes a price break on heavy volume, and volume is
        # among its required inputs. Neither measurement here reads it, in any history, so it
        # is named as evidence this reading does not consume rather than evidence it wanted:
        # the same numbers came back from a frame that had volume and one that did not.
        "claim_inputs_not_read": _unread_claim_inputs((_STAGE3, _ATR, _SLOPE), ("price_history", "sma_200")),
        "needs_chart": True,
    }


def _base_extension(bars: pd.DataFrame, *, entry_date: date, base_top: float | None, readable: _Readable) -> dict[str, Any]:
    if base_top is None:
        return {"state": "unavailable", "reason": "base_top_not_declared"}
    # From the session after entry, which is the window the excursion beside this block
    # reads. A daily bar cannot say whether its High printed before or after the fill, so
    # crediting the entry session's own High here would report the position further along
    # than the peak the stop rules measure from -- one question with two answers, and the
    # more flattering one on the page a reader takes the extension from.
    held = [position for position, timestamp in enumerate(bars.index) if timestamp.date() > entry_date]
    # Two readings, two windows: the extension is the latest close against the base top, and
    # the furthest the position got is the highest High since entry. No close between them
    # is opened, so a hole in one is not this block's business.
    # Three windows, not one. The extension opens the latest close; the peak opens the Highs
    # after entry; and the coordinate system is the one the base top was declared in, which
    # is the entry session's -- so the split question is asked from there. An event on the
    # entry session is the system the position was opened in and crosses nothing, while one
    # the session after it sits between the declared base top and every close since.
    declared = _positions_since(bars, entry_date)
    gap = (
        readable.gap(len(bars) - 1, columns=("Close",))
        or readable.gap(held[0] if held else 0, columns=("High",))
        or readable.split(declared[0] if declared else 0)
    )
    if gap is not None:
        return {**gap, "doctrine_id": _PAUSE_ZONE}
    closes = bars["Close"].astype(float)
    highs = bars["High"].astype(float)
    last_close = _finite(closes.iloc[-1])
    # With no session after entry there is no High to read, and the last completed close is
    # the floor of what the position reached -- which is the rule the stop side already
    # applies. Falling silent here would publish a null beside an excursion measured from
    # that same close, and the reader would have two answers to how far the position got.
    max_high = _finite(highs.iloc[held].max()) if held else last_close
    if last_close is None or base_top <= 0:
        return {"state": "unavailable", "reason": "invalid_close_or_base_top"}
    extension_pct = (last_close / base_top - 1) * 100
    return {
        "doctrine_id": _PAUSE_ZONE,
        "binds": doctrine.binds(_PAUSE_ZONE),
        "state": "reported",
        "base_top": base_top,
        "extension_pct": _reported(extension_pct),
        "claim_inputs_not_read": _unread_claim_inputs((_PAUSE_ZONE,), ("base_top", "current_price", "max_high_since_entry")),
        "max_extension_pct": _reported((max_high / base_top - 1) * 100 if max_high is not None else None),
        "band": doctrine.evaluate_band(_PAUSE_ZONE, "pause_zone_pct", extension_pct),
    }


def _average_true_range(bars: pd.DataFrame) -> tuple[dict[str, Any], float | None]:
    """The record to publish, and the measurement to keep computing with.

    They are not the same number. The record is rounded so a reader is not handed the last
    bits of a binary float; feeding that rounded figure back in as a divisor makes the next
    measurement wrong in its tenth decimal place, which is a number nobody can reproduce
    from the definition.
    """

    length = int(doctrine.parameter(_ATR, "atr_length_sessions"))
    highs = bars["High"].astype(float)
    lows = bars["Low"].astype(float)
    closes = bars["Close"].astype(float)
    if len(bars) < length + 1:
        return {"doctrine_id": _ATR, "state": "unavailable", "reason": "insufficient_history_for_average_true_range", "length_sessions": length}, None
    previous_close = closes.shift(1)
    true_range = pd.concat([highs - lows, (highs - previous_close).abs(), (previous_close - lows).abs()], axis=1).max(axis=1)
    value = float(true_range.iloc[-length:].mean())
    if not math.isfinite(value) or value <= 0:
        return {"doctrine_id": _ATR, "state": "unavailable", "reason": "invalid_true_range", "length_sessions": length}, None
    return {"doctrine_id": _ATR, "length_sessions": length, "value": _reported(value)}, value


def _moving_average_extension(bars: pd.DataFrame, *, readable: _Readable) -> dict[str, Any]:
    ema_length = int(doctrine.threshold(_ROLES, "ema_length_sessions"))
    sma_length = int(doctrine.threshold(_ROLES, "sma_length_sessions"))
    atr_length = int(doctrine.parameter(_ATR, "atr_length_sessions"))
    # Two windows, because two different readings: the percentile ranks every prior session's
    # closes, and the true range reads High and Low over its own length and no further back.
    gap = readable.gap(0, columns=("Close",)) or readable.gap(len(bars) - atr_length, columns=("High", "Low")) or readable.split(0)
    if gap is not None:
        return {**gap, "doctrine_id": _OWN_CHARACTER}
    closes = bars["Close"].astype(float)
    atr, atr_value = _average_true_range(bars)
    # No warm-up mask here: the length guard below already refuses a history shorter than
    # the average, and every position this block reads starts at the average's own warm-up.
    # A mutation probe proved a mask changes nothing, which makes it a line that looks like
    # a rule and is not one.
    ema = closes.ewm(span=ema_length, adjust=False).mean()
    sma = closes.rolling(sma_length).mean()
    block: dict[str, Any] = {
        "doctrine_id": _OWN_CHARACTER,
        "doctrine_ids": [_OWN_CHARACTER, _ATR],
        "binds": doctrine.binds(_OWN_CHARACTER),
        "state": "reported",
        "atr": atr,
        "claim_inputs_not_read": _unread_claim_inputs((_OWN_CHARACTER, _ATR), ("price_history", "ema_21", "sma_50", "average_true_range")),
        "needs_chart": True,
    }
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
    # The prior session is part of the reading: the gap and the prior low come from it. But
    # only the latest session's Open and Close are opened -- every other session in the
    # window contributes a range and a volume, and nothing else.
    gap = (
        readable.gap(max(0, window[0] - 1), columns=("High", "Low"))
        or readable.gap(window[0], columns=("Volume",))
        or readable.gap(len(bars) - 1, columns=("Open", "Close"))
        or readable.split(max(0, window[0] - 1))
    )
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
        **_closing_range(bars.iloc[last]),
        "visually_extended": None,
        "trend_line_of_highs_breached": None,
    }
    computable = sum(1 for name in ("gap_up_filled_and_reversed", "highest_volume_since", "widest_range_since") if features[name] is True)
    missing_inputs = [name for name, present in (("open_history", opens is not None), ("volume_history", volumes is not None)) if not present]
    return {
        "doctrine_id": _KEY_REVERSAL,
        "doctrine_ids": [_KEY_REVERSAL, _CLOSING_RANGE],
        "binds": doctrine.binds(_KEY_REVERSAL),
        "state": "reported",
        "claim_inputs_not_read": _unread_claim_inputs((_KEY_REVERSAL, _CLOSING_RANGE), ("price_history", "volume_history", "breakout_date", "daily_bar")),
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


def _climax(bars: pd.DataFrame, *, readable: _Readable) -> dict[str, Any]:
    closes = bars["Close"].astype(float)
    lengths = [int(doctrine.parameter(_WINDOWS, name)) for name in ("short_window_sessions", "medium_window_sessions", "long_window_sessions")]
    gap_window = int(doctrine.parameter(_WINDOWS, "medium_window_sessions"))
    # A return over twenty sessions opens two closes, not twenty-one. The gap count reads
    # Opens and Highs over its own window, and the latest session's range is read by the
    # closing-range formula, which names its own missing inputs rather than voiding this.
    gap = (
        readable.missing_at([len(bars) - 1 - back for back in (0, *lengths)], ("Close",))
        or readable.gap(max(0, len(bars) - (gap_window + 1)), columns=("Open", "High"))
        or readable.split(len(bars) - (max(lengths) + 1))
    )
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
    volume_population_complete = True
    if "Volume" in bars.columns:
        volumes = bars["Volume"].astype(float)
        prior = [_finite(volumes.iloc[position]) for position in range(len(bars) - 1)]
        last_volume = _finite(volumes.iloc[-1])
        # The readability guard covers the return windows, and this ranking reads every prior
        # session. A NaN inside that population counts as a session the latest volume beat --
        # a rank against bars that were never there -- so an incomplete population produces
        # no percentile rather than a number nobody can reproduce.
        # A split inside the population is the same hole reached from the other side: the
        # volumes before it count a different share, so ranking today against them is a rank
        # over two populations. The event does not void the block -- the return windows are
        # this side of it -- but it does void the ranking.
        volume_population_complete = last_volume is not None and all(value is not None for value in prior) and readable.split_position(0) is None
        if volume_population_complete and prior:
            percentile = sum(1 for value in prior if value <= last_volume) / len(prior) * 100
    # Its own reading of the latest session, so the range and the marker beside it come from
    # one computation, and the values it could not use are named rather than left as a null
    # with nothing to explain it. The other climax measurements are unaffected: this session
    # opens the range only.
    last_range = _closing_range(bars.iloc[-1])
    return {
        "doctrine_id": _CLIMAX,
        "doctrine_ids": [_CLIMAX, _WINDOWS, _CLOSING_RANGE],
        "binds": doctrine.binds(_CLIMAX),
        "state": "reported",
        "windows": {**{f"return_{window}_pct": window for window in lengths}, "gap_ups_last_10_sessions": gap_window},
        "missing_inputs": [name for name, present in (("open_history", opens is not None), ("volume_history", "Volume" in bars.columns and volume_population_complete)) if not present]
        + [f"last_{name}" for name in last_range["closing_range_missing_inputs"]],
        # The claim asks for the base count as well -- a climax run is read against how far
        # into the advance the stock is -- and nothing in this block reads it. That is not
        # the same as an input that was wanted and absent, so it is named separately: a
        # reader must be able to see which half of the claim these numbers actually cover.
        "claim_inputs_not_read": _unread_claim_inputs((_CLIMAX, _WINDOWS, _CLOSING_RANGE), ("price_history", "volume_history", "daily_bar")),
        **returns,
        "gap_ups_last_10_sessions": gap_ups,
        "last_volume_percentile": _reported(percentile),
        "last_closing_range_pct": last_range["closing_range_pct"],
        "last_closing_range_marker": last_range["closing_range_marker"],
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
        # Every block this capability promises, named. A key that simply vanishes reads as a
        # measurement with nothing to report, and the caller cannot tell it from one that was
        # never attempted -- which is the whole distinction this evidence pack exists to keep.
        unavailable = {"state": "unavailable", "reason": "completed_ohlc_history_unavailable"}
        return {name: ({**unavailable, "selected": management_average} if name == "moving_average_trail" else dict(unavailable)) for name in _BLOCKS}
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
