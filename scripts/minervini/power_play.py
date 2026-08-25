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

from .setup_structure import _CORPORATE_ACTION_COLUMN, read_bars


_SESSIONS_PER_WEEK = 5


def _change(bars: pd.DataFrame, column: str, start: int, end: int) -> float | None:
    """One column's percentage move between two positions, or nothing if it is not carried.

    ``start`` is the session before the move, not its first session. "An explosive price move
    commences on huge volume" makes the launch bar part of the advance, so reading from its own
    close throws away whatever it did: a stock that ran from ninety to two hundred in two weeks
    reported thirty-three percent, because the session that travelled from eighty to one hundred
    and sixty was where the reading began. With nothing in front of it there is no price before
    the move, which is a gap rather than a zero.
    """
    if column not in bars or start < 0:
        return None
    first = float(bars.iloc[start][column])
    return (float(bars.iloc[end][column]) - first) / first * 100 if first > 0 else None


def _empty(reason: str | None) -> dict[str, Any]:
    return {
        "peak_date": None,
        "peak_high": None,
        "advance_low": None,
        "advance_low_date": None,
        "advance_pct": None,
        "advance_pct_closes": None,
        "advance_pct_adjusted": None,
        "advance_sessions": None,
        "advance_weeks": None,
        "launch_volume_ratio": None,
        "advance_peak_volume_ratio": None,
        "advance_peak_volume_date": None,
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
    # Inside the search span and nowhere else. Taking the first equal high anywhere in the loaded
    # history is the mirror of taking the last: one glues the flag to a session months earlier
    # that merely printed the same price, the other re-labels the flag as advance. A tie says
    # nothing about whether two sessions belong to one structure, so the span decides which ties
    # are even candidates and the first of those starts the flag.
    #
    # A version of this also looked for the last session that traded *above* the peak and started
    # from there. Nothing can trade above the maximum of the window it is the maximum of, so that
    # search never found anything and the clause described a rule the code did not run.
    peak_label = window.index[window["High"] == peak_high][0]
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

    baseline_volume = float(baseline["Volume"].mean()) if len(baseline) else None
    measurable = baseline_volume is not None and baseline_volume > 0

    return {
        "peak_date": peak_label.date().isoformat(),
        "peak_high": peak_high,
        "advance_low": advance_low,
        "advance_low_date": low_label.date().isoformat(),
        # Three readings of one move, because the raw tape cannot tell a move from a corporate
        # action or from a single wick. Extremes take the session's own low against the peak's
        # own high and are the widest; the closes reading is the same move between two prices the
        # tape settled at; the adjusted reading is that one corrected for splits and dividends.
        #
        # Reported apart rather than reduced to one number here. Which reading a criterion is
        # read against is doctrine, and taking the smallest -- the first thing tried -- turns the
        # source's single hundred percent condition into a new three-way AND: on real bars the
        # extremes reading runs a median of 5.4 points above the closes one, and on the one
        # ticker whose advance actually reached a hundred percent it was 101.8 against 96.4.
        "advance_pct": (peak_high - advance_low) / advance_low * 100 if advance_low > 0 else None,
        "advance_pct_closes": _change(bars, "Close", launch - 1, peak),
        "advance_pct_adjusted": _change(bars, _CORPORATE_ACTION_COLUMN, launch - 1, peak),
        "advance_sessions": peak - launch,
        "advance_weeks": (peak - launch) / _SESSIONS_PER_WEEK,
        # Three readings of the volume clause, because "commences on huge volume" asks about a
        # session and the search cannot say for certain which session that was.
        #
        # The average across the advance answers a different question and answers it wrongly: one
        # bar at ten times its baseline followed by nineteen quiet ones averages below the
        # baseline and reads as no expansion at all. The lowest bar is not reliably the one the
        # move began on either -- a quiet undercut five weeks before the peak wins the lowest-low
        # search, and reading the clause there reported no expansion on a stock that went from
        # ninety to two hundred in nine sessions at ten times its usual volume.
        #
        # So the heaviest session of the advance is reported with its date, and it is the reading
        # a numberless observation can be taken on: an advance with no expanded session anywhere
        # in it did not commence on huge volume under any identification of its first bar. Whether
        # the expansion was *huge*, and whether it came at the commencement rather than in the
        # middle, is what the chart is asked -- and the date beside the ratio is what that
        # question is asked about.
        "launch_volume_ratio": float(bars.iloc[launch]["Volume"]) / baseline_volume if measurable else None,
        "advance_peak_volume_ratio": float(bars.iloc[launch:peak + 1]["Volume"].max()) / baseline_volume if measurable else None,
        "advance_peak_volume_date": bars.index[launch + int(bars.iloc[launch:peak + 1]["Volume"].to_numpy().argmax())].date().isoformat() if measurable else None,
        "advance_volume_ratio": float(bars.iloc[launch:peak + 1]["Volume"].mean()) / baseline_volume if measurable else None,
        "flag_sessions": int(len(flag)),
        "flag_weeks": len(flag) / _SESSIONS_PER_WEEK,
        "flag_depth_pct": (peak_high - float(flag["Low"].min())) / peak_high * 100 if len(flag) else None,
        "flag_low": float(flag["Low"].min()) if len(flag) else None,
        "flag_low_date": flag["Low"].idxmin().date().isoformat() if len(flag) else None,
        "rejection": None,
    }


__all__ = ["measure_power_play"]
