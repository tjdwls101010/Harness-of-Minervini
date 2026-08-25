"""Segment completed bars into alternating turning points, deterministically.

This exists because the engine cannot tell an honest swing chain from a flattering one by
measuring it: a chain that skipped an unfavourable contraction still has every anchor sitting
at its own span's extreme. What it can do is produce its own segmentation and compare, which
is what makes a caller's chart reading checkable at all.

Everything here is the harness's own convention. The source calls swing reading chart work and
never names a retracement, so the rules are written down rather than left to whatever the loop
happened to do: an extreme is never confirmed by its own bar, because a daily bar does not say
whether its high came before its low; the first of two equal extremes is the one named; and the
chain a base is described by is chosen by this module, never by the caller, because letting a
caller pick the parameter or the starting anchor puts the segmentation gaming back in through
the choice.

The parameters live in the registry as parameters rather than thresholds. They are not limits a
measurement is compared with -- they select what gets computed -- but they are not inert either:
the chain they produce decides a required condition, so they are recorded as affecting the
verdict and travel in every answer.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from . import doctrine
from .setup_structure import completed_bars


_CONVENTION = "setup.swing_segmentation_convention"


def segment(history: Any, *, retracement_pct: float) -> dict[str, Any]:
    """A base's confirmed turning points, the leg price is in now, and what was ambiguous.

    Confirming an extreme means watching price fall away from it by the retracement, so the
    move currently underway is never confirmed. That matters at exactly the point a setup is
    about: a breakout in progress is an unconfirmed advance, and folding it into the base's
    chain would move the pivot onto the breakout bar.

    Raises:
        ValueError: If ``retracement_pct`` is not a percentage strictly between zero and 100.
    """
    if isinstance(retracement_pct, bool) or not isinstance(retracement_pct, (int, float)):
        raise ValueError("retracement_pct must be a percentage greater than zero and less than 100")
    if not 0 < float(retracement_pct) < 100:
        raise ValueError("retracement_pct must be a percentage greater than zero and less than 100")

    empty: dict[str, Any] = {
        "anchors": [],
        "live_leg": None,
        "ambiguous_sessions": [],
        "retracement_pct": float(retracement_pct),
    }
    bars = completed_bars(history)
    if bars is None or bars.empty:
        return empty

    fraction = float(retracement_pct) / 100
    highs, lows = bars["High"], bars["Low"]
    swings: list[dict[str, Any]] = []
    ambiguous: list[str] = []
    # Looking for a high first: a base begins at the left rim of its own decline, and the run-up
    # into that rim produces no turn until price falls away from it.
    rising = True
    extreme_label = bars.index[0]
    extreme = float(highs.iloc[0])

    for label in bars.index[1:]:
        high, low = float(highs.at[label]), float(lows.at[label])
        if rising:
            extends, reverses = high > extreme, low <= extreme * (1 - fraction)
            if extends and reverses:
                # The bar did both and a daily bar cannot say in which order. Extending is the
                # reading that changes nothing about what has been confirmed so far.
                ambiguous.append(_iso(label))
                extreme_label, extreme = label, high
            elif extends:
                extreme_label, extreme = label, high
            elif reverses and label > extreme_label:
                swings.append({"date": _iso(extreme_label), "kind": "high", "price": extreme})
                rising, extreme_label, extreme = False, label, low
        else:
            extends, reverses = low < extreme, high >= extreme * (1 + fraction)
            if extends and reverses:
                ambiguous.append(_iso(label))
                extreme_label, extreme = label, low
            elif extends:
                extreme_label, extreme = label, low
            elif reverses and label > extreme_label:
                swings.append({"date": _iso(extreme_label), "kind": "low", "price": extreme})
                rising, extreme_label, extreme = True, label, high

    return {
        "anchors": swings,
        "live_leg": {"date": _iso(extreme_label), "kind": "high" if rising else "low", "price": extreme},
        "ambiguous_sessions": ambiguous,
        "retracement_pct": float(retracement_pct),
    }


def base_chain(confirmed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The one base among the confirmed turning points, chosen without asking the caller.

    The pivot is the last confirmed high, because that is the level a breakout would clear. The
    left rim is the highest confirmed high at or before it, because that is the peak the
    correction ran from -- the same peak the depth limit measures against. Taking the whole
    confirmed history instead would splice several bases into one; letting the caller name the
    start would hand back the choice this module exists to remove.
    """
    highs = [index for index, anchor in enumerate(confirmed) if anchor["kind"] == "high"]
    if not highs:
        return []
    pivot = highs[-1]
    rim = max((index for index in highs if index <= pivot), key=lambda index: (confirmed[index]["price"], -index))
    chain = confirmed[rim : pivot + 1]
    return chain if len(chain) >= 3 and len(chain) % 2 == 1 else []


def canonical_chain(history: Any) -> dict[str, Any]:
    """The segmentation `ticker.setup` corroborates a declared chain against.

    It refuses to vouch for anything when a neighbouring parameter value would have produced a
    different chain. Reporting the instability and passing one of the readings anyway is the
    same failure as issuing a verdict over a gap the engine already knows about: what changes
    is only whether the gap is visible.
    """
    retracement = float(doctrine.parameter(_CONVENTION, "retracement_pct"))
    offsets = [float(value) for value in doctrine.parameter(_CONVENTION, "sensitivity_offsets_pct")]
    parameters = {"retracement_pct": retracement, "sensitivity_offsets_pct": offsets}

    bars = completed_bars(history)
    sessions = 0 if bars is None else int(len(bars))
    primary = segment(bars if bars is not None else history, retracement_pct=retracement)
    anchors = base_chain(primary["anchors"])

    sensitivity: list[dict[str, Any]] = []
    for offset in offsets:
        neighbour = retracement + offset
        if neighbour <= 0:
            continue
        found = base_chain(segment(bars if bars is not None else history, retracement_pct=neighbour)["anchors"])
        if [item["date"] for item in found] != [item["date"] for item in anchors]:
            sensitivity.append({"retracement_pct": neighbour, "anchors": [item["date"] for item in found]})

    state = "resolved" if anchors and not sensitivity else "unstable" if anchors else "unavailable"
    return {
        "state": state,
        "anchors": anchors if state == "resolved" else [],
        "live_leg": primary["live_leg"],
        "ambiguous_sessions": primary["ambiguous_sessions"],
        "sensitivity": sensitivity,
        "parameters": parameters,
        "sessions": sessions,
    }


def _iso(label: Any) -> str:
    return pd.Timestamp(label).date().isoformat()


__all__ = ["base_chain", "canonical_chain", "segment"]
