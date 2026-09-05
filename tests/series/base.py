"""Build OHLCV series whose swing extremes are exactly the numbers a test names.

The book's own worked example is a 25 percent contraction, then 10, then 5. A test that
constructs those depths and asks the engine to recover them is comparing the engine with
the source, not with the code that drew the bars.

Every bar opens at its close and carries a wick narrower than the smallest leg step, so a
declared swing bar really is the extreme of its span. An earlier version inflated wicks by
a fixed percentage and quietly put the highest bar one session past every declared high;
the structure resolver rejected the fixture, which is the resolver working.
"""

from __future__ import annotations

from dataclasses import dataclass

from collections.abc import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Anchor:
    """One turning point the builder pinned, so a test can name its date."""

    position: int
    kind: str
    price: float


def _leg(start: float, end: float, sessions: int) -> list[float]:
    step = (end - start) / sessions
    return [start + step * (index + 1) for index in range(sessions)]


def base_series(
    *,
    base_high: float = 100.0,
    depths: tuple[float, ...] = (25.0, 10.0, 5.0),
    run_up: int = 55,
    decline: int = 12,
    rally: int = 10,
    rallies: tuple[int, ...] | None = None,
    declines: tuple[int, ...] | None = None,
    volume_profile: str = "drying",
    pause_dip_pct: float = 1.5,
    breakout: bool = True,
    daily_range_pct: float | None = None,
    hidden_bounce: bool = False,
    start: str = "2026-01-02",
) -> tuple[pd.DataFrame, list[Anchor]]:
    closes = _leg(base_high * 0.55, base_high, run_up)
    anchors = [Anchor(len(closes) - 1, "high", base_high)]
    high = base_high
    down = declines or (decline,) * len(depths)
    up = rallies or (rally,) * len(depths)
    for depth, decline_sessions, rally_sessions in zip(depths, down, up):
        low = high * (1 - depth / 100)
        closes += _leg(high, low, decline_sessions)
        anchors.append(Anchor(len(closes) - 1, "low", low))
        # Each rally stops just under the prior swing high, the way a base tightens toward
        # the right without printing a new high before the pivot.
        high = high * 0.998
        closes += _leg(low, high, rally_sessions)
        anchors.append(Anchor(len(closes) - 1, "high", high))
    # A pivot is a high the stock backed away from before clearing it. Without that pause the
    # last anchor is just a point on a monotonic rise, and no segmentation can find it -- which
    # is what a breakout is measured against. The pause is there whether or not the breakout has
    # happened yet; a base waiting for one is sitting in it.
    if pause_dip_pct:
        closes += _leg(high, high * (1 - pause_dip_pct / 100), 3)
    if breakout:
        closes.append(base_high * 1.03)

    steps = [abs(later - earlier) for earlier, later in zip(closes, closes[1:])]
    wick = 0.15 * min(step for step in steps if step > 0)

    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    if daily_range_pct is None:
        frame["High"] = frame["Close"] + wick
        frame["Low"] = frame["Close"] - wick
    else:
        # Real bars are wide: a session's high and low routinely straddle its close by more than
        # a leg step. Everything built with the default hairline wick hides whatever a rule gets
        # wrong about a bar that both extends a move and retraces it -- which is how a detector
        # that resolved nothing on real data passed six adversarial review rounds.
        #
        # It is opt-in rather than the default because these legs are long: the last contraction
        # of a twenty-five/ten/five base moves less per session than a realistic bar is wide, so
        # its declared anchor stops being the extreme of its own span and the structure resolver
        # rejects the fixture. A realistic fixture needs shorter legs as well as wider bars.
        half = daily_range_pct / 200
        frame["High"] = frame["Close"] * (1 + half)
        frame["Low"] = frame["Close"] * (1 - half)
    if hidden_bounce:
        _insert_bounce_between_neighbours(frame, anchors, daily_range_pct)
    pinned = {anchor.position: anchor.kind for anchor in anchors}
    for position, kind in pinned.items():
        label = index[position]
        # The declared extreme is the close itself, so no neighbour's wick can reach it.
        frame.loc[label, "High" if kind == "high" else "Low"] = frame.loc[label, "Close"]

    span = len(closes)
    if volume_profile == "drying":
        # Volume dries through the base and arrives on up days rather than down days,
        # which is what accumulation looks like on the tape.
        volumes = [
            2_000_000
            * (1 - 0.7 * position / span)
            * (1.8 if position and closes[position] > closes[position - 1] else 0.5)
            for position in range(span)
        ]
    elif volume_profile == "rising":
        volumes = [700_000 * (1 + 1.5 * position / span) for position in range(span)]
    elif volume_profile == "distribution":
        # Heavy on down days and light on up days: contractions can still contract while
        # the stock is being distributed, which is the case the source's up/down volume
        # rule exists to catch.
        volumes = [
            2_000_000.0 if position and closes[position] < closes[position - 1] else 500_000.0
            for position in range(span)
        ]
    else:
        volumes = [1_000_000.0] * span
    frame["Volume"] = volumes
    if breakout:
        # A breakout session opens near the pivot and travels, so its range spans the entry a
        # trader would actually have taken. Giving it the same narrow wick as every other bar
        # made the pivot unreachable inside the bar that cleared it.
        label = index[-1]
        pivot = anchors[-1].price
        frame.loc[label, "Open"] = pivot * 1.001
        frame.loc[label, "Low"] = pivot * 0.999
        frame.loc[label, "High"] = frame.loc[label, "Close"] * 1.004
        frame.loc[label, "Volume"] = float(pd.Series(volumes[-51:-1]).mean()) * 2.0
    return frame[["Open", "High", "Low", "Close", "Volume"]], anchors


