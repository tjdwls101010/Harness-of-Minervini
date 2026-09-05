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

# Keep orchestration lookups here so existing module-level overrides still apply.

import math
from datetime import date, timedelta
from typing import Any
import numpy as np
import pandas as pd
from ..numbers import REPORTED_PRECISION as _REPORTED_PRECISION
from ..numbers import finite_or_none as _finite
from ..setup_structure import session_index
from .. import doctrine


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


from .readings import AVERAGES, BLOCKS, SMALLEST_RECOGNIZED_SPLIT_RATIO, SPLIT_COLUMN, _CLOSING_RANGE, _DISCONTINUITY, _ROLES, _Readable, _SPLIT_COLUMN, _TWENTY_DAY, _VOLUME_CONVENTION, _VOLUME_STATE, _closing_range, _closing_range_pct, _completed, _first_trouble, _latest_tie, _positions_since, _reported, _twenty_day_average, _unread_claim_inputs, impossible_bar_relations, split_sized_discontinuities
from .stops import _moving_average_trail, _trail
from .structure import _ATR, _CLIMAX, _KEY_REVERSAL, _LARGEST_DECLINE, _OWN_CHARACTER, _PAUSE_ZONE, _SLOPE, _STAGE3, _WINDOWS, _average_true_range, _base_extension, _climax, _daily, _key_reversal, _largest_decline, _moving_average_extension, _stage3_transition, _weekly
from .time import _ACTS_AS_EXPECTED, _FAILED_VOLUME, _FIRST_SESSIONS, _LATE_GAPS, _TENNIS_BALL, _failed_volume_confirmation, _first_sessions, _gaps_since_breakout, _natural_reactions, _post_breakout_behavior


__all__ = ["AVERAGES", "build_management_evidence"]
