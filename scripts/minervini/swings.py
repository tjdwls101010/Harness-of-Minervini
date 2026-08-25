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


def base_chain(confirmed: list[dict[str, Any]], closes: pd.Series | None = None) -> list[dict[str, Any]]:
    """The one base among the confirmed turning points, chosen without asking the caller.

    The left rim is the highest confirmed high, because that is the peak the correction ran
    from -- the same peak the depth limit measures against. The base runs forward from there
    and stops at the first high above the rim, because a high above the rim is not part of the
    consolidation: it is the stock leaving it.

    That last clause is what keeps a base's identity from moving. Taking the last confirmed
    high instead made the breakout's own high become the pivot as soon as price gave a little
    back, which erased the base the breakout was measured against.

    When closes are supplied, a consolidation that price closed above inside the window ended
    there, and the base starts after it. Without that, one window spanning a breakout and the
    base above it would be spliced into a single structure.
    """
    highs = [index for index, anchor in enumerate(confirmed) if anchor["kind"] == "high"]
    if not highs:
        return []
    pivot = _pivot_index(confirmed, highs, closes)
    if pivot is None:
        return []
    rim = max((index for index in highs if index <= pivot), key=lambda index: (confirmed[index]["price"], -index))
    window = confirmed[rim : pivot + 1]
    if closes is not None and len(window) >= 3:
        window = _after_the_last_breakout(window, closes)
    return window if len(window) >= 3 and len(window) % 2 == 1 else []


def _pivot_index(confirmed: list[dict[str, Any]], highs: list[int], closes: pd.Series | None) -> int | None:
    """The high the current advance came out of, which does not move when new highs form.

    Taking the last confirmed high made the breakout's own high become the pivot as soon as
    price gave a little back, and with it the rim, which erased the base the breakout was
    measured against. The pivot is instead the latest high price has closed above and stayed
    above: that is the level the stock left the base through. With no such high, price is still
    inside the base and its last confirmed high is the pivot.
    """
    # A high standing above everything before it is the stock leaving a structure rather than
    # the top of one, so it is never the pivot while an earlier high is available.
    tops = [index for index in highs if not _is_new_high(confirmed, highs, index)] or highs
    if closes is not None:
        cleared = [
            index
            for index in tops
            if _cleared_and_held(closes, pd.Timestamp(confirmed[index]["date"]), float(confirmed[index]["price"]))
        ]
        if cleared:
            return cleared[-1]
    return tops[-1]


def _is_new_high(confirmed: list[dict[str, Any]], highs: list[int], index: int) -> bool:
    """Whether this high stands above everything the stock had made before it.

    Such a high is the stock leaving a structure, not the top of one. Without this the breakout
    high qualified as a pivot the moment price cleared and held above it, and the base it broke
    out of vanished.
    """
    earlier = [confirmed[other]["price"] for other in highs if other < index]
    return bool(earlier) and float(confirmed[index]["price"]) > max(earlier)


def _cleared_and_held(closes: pd.Series, after: pd.Timestamp, level: float) -> bool:
    later = closes.loc[after:].iloc[1:]
    above = later.loc[later > level]
    if above.empty:
        return False
    return bool((closes.loc[above.index[0] :] > level).all())


def _after_the_last_breakout(window: list[dict[str, Any]], closes: pd.Series) -> list[dict[str, Any]]:
    """Trim a window that spans a consolidation price already left.

    A close above one of the window's own highs is that consolidation ending. Keeping the bars
    before it inside the same base would splice a completed structure onto the one being judged.
    """
    pivot_date = pd.Timestamp(window[-1]["date"])
    start = 0
    for position, anchor in enumerate(window[:-1]):
        if anchor["kind"] != "high":
            continue
        after = closes.loc[pd.Timestamp(anchor["date"]) : pivot_date].iloc[1:-1]
        if len(after) and float(after.max()) > float(anchor["price"]):
            start = position + 1
    trimmed = window[start:]
    while trimmed and trimmed[0]["kind"] != "high":
        trimmed.pop(0)
    return trimmed


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
    source = bars if bars is not None else history
    closes = bars["Close"] if bars is not None else None
    primary = segment(source, retracement_pct=retracement)
    anchors = base_chain(primary["anchors"], closes)

    sensitivity: list[dict[str, Any]] = []
    for offset in offsets:
        neighbour = retracement + offset
        if neighbour <= 0:
            continue
        found = base_chain(segment(source, retracement_pct=neighbour)["anchors"], closes)
        # A finer scale finding an extra wobble is not disagreement about this base. What
        # matters is whether every turning point this chain rests on is still there, and whether
        # the pivot is the same level. Requiring identical chains made a three-quarter-percent
        # bounce inside a twenty-five percent decline veto the whole segmentation.
        dates = {item["date"] for item in found}
        persists = all(anchor["date"] in dates for anchor in anchors)
        same_pivot = bool(found) and bool(anchors) and found[-1]["date"] == anchors[-1]["date"]
        if not (persists and same_pivot):
            sensitivity.append({"retracement_pct": neighbour, "anchors": [item["date"] for item in found]})

    # A session that both extended a move and reversed it could have done either first, and a
    # daily bar does not say which. One inside the base means a turning point may be missing
    # from the chain, so the chain is not something to check a declaration against.
    span = (
        [date for date in primary["ambiguous_sessions"] if anchors and anchors[0]["date"] <= date <= anchors[-1]["date"]]
        if anchors
        else []
    )
    state = "resolved" if anchors and not sensitivity and not span else "unstable" if anchors else "unavailable"
    return {
        "state": state,
        "anchors": anchors if state == "resolved" else [],
        "live_leg": primary["live_leg"],
        "ambiguous_sessions": primary["ambiguous_sessions"],
        "sensitivity": sensitivity,
        "ambiguous_sessions_in_base": span,
        "parameters": parameters,
        "sessions": sessions,
    }


def _iso(label: Any) -> str:
    return pd.Timestamp(label).date().isoformat()


__all__ = ["base_chain", "canonical_chain", "segment"]