def anchor_dates(frame: pd.DataFrame, anchors: list[Anchor]) -> list[str]:
    """The alternating high/low chain a caller would declare for this series."""

    return [frame.index[anchor.position].date().isoformat() for anchor in anchors]


def two_bases_series(
    *,
    first_high: float = 100.0,
    second_high: float = 130.0,
    first_depths: tuple[float, ...] = (25.0, 10.0, 5.0),
    second_depths: tuple[float, ...] = (15.0, 8.0, 4.0),
    advance: int = 25,
    start: str = "2026-01-02",
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """A base the stock already broke out of, and the base it built above it.

    One history holding two completed structures is what tells a proposal apart from a memory:
    a detector that answers with the older base is describing a level the stock is thirty
    percent above. Both chains come back so a test can name which one it expected.
    """

    closes = _leg(first_high * 0.55, first_high, 55)
    first: list[Anchor] = [Anchor(len(closes) - 1, "high", first_high)]
    second: list[Anchor] = []

    def consolidate(rim: float, depths: tuple[float, ...], anchors: list[Anchor]) -> float:
        high = rim
        for depth in depths:
            low = high * (1 - depth / 100)
            closes.extend(_leg(high, low, 12))
            anchors.append(Anchor(len(closes) - 1, "low", low))
            high = high * 0.998
            closes.extend(_leg(low, high, 10))
            anchors.append(Anchor(len(closes) - 1, "high", high))
        # The pause that makes the last high a pivot rather than a point on a rise.
        closes.extend(_leg(high, high * 0.985, 3))
        return high

    first_pivot = consolidate(first_high, first_depths, first)
    closes.extend(_leg(closes[-1], second_high, advance))
    second.append(Anchor(len(closes) - 1, "high", second_high))
    consolidate(second_high, second_depths, second)

    steps = [abs(later - earlier) for earlier, later in zip(closes, closes[1:])]
    wick = 0.15 * min(step for step in steps if step > 0)
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] + wick
    frame["Low"] = frame["Close"] - wick
    for anchor in first + second:
        label = index[anchor.position]
        frame.loc[label, "High" if anchor.kind == "high" else "Low"] = frame.loc[label, "Close"]
    frame["Volume"] = [1_000_000.0] * len(closes)
    assert first_pivot < second_high
    return (
        frame[["Open", "High", "Low", "Close", "Volume"]],
        [index[anchor.position].date().isoformat() for anchor in first],
        [index[anchor.position].date().isoformat() for anchor in second],
    )


