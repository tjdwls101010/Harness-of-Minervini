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
from .setup_structure import bars_fingerprint, completed_bars


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

    The pivot is picked first, then the rim: the highest high at or before it, because that is
    the peak the correction ran from and the same peak the depth limit measures against. There
    is no second rule, and arriving at that took three attempts worth writing down.

    Twice a trim was added to stop the rim reaching back across "a structure price already
    left", on the reading that a base under an older peak is really two. Each version broke
    something the plain rule does not. Cutting at a high price cleared and held deletes the
    anchors carrying the contraction that widened, so twenty-five then thirty comes back as four
    and a half then two and a half and the detector vouches for its own edit. Measuring that
    departure only up to the pivot misses one completed on the pivot bar and counts one price
    came back under afterwards. Measuring it to the last bar instead makes every interior high
    of a base "left" the moment the stock breaks out, and the base vanishes entirely.

    They failed because the distinction is not observable. Inside a correction, price rallying
    above an earlier rally top is a contraction, not a departure, and there is nothing in the
    bars that separates that from a fresh consolidation under an old peak -- only a magnitude
    the source never supplies. What the source does supply is `contractions_must_contract`, a
    gate in the required evidence: a history that really is two structures spliced together
    shows a contraction that widens at the seam and is rejected there, by name. A history whose
    depths contract the whole way is one deep base, and reading it as one is correct.

    Leaving a base is breaking out of it, and that prints a high above everything before it,
    which the rim rule already lands on without help.
    """
    highs = [index for index, anchor in enumerate(confirmed) if anchor["kind"] == "high"]
    if not highs:
        return []
    pivot = _pivot_index(confirmed, highs)
    if pivot is None:
        return []
    rim = max((index for index in highs if index <= pivot), key=lambda index: (confirmed[index]["price"], -index))
    window = confirmed[rim : pivot + 1]
    return window if len(window) >= 3 and len(window) % 2 == 1 else []


def _pivot_index(confirmed: list[dict[str, Any]], highs: list[int]) -> int | None:
    """The high the current advance came out of, which does not move when new highs form.

    Taking the last confirmed high outright made the breakout's own high become the pivot as
    soon as price gave a little back, and with it the rim, which erased the base the breakout
    was measured against. Excluding highs that stand above everything before them fixes that
    without moving the pivot backwards in time: the breakout's high is the stock leaving a
    structure, while the pause it left through is still the latest ordinary high.

    Preferring a high price had *cleared and held* was the other attempt, and it reached past
    the current base entirely. Every high of a base the stock broke out of months ago passes
    that test, and no high of the base being built now does, because price has not cleared it
    yet -- so the proposal came back describing a level the stock was thirty percent above.
    """
    # A high standing above everything before it is the stock leaving a structure rather than
    # the top of one, so it is never the pivot while an earlier high is available.
    tops = [index for index in highs if not _is_new_high(confirmed, highs, index)] or highs
    return tops[-1]


def _is_new_high(confirmed: list[dict[str, Any]], highs: list[int], index: int) -> bool:
    """Whether this high stands above everything the stock had made before it.

    Such a high is the stock leaving a structure, not the top of one. Without this the breakout
    high qualified as a pivot the moment price cleared and held above it, and the base it broke
    out of vanished.
    """
    earlier = [confirmed[other]["price"] for other in highs if other < index]
    return bool(earlier) and float(confirmed[index]["price"]) > max(earlier)


def canonical_chain(history: Any) -> dict[str, Any]:
    """The segmentation `ticker.setup` corroborates a declared chain against.

    It refuses to vouch for anything when a neighbouring parameter value would have produced a
    different chain. Reporting the instability and passing one of the readings anyway is the
    same failure as issuing a verdict over a gap the engine already knows about: what changes
    is only whether the gap is visible.
    """
    multiple = float(doctrine.parameter(_CONVENTION, "retracement_range_multiple"))
    offsets = [float(value) for value in doctrine.parameter(_CONVENTION, "sensitivity_offsets")]

    bars = completed_bars(history)
    sessions = 0 if bars is None else int(len(bars))
    source = bars if bars is not None else history
    typical = _typical_range_pct(bars)
    parameters = {
        "retracement_range_multiple": multiple,
        "sensitivity_offsets": offsets,
        "typical_daily_range_pct": None if typical is None else round(typical, 4),
        "retracement_pct": None if typical is None else round(multiple * typical, 4),
    }
    if typical is None:
        return {
            "state": "unavailable", "anchors": [], "live_leg": None, "ambiguous_sessions": [],
            "sensitivity": [], "ambiguous_sessions_in_base": [], "parameters": parameters,
            "sessions": sessions, "bars_fingerprint": bars_fingerprint(source),
        }
    retracement = multiple * typical
    primary = segment(source, retracement_pct=retracement)
    anchors = base_chain(primary["anchors"])

    sensitivity: list[dict[str, Any]] = []
    for offset in offsets:
        neighbour = (multiple + offset) * typical
        if neighbour <= 0:
            continue
        found = base_chain(segment(source, retracement_pct=neighbour)["anchors"])
        # The same chain, not a chain the same anchors survive into. Accepting a neighbour that
        # cut an extra contraction between the same endpoints would wave through exactly what a
        # declared chain is refused for downstream: an unfavourable contraction re-cut into
        # smaller ones vanishes from the sequence without an endpoint moving.
        if [item["date"] for item in found] != [anchor["date"] for anchor in anchors]:
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
        "bars_fingerprint": bars_fingerprint(source),
    }


def _typical_range_pct(bars: Any) -> float | None:
    """How far this stock travels inside an ordinary session, as a percentage of its close.

    The median rather than the mean, so one gap or one earnings session does not set the scale
    the whole history is read at.
    """
    if bars is None or len(bars) == 0:
        return None
    spread = ((bars["High"] - bars["Low"]) / bars["Close"] * 100).median()
    return float(spread) if spread > 0 else None


def _iso(label: Any) -> str:
    return pd.Timestamp(label).date().isoformat()


__all__ = ["base_chain", "canonical_chain", "segment"]
