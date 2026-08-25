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
from .setup_structure import bars_fingerprint, read_bars


_CONVENTION = "setup.swing_segmentation_convention"
_TRIGGER = "setup.structural_pivot_and_trigger"


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
    bars, _ = read_bars(history)
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


def base_chain(
    confirmed: list[dict[str, Any]],
    closes: pd.Series | None = None,
    lows: pd.Series | None = None,
    volumes: pd.Series | None = None,
    allow_reset: bool = False,
) -> list[dict[str, Any]]:
    """The one base among the confirmed turning points, chosen without asking the caller.

    The pivot is picked first. The rim is then the highest high at or before it -- the peak the
    correction ran from, and the peak the depth limit measures against -- but the search stops
    at any high the stock has already left, because the contractions of a structure price
    departed from are not this base's contractions.

    Getting that boundary wrong reaches `ready` on evidence that is not there, in either
    direction. Reach back too far and an older structure supplies a contraction the current one
    lacks: a base with one contraction has no sequence to judge, until a decline from two
    structures ago is spliced in front of it and the depths read forty, fifteen, seven. Cut too
    eagerly and the contraction that widened is deleted, so twenty-five then thirty comes back
    as four and a half then two and a half. Neither erring direction is safe.

    Three price-only rules were tried for the boundary and all three failed, because on price
    alone a rally above an earlier rally top inside a correction and a fresh consolidation under
    an old peak are the same picture at different magnitudes -- and the source supplies no
    magnitude. What it does supply is the other half of the observation: the buy point is price
    moving above the pivot *on expanding volume*. Leaving is a breakout, a breakout has a volume
    signature, and that signature is what tells the two apart without inventing a number.
    """
    highs = [index for index, anchor in enumerate(confirmed) if anchor["kind"] == "high"]
    if not highs:
        return []
    pivot = _pivot_index(confirmed, highs)
    if pivot is None:
        return []
    floor = _after_the_structure_it_left(confirmed, highs, pivot, closes, lows, volumes, allow_reset)
    if floor is None:
        return []
    candidates = [index for index in highs if floor <= index <= pivot]
    if not candidates:
        return []
    rim = max(candidates, key=lambda index: (confirmed[index]["price"], -index))
    window = confirmed[rim : pivot + 1]
    return window if len(window) >= 3 and len(window) % 2 == 1 else []


def _after_the_structure_it_left(
    confirmed: list[dict[str, Any]],
    highs: list[int],
    pivot: int,
    closes: pd.Series | None,
    lows: pd.Series | None,
    volumes: pd.Series | None,
    allow_reset: bool,
) -> int | None:
    """The earliest anchor the rim search may reach, or nothing when the bars cannot say."""

    if closes is None or lows is None or volumes is None:
        return 0
    until = pd.Timestamp(confirmed[pivot]["date"])
    verdicts = [
        (index, _left_behind(closes, lows, volumes, confirmed[index], until, allow_reset))
        for index in highs
        if index < pivot
    ]
    left = [index for index, verdict in verdicts if verdict]
    floor = left[-1] if left else -1
    # An unjudgeable crossing only matters where judging it could move the floor. The floor is
    # set by the last departure, so one behind that is already inside the discarded span and
    # changes nothing; one ahead of it is a departure that might exist and would cut further.
    # Refusing on any of them at all rejected most real histories on their opening fifty
    # sessions, which have nothing to do with the base being judged.
    if any(verdict is None and index > floor for index, verdict in verdicts):
        return None
    return floor + 1


def _left_behind(
    closes: pd.Series,
    lows: pd.Series,
    volumes: pd.Series,
    anchor: dict[str, Any],
    before: pd.Timestamp,
    allow_reset: bool,
) -> bool | None:
    """Whether the stock broke out above this high and has stayed above it since.

    Three conditions, each from somewhere: a close above the level, on volume expanding against
    what the stock had been trading -- the source's own buy point, stated without a number -- and
    every low since above it, because clearing a level and giving it back is a pivot failure that
    belongs to the base rather than ending it.

    The crossing has to happen before the pivot formed. Without that, the current base's own
    breakout clears every interior high at once on expanding volume, and the base it broke out
    of disappears from under it.

    Holding is read to the last completed bar rather than to the pivot, because whether the stock
    is out of a structure is a fact about now: a high price came back under afterwards was never
    left. Any qualifying crossing counts, not the first -- a level poked through once and
    reclaimed later has been left, and reading only the first attempt kept the older structure
    spliced on forever after one failure.

    `allow_reset` is the second way to read holding, not a looser one. The source says a pivot
    failure can reset and recover, so a breakout, a shallow slip and a quiet recovery is a
    departure it would recognise while the strict reading refuses -- and a recovery has no
    reason to expand again, so no later crossing rescues it there. Each reading is defensible
    and each is wrong somewhere, so both are computed and neither decides alone: the caller of
    this module vouches for a base only where they agree.
    """
    level = float(anchor["price"])
    window = closes.loc[pd.Timestamp(anchor["date"]) : before].iloc[1:-1]
    judged = [(stamp, _volume_expanded(volumes, stamp)) for stamp in window.loc[window > level].index]
    if any(verdict is None for _, verdict in judged):
        # A crossing nobody can judge leaves the question open, and an open question is not a no.
        return None
    crossings = [stamp for stamp, verdict in judged if verdict]
    if not crossings:
        return False
    if not allow_reset:
        return any(
            len(lows.loc[stamp:].iloc[1:]) and bool((lows.loc[stamp:].iloc[1:] > level).all())
            for stamp in crossings
        )
    after = lows.loc[crossings[0] :].iloc[1:]
    touches = after.loc[after <= level]
    if touches.empty:
        return bool(len(after))
    resumed = after.loc[touches.index[-1] :].iloc[1:]
    return bool(len(resumed)) and bool((resumed > level).all())


