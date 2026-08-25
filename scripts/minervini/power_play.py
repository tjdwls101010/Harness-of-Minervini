"""Measure a Power Play from completed bars, with no doctrine in the room.

The same contract the base measurements keep: the registry owns every limit, the windows
arrive as an argument, and this returns numbers or ``None`` and decides nothing.

The structure is read backward from the session being traded, because that is the only form
the question is asked in. "The stock price *then* moves sideways" -- the flag runs from the
peak to the last completed bar, so the peak is looked for inside the longest flag the source
allows, and the advance inside the longest advance it allows before that peak. Both windows
are anchored at the last bar, which is what keeps the answer from moving when a caller loads
a different amount of history: measured against the whole history's maximum instead, fourteen
of eighteen real tickers reported a different peak, a different advance, or both, at two
lookbacks that differed only in how much dormancy they included.

That anchoring is also where the eight-week and six-week limits are enforced. They are not
emitted as gates that could reject, because nothing outside them is ever measured: an advance
that took nine weeks cannot be found by a search that only looks back eight, and its ninth
week is not silently forgiven -- it is the reason the eight-week window reports a smaller
advance than the criterion needs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from .setup_structure import read_bars


_SESSIONS_PER_WEEK = 5


def _empty(reason: str | None) -> dict[str, Any]:
    return {
        "peak_date": None,
        "peak_high": None,
        "advance_low": None,
        "advance_low_date": None,
        "advance_pct": None,
        "advance_sessions": None,
        "advance_weeks": None,
        "advance_volume_ratio": None,
        "flag_sessions": None,
        "flag_weeks": None,
        "flag_depth_pct": None,
        "flag_low": None,
        "flag_low_date": None,
        "rejection": reason,
    }


def measure_power_play(history: Any, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a history to the numbers the Power Play criteria are read against."""

    bars, rejection = read_bars(history)
    if bars is None:
        return _empty(rejection)

    flag_window = int(spec["flag_window_sessions"])
    advance_window = int(spec["advance_window_sessions"])

    # The peak the flag hangs from is the highest bar of the longest structure the criteria
    # describe -- an advance of up to eight weeks and a flag of up to six -- and then the FIRST
    # session that printed it, counting from the last time the stock traded above it.
    #
    # Both halves of that are load-bearing, and each was wrong on its own once. Looking only
    # inside the flag's own limit makes the limit satisfied by the search: every flag measures
    # six weeks or less because nothing longer can be found, and a stock ten weeks past its
    # high reports a fictional flag off some lower high inside the decline. Reading the peak
    # from the LAST equal high instead re-labels the flag before it as advance, so a forty
    # session flag becomes twelve and clears the limit that way. Together the limit rejects
    # what it is supposed to reject: a flag that really ran ten weeks measures ten.
    window = bars.iloc[-(advance_window + flag_window + 1):]
    peak_high = float(window["High"].max())
    exceeded = bars.index[bars["High"] > peak_high]
    since = bars.loc[exceeded[-1]:].iloc[1:] if len(exceeded) else bars
    peak_label = since.index[since["High"] == peak_high][0]
    peak = int(bars.index.get_loc(peak_label))

    before = bars.iloc[max(0, peak - advance_window):peak]
    flag = bars.iloc[peak + 1:]

    if not len(before):
        return _empty("history_has_no_sessions_before_the_peak")

    low_label = before["Low"].idxmin()
    advance_low = float(before.loc[low_label, "Low"])
    launch = int(bars.index.get_loc(low_label))
    # The volume the advance "commences on", against what the same stock traded before it. The
    # source gives the clause no magnitude, so this is the ratio and nothing decides on it.
    #
    # The window is required in full rather than taken as far as it reaches. Sliced to a shorter
    # lookback, five real tickers reported the same peak, advance and flag while this ratio
    # moved, because the only thing that had changed was how many sessions were left in front of
    # the launch to average -- a short average wearing a full one's name.
    baseline = bars.iloc[launch - advance_window:launch] if launch >= advance_window else bars.iloc[0:0]

    return {
        "peak_date": peak_label.date().isoformat(),
        "peak_high": peak_high,
        "advance_low": advance_low,
        "advance_low_date": low_label.date().isoformat(),
        "advance_pct": (peak_high - advance_low) / advance_low * 100 if advance_low > 0 else None,
        "advance_sessions": peak - launch,
        "advance_weeks": (peak - launch) / _SESSIONS_PER_WEEK,
        "advance_volume_ratio": (
            float(bars.iloc[launch:peak + 1]["Volume"].mean()) / float(baseline["Volume"].mean())
            if len(baseline) and float(baseline["Volume"].mean()) > 0
            else None
        ),
        "flag_sessions": int(len(flag)),
        "flag_weeks": len(flag) / _SESSIONS_PER_WEEK,
        "flag_depth_pct": (peak_high - float(flag["Low"].min())) / peak_high * 100 if len(flag) else None,
        "flag_low": float(flag["Low"].min()) if len(flag) else None,
        "flag_low_date": flag["Low"].idxmin().date().isoformat() if len(flag) else None,
        "rejection": None,
    }


__all__ = ["measure_power_play"]
