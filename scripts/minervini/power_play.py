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
        "peak_is_the_structure_high": None,
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

    # The peak the flag hangs from is the highest bar inside the longest flag the source
    # allows -- and then the FIRST session that printed it, counting from the last time the
    # stock traded above it. Reading it from the last equal high instead re-labels the flag
    # that came before as part of the advance: a session that merely matched a high already
    # made is not the explosive move the first criterion is about, and a forty-session flag
    # read from it becomes a twelve-session one that clears the six-week limit.
    #
    # It is also what stops the six-week limit from being a tautology. Bounded by the search
    # window on both sides, every flag would measure at six weeks or less by construction;
    # anchored at the first occurrence, a flag that really did run longer measures longer and
    # fails on its own length.
    window = bars.iloc[-(flag_window + 1):]
    peak_high = float(window["High"].max())
    exceeded = bars.index[bars["High"] > peak_high]
    since = bars.loc[exceeded[-1]:].iloc[1:] if len(exceeded) else bars
    peak_label = since.index[since["High"] == peak_high][0]
    peak = int(bars.index.get_loc(peak_label))

    before = bars.iloc[max(0, peak - advance_window):peak]
    flag = bars.iloc[peak + 1:]

    if not len(before):
        return _empty("history_has_no_sessions_before_the_peak")

    # Both windows are anchored at the last bar, so the flag alone cannot say whether the peak
    # it hangs from is the top of anything: a search that starts six weeks back finds a six-week
    # flag whether or not the bar before it traded higher. Two of eighteen real tickers reported
    # exactly that. The structure's own span is what settles it -- the advance's window through
    # the last bar -- and a peak that is not its highest point is not the peak the criteria are
    # about, however tidy the flag under it looks.
    structure_high = float(bars.iloc[max(0, peak - advance_window):]["High"].max())

    low_label = before["Low"].idxmin()
    advance_low = float(before.loc[low_label, "Low"])
    launch = int(bars.index.get_loc(low_label))
    # The volume the advance "commences on", against what the same stock traded before it. The
    # source gives the clause no magnitude, so this is the ratio and nothing decides on it.
    baseline = bars.iloc[max(0, launch - advance_window):launch]

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
        "peak_is_the_structure_high": peak_high >= structure_high,
        "flag_sessions": int(len(flag)),
        "flag_weeks": len(flag) / _SESSIONS_PER_WEEK,
        "flag_depth_pct": (peak_high - float(flag["Low"].min())) / peak_high * 100 if len(flag) else None,
        "flag_low": float(flag["Low"].min()) if len(flag) else None,
        "flag_low_date": flag["Low"].idxmin().date().isoformat() if len(flag) else None,
        "rejection": None,
    }


__all__ = ["measure_power_play"]