def bases_under_an_older_high_series(*, start: str = "2026-01-02") -> tuple[pd.DataFrame, list[str], list[str]]:
    """Two bases where the breakout between them never took out the older high.

    `two_bases_series` puts the second rim above everything before it, which happens to satisfy
    the rim rule by accident. A deep correction, a partial recovery, and a breakout out of that
    recovery's own pivot is the shape that does not: the old peak still towers over the base
    being built, so the chain covers both structures. That is the answer -- the contraction gate
    is what rejects it, and a detector that trimmed to the newer half would be deleting the
    evidence that gate reads.
    """

    closes = _leg(55.0, 100.0, 50)
    first = [Anchor(len(closes) - 1, "high", 100.0)]
    closes.extend(_leg(100.0, 60.0, 25))
    first.append(Anchor(len(closes) - 1, "low", 60.0))
    closes.extend(_leg(60.0, 80.0, 20))
    first.append(Anchor(len(closes) - 1, "high", 80.0))
    closes.extend(_leg(80.0, 78.0, 3))

    second: list[Anchor] = []
    closes.extend(_leg(78.0, 95.0, 18))
    second.append(Anchor(len(closes) - 1, "high", 95.0))
    for low, high in ((84.0, 94.8), (88.0, 94.6)):
        closes.extend(_leg(closes[-1], low, 12))
        second.append(Anchor(len(closes) - 1, "low", low))
        closes.extend(_leg(low, high, 10))
        second.append(Anchor(len(closes) - 1, "high", high))
    closes.extend(_leg(closes[-1], 93.2, 3))

    steps = [abs(later - earlier) for earlier, later in zip(closes, closes[1:])]
    wick = 0.15 * min(step for step in steps if step > 0)
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] + wick
    frame["Low"] = frame["Close"] - wick
    for anchor in first + second:
        label = index[anchor.position]
        frame.loc[label, "High" if anchor.kind == "high" else "Low"] = frame.loc[label, "Close"]
    frame["Volume"] = [1_000_000.0] * len(closes)
    return (
        frame[["Open", "High", "Low", "Close", "Volume"]],
        [index[anchor.position].date().isoformat() for anchor in first],
        [index[anchor.position].date().isoformat() for anchor in second],
    )


def hidden_turn_series(*, turn_pct: float = 0.2) -> tuple[pd.DataFrame, list[str], list[str]]:
    """A base with one turn too small for the detector but big enough to declare.

    This is the shape the equality rule exists for. A caller who keeps every detected date and
    cuts one contraction into two skips nothing and moves no endpoint, so every anchor is still
    the extreme of its own span and the structure resolver has nothing to object to -- and the
    unfavourable contraction is gone from the sequence that gets judged.

    The turn is smaller than the retracement at the lowest neighbouring multiple, so it stays
    invisible at all three and the segmentation is still one the detector will vouch for. Any
    larger and the nearest neighbour sees it, the detector refuses to vouch, and the test would
    be measuring the instability rather than the comparison.
    """

    frame, anchors = base_series()
    chain = anchor_dates(frame, anchors)
    peak, trough = anchors[0].position, anchors[1].position
    at = (peak + trough) // 2
    wick = float(frame["High"].iloc[at] - frame["Close"].iloc[at])
    dip = float(frame["Close"].iloc[at]) * (1 - turn_pct / 200)
    bounce = dip * (1 + turn_pct / 100)
    frame.iloc[at, frame.columns.get_indexer(["Open", "Close", "Low"])] = dip
    frame.iloc[at, frame.columns.get_loc("High")] = dip + wick
    frame.iloc[at + 1, frame.columns.get_indexer(["Open", "Close", "High"])] = bounce
    frame.iloc[at + 1, frame.columns.get_loc("Low")] = bounce - wick
    finer = [chain[0], frame.index[at].date().isoformat(), frame.index[at + 1].date().isoformat(), *chain[1:]]
    return frame, chain, finer


