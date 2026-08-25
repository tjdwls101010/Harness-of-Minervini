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
    if breakout:
        # A pivot is a high the stock backed away from before clearing it. Without that pause
        # the last anchor is just a point on a monotonic rise, and no segmentation can find
        # it -- which is what a breakout is measured against.
        if pause_dip_pct:
            closes += _leg(high, high * (1 - pause_dip_pct / 100), 3)
        closes.append(base_high * 1.03)

    steps = [abs(later - earlier) for earlier, later in zip(closes, closes[1:])]
    wick = 0.15 * min(step for step in steps if step > 0)

    index = pd.bdate_range(start=start, periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = frame["Close"] + wick
    frame["Low"] = frame["Close"] - wick
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
