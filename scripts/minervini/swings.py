"""Segment completed bars into alternating turning points, deterministically.

This exists because the engine cannot tell an honest swing chain from a flattering one by
measuring it: a chain that skipped an unfavourable contraction still has every anchor
sitting at its own span's extreme. What it can do is produce an independent segmentation
and compare, which is what makes the caller's chart reading checkable at all.

The retracement that decides when a move has turned is the harness's own convention. The
source calls swing reading chart work and never names a percentage, so this is not doctrine
and does not pretend to be: the value travels in the envelope, and the instability of a
segmentation across neighbouring values is reported rather than hidden behind one of them.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .setup_structure import completed_bars


def segment(history: Any, *, retracement_pct: float) -> dict[str, Any]:
    """A base's confirmed turning points, and the leg price is in now, kept apart.

    Confirming an extreme means watching price fall away from it by the retracement, so the
    move currently underway is never confirmed. That matters at exactly the point the setup is
    about: a breakout in progress is an unconfirmed advance, and folding it into the base's
    chain would move the pivot onto the breakout bar. The base is the confirmed chain, trimmed
    to end on a high because that high is the pivot; the live leg travels separately.

    Raises:
        ValueError: If ``retracement_pct`` is not a percentage strictly between zero and 100.
    """
    if not isinstance(retracement_pct, (int, float)) or not 0 < float(retracement_pct) < 100:
        raise ValueError("retracement_pct must be a percentage greater than zero and less than 100")

    empty: dict[str, Any] = {"anchors": [], "provisional": None, "retracement_pct": float(retracement_pct)}
    bars = completed_bars(history)
    if bars is None or bars.empty:
        return empty

    fraction = float(retracement_pct) / 100
    highs, lows = bars["High"], bars["Low"]
    swings: list[dict[str, Any]] = []
    # Start looking for a high: a base begins at the left rim of its own decline, and a run-up
    # into that rim produces no turn until price falls away from it.
    rising = True
    extreme_label = bars.index[0]
    extreme = float(highs.iloc[0])

    for label in bars.index[1:]:
        high, low = float(highs.at[label]), float(lows.at[label])
        if rising:
            if high >= extreme:
                extreme_label, extreme = label, high
            elif low <= extreme * (1 - fraction):
                swings.append({"date": _iso(extreme_label), "kind": "high", "price": extreme})
                rising, extreme_label, extreme = False, label, low
        else:
            if low <= extreme:
                extreme_label, extreme = label, low
            elif high >= extreme * (1 + fraction):
                swings.append({"date": _iso(extreme_label), "kind": "low", "price": extreme})
                rising, extreme_label, extreme = True, label, high

    provisional = {"date": _iso(extreme_label), "kind": "high" if rising else "low", "price": extreme}
    # A base runs high to high, and the last high is its pivot. A confirmed chain ending on a
    # low describes a decline still under way, which names no pivot.
    while swings and swings[-1]["kind"] != "high":
        swings.pop()
    anchors = swings if len(swings) >= 3 else []
    return {"anchors": anchors, "provisional": provisional, "retracement_pct": float(retracement_pct)}


def _iso(label: Any) -> str:
    return pd.Timestamp(label).date().isoformat()


__all__ = ["segment"]
