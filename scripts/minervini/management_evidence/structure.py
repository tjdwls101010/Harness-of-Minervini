"""Price, volume and late-stage structure measurements."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any
import pandas as pd
from ..numbers import finite_or_none as _finite
from .. import doctrine

from .readings import _CLOSING_RANGE, _ROLES, _Readable, _VOLUME_CONVENTION, _VOLUME_STATE, _closing_range, _latest_tie, _positions_since, _reported, _unread_claim_inputs


_LARGEST_DECLINE = "management.largest_decline_since_stage2_start"
_PAUSE_ZONE = "management.tl_base_extension_pause_zone"
_OWN_CHARACTER = "management.tl_extension_measured_against_own_character"
_KEY_REVERSAL = "management.tl_key_reversal_criteria"
_CLIMAX = "management.climax_run_ends_the_advance"
_ATR = "convention.average_true_range"
_WINDOWS = "convention.momentum_review_windows"
_STAGE3 = "stage.stage3_characteristics"
_SLOPE = "convention.long_average_slope_window"


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