def _volume_expanded(volumes: pd.Series, stamp: pd.Timestamp) -> bool | None:
    """More than the stock had been trading, over the window the source names for a breakout.

    The comparison is the number-free half of "moves above the pivot point on expanding volume".
    Minervini's own figure -- volume eclipsing its fifty-day average -- is registered as a marker
    rather than a gate, so it supplies the window to look over and never the amount to clear.
    """
    sessions = int(doctrine.parameter(_CONVENTION, "breakout_volume_reference_sessions"))
    prior = volumes.loc[:stamp].iloc[-(sessions + 1) : -1]
    # The whole window, not whatever part of it exists: comparing against two sessions is not the
    # observation the source describes. Absent, the answer is unknown rather than no. Folding it
    # into no made all three readings of the left edge lose the same information and agree, which
    # the agreement rule then read as settled -- so a base borrowed a contraction from a
    # structure nobody could tell whether the stock had left.
    if len(prior) < sessions:
        return None
    return float(volumes.at[stamp]) > float(prior.mean())


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

    bars, rejection = read_bars(history)
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
            "rejection": rejection or "history_has_no_measurable_range",
        }
    retracement = multiple * typical
    closes = None if bars is None else bars["Close"]
    lows = None if bars is None else bars["Low"]
    volumes = None if bars is None else bars["Volume"]
    # Every multiple the sweep will run at, not only the middle one: the upper neighbour reaches
    # past the segmenter's domain first, and it was still being handed to it.
    if not all(0 < (multiple + offset) * typical < 100 for offset in [0.0, *offsets]):
        # A history whose ordinary session spans a large fraction of its own close gives a scale
        # the segmenter has no domain for. That is a fact about the data, so it leaves as typed
        # unavailability rather than as an exception out of a boundary.
        return {
            "state": "unavailable", "anchors": [], "live_leg": None, "ambiguous_sessions": [],
            "sensitivity": [], "ambiguous_sessions_in_base": [], "parameters": parameters,
            "sessions": sessions, "bars_fingerprint": bars_fingerprint(source),
            "rejection": "typical_daily_range_leaves_no_usable_retracement",
        }
    primary = segment(source, retracement_pct=retracement)
    anchors = base_chain(primary["anchors"], closes, lows, volumes)
    # Where the base begins is the one judgment the bars will not settle. Bounding it at a
    # volume-backed breakout is the source's own observation and it is still a reading: it
    # deletes the contraction that widened when the high it fires on is interior to a structure
    # price never left, and it merges two structures when a breakout failed shallowly and
    # recovered quietly. Each of those reached `ready` on a chain the detector had edited.
    #
    # So when the two readings of the left edge disagree, neither is vouched for. That is the
    # rule the parameter sweep already applies, for the same reason: a chain that depends on a
    # call the evidence does not make is not a chain to check a declaration against. It costs
    # almost nothing -- across fifteen real histories the readings agreed on thirteen, and the
    # two they split on were a forty-one and a seventy-nine anchor "base" collapsing to none.
    readings = [
        base_chain(primary["anchors"]),
        anchors,
        base_chain(primary["anchors"], closes, lows, volumes, allow_reset=True),
    ]
    dates = [[item["date"] for item in reading] for reading in readings]
    left_edge_disputed = any(reading != dates[0] for reading in dates[1:])

    sensitivity: list[dict[str, Any]] = []
    for offset in offsets:
        neighbour = (multiple + offset) * typical
        if neighbour <= 0:
            continue
        found = base_chain(segment(source, retracement_pct=neighbour)["anchors"], closes, lows, volumes)
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
    if anchors and not sensitivity and not span and not left_edge_disputed:
        state = "resolved"
    elif anchors or left_edge_disputed:
        state = "unstable"
    else:
        state = "unavailable"
    return {
        "state": state,
        "anchors": anchors if state == "resolved" else [],
        "live_leg": primary["live_leg"],
        "ambiguous_sessions": primary["ambiguous_sessions"],
        "sensitivity": sensitivity,
        "ambiguous_sessions_in_base": span,
        "left_edge_disputed": left_edge_disputed,
        "left_edge_readings": dates if left_edge_disputed else [],
        "parameters": parameters,
        "sessions": sessions,
        "bars_fingerprint": bars_fingerprint(source),
        "rejection": None,
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