def borrowed_contraction_series(*, breakout_volume: bool = True) -> tuple[pd.DataFrame, list[str], list[str]]:
    """A current structure with one contraction, sitting above a structure price left.

    One contraction is no sequence, so `contractions_contract` comes back unavailable and the
    setup cannot be ready. Reach back past the departure and the older decline supplies the
    missing one: forty, fifteen, seven reads as a textbook progression, and a base that had no
    sequence to judge is promoted on contractions belonging to a structure the stock is already
    out of.
    """

    closes = _leg(55.0, 100.0, 55)
    left = [Anchor(len(closes) - 1, "high", 100.0)]
    for target, kind, sessions in ((60.0, "low", 25), (80.0, "high", 20), (68.0, "low", 12)):
        closes.extend(_leg(closes[-1], target, sessions))
        left.append(Anchor(len(closes) - 1, kind, target))

    current: list[Anchor] = []
    for target, kind, sessions in ((95.0, "high", 18), (88.0, "low", 10), (94.8, "high", 10)):
        closes.extend(_leg(closes[-1], target, sessions))
        current.append(Anchor(len(closes) - 1, kind, target))
    closes.extend(_leg(94.8, 92.8, 3))

    index = pd.bdate_range(start="2026-01-02", periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] + 0.1
    frame["Low"] = frame["Close"] - 0.1
    for anchor in left + current:
        label = index[anchor.position]
        frame.loc[label, "High" if anchor.kind == "high" else "Low"] = frame.loc[label, "Close"]
    span = len(closes)
    frame["Volume"] = [
        2_000_000 * (1 - 0.7 * position / span) * (1.8 if position and closes[position] > closes[position - 1] else 0.5)
        for position in range(span)
    ]
    if not breakout_volume:
        # The same price path with nothing on the tape. Whether the stock left the eighty level
        # is the whole question, and price alone answers it identically either way -- so a
        # fixture that only ever expands proves the boundary fires, never that volume is what
        # fires it.
        level = left[-1].price
        for position, label in enumerate(frame.index):
            if float(frame.at[label, "Close"]) <= level or position < 50:
                continue
            prior = frame["Volume"].iloc[position - 50 : position]
            frame.at[label, "Volume"] = float(prior.mean()) * 0.5
    return (
        frame[["Open", "High", "Low", "Close", "Volume"]],
        [index[anchor.position].date().isoformat() for anchor in left],
        [index[anchor.position].date().isoformat() for anchor in current],
    )


def from_legs(
    legs: tuple[tuple[float, float, int], ...],
    *,
    last: tuple[float, float, float, float] | None = None,
    wick: float = 0.03,
    start: str = "2025-08-01",
) -> pd.DataFrame:
    """A frame from explicit price legs, for shapes no base builder produces.

    Each leg is (from, to, sessions) of evenly spaced closes. `last` replaces the final bar's
    OHLC, which is how a breakout that opens under the level it clears gets built.
    """

    closes: list[float] = []
    for begin, end, sessions in legs:
        step = (end - begin) / sessions
        closes.extend(begin + step * (position + 1) for position in range(sessions))
    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] + wick
    frame["Low"] = frame["Close"] - wick
    span = len(closes)
    frame["Volume"] = [
        2_000_000 * (1 - 0.7 * position / span) * (1.8 if position and closes[position] > closes[position - 1] else 0.5)
        for position in range(span)
    ]
    if last is not None:
        frame.loc[index[-1], ["Open", "High", "Low", "Close"]] = last
        frame.loc[index[-1], "Volume"] = float(frame["Volume"].iloc[-51:-1].mean()) * 2.0
    return frame[["Open", "High", "Low", "Close", "Volume"]]


def turn_between_neighbours_series(*, daily_range_pct: float = 1.0) -> pd.DataFrame:
    """A decline interrupted by one bounce sized to fall between two neighbouring multiples.

    The retracement is derived from the bars, so a fixture with a hand-picked bounce is tuned to
    whatever the multiple happens to be today. This computes the bounce from the registry
    instead: large enough that the lower neighbour calls it a turn, small enough that the primary
    multiple does not. What it demonstrates is a chain that exists only at one end of the
    sensitivity sweep, which is the thing the detector refuses to vouch for.
    """

    from scripts.minervini import doctrine

    convention = "setup.swing_segmentation_convention"
    multiple = float(doctrine.parameter(convention, "retracement_range_multiple"))
    lower = multiple + min(float(value) for value in doctrine.parameter(convention, "sensitivity_offsets"))
    half = daily_range_pct / 200
    # A bounce is measured from the running low, which sits a half-range under its close.
    low = 90.0 * (1 - half)
    fraction = (lower + multiple) / 2 * daily_range_pct / 100
    bounce = low * (1 + fraction) / (1 + half)

    closes = [80.0, 90.0, 100.0, 95.0, 90.0, bounce, 90.0, 80.0, 75.0, 85.0,
              99.0, 95.0, 89.0, 94.0, 98.0, 95.0, 93.0, 96.0, 97.0, 95.0]
    index = pd.bdate_range("2026-01-02", periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes, "Volume": [1e6] * len(closes)}, index=index)
    frame["High"] = frame["Close"] * (1 + half)
    frame["Low"] = frame["Close"] * (1 - half)
    return frame[["Open", "High", "Low", "Close", "Volume"]]


