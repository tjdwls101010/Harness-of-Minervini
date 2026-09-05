"""Moving-average trails and their completed breaches."""

from __future__ import annotations

import math
from datetime import date
from typing import Any
import pandas as pd
from ..numbers import finite_or_none as _finite
from .. import doctrine

from .readings import _ROLES, _Readable, _closing_range, _first_trouble, _reported, _unread_claim_inputs


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