def _insert_bounce_between_neighbours(frame: pd.DataFrame, anchors: list[Anchor], daily_range_pct: float | None) -> None:
    """Put one turn inside the first decline that only the lower neighbouring multiple can see.

    Sized from the registry rather than by hand: the retracement is derived from the bars, so a
    fixture with a chosen bounce is tuned to whatever the multiple happens to be today and goes
    quietly meaningless the next time it moves.
    """

    from scripts.minervini import doctrine

    if not daily_range_pct:
        raise ValueError("hidden_bounce needs an explicit daily_range_pct so the scale is known")
    convention = "setup.swing_segmentation_convention"
    multiple = float(doctrine.parameter(convention, "retracement_range_multiple"))
    lower = multiple + min(float(value) for value in doctrine.parameter(convention, "sensitivity_offsets"))
    half = daily_range_pct / 200
    at = (anchors[0].position + anchors[1].position) // 2
    fraction = (lower + multiple) / 2 * daily_range_pct / 100
    dip = float(frame["Close"].iloc[at])
    bounce = dip * (1 - half) * (1 + fraction) / (1 + half)
    frame.iloc[at + 1, frame.columns.get_indexer(["Open", "Close"])] = bounce
    frame.iloc[at + 1, frame.columns.get_loc("High")] = bounce * (1 + half)
    frame.iloc[at + 1, frame.columns.get_loc("Low")] = bounce * (1 - half)


def unstable_series(**kwargs) -> tuple[pd.DataFrame, list[Anchor]]:
    """A base the detector refuses to vouch for, because neighbouring multiples cut it apart.

    The turn is placed by the registry's own numbers, so the fixture follows the parameter rather
    than being retuned behind it. No session is ambiguous here, which keeps the two reasons a
    segmentation can fail apart.
    """

    # Wide enough that the bounce has room to sit between two multiples, narrow enough that the
    # declared anchors are still the extremes of their spans: the last contraction of this base
    # moves less per session than a full-width bar, so a realistic width makes the structure
    # resolver reject the fixture before the detector is ever consulted.
    kwargs.setdefault("daily_range_pct", 0.5)
    return base_series(hidden_bounce=True, **kwargs)


def neighbour_only_ambiguity_series() -> tuple[pd.DataFrame, str]:
    """One session a neighbouring multiple cannot order, where every chain still matches.

    The sensitivity sweep used to compare anchor dates and nothing else, so a neighbour run that
    had itself reported "this bar could have turned either way" was read as agreement. Both runs
    had lost the same evidence, which is not the same as both having found the same thing.

    The give-back is sized from the registry to fall between the primary multiple and its lower
    neighbour: below the primary's retracement, so that run sees an ordinary bar, and above the
    neighbour's, so that one sees a bar which both extended the move and reversed it.
    """

    from scripts.minervini import doctrine

    convention = "setup.swing_segmentation_convention"
    multiple = float(doctrine.parameter(convention, "retracement_range_multiple"))
    lower = multiple + min(float(value) for value in doctrine.parameter(convention, "sensitivity_offsets"))
    frame, anchors = base_series(daily_range_pct=0.5)
    typical = float(((frame["High"] - frame["Low"]) / frame["Close"] * 100).median())
    give_back = (multiple + lower) / 2 * typical / 100

    at = anchors[0].position + 1
    for position in range(anchors[0].position + 1, anchors[-1].position):
        label = frame.index[position]
        peak = float(frame["High"].iloc[:position].max())
        high, low = peak * 1.0005, peak * (1 - give_back)
        frame.loc[label, "High"], frame.loc[label, "Low"] = high, low
        frame.loc[label, ["Open", "Close"]] = (high + low) / 2
        at = position
        break
    return frame, frame.index[at].date().isoformat()


def distribution_only_in_the_tail_series() -> tuple[pd.DataFrame, list[str], list[str]]:
    """A base whose volume is healthy, and a suffix of its own chain where it is not.

    Declared as the whole base the up/down ratio passes; declared as the last five anchors it
    fails, because that span is where the down-day volume was piled. The suffix is structurally
    valid -- every anchor is still the extreme of its span -- so nothing but the comparison with
    the detector's own chain separates it from an honest declaration, and the verdict read off it
    is a finding about some other span.
    """

    frame, anchors = base_series()
    whole = [frame.index[anchor.position].date().isoformat() for anchor in anchors]
    suffix = whole[2:]
    heavier = (frame["Close"] < frame["Close"].shift(1)) & (frame.index >= pd.Timestamp(suffix[0]))
    frame.loc[heavier, "Volume"] = frame.loc[heavier, "Volume"] * 3
    return frame, whole, suffix
