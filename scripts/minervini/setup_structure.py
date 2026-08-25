"""Turn a caller's swing dates into a base structure completed bars can contradict.

The setup engine used to take `--price-geometry pass`, an assertion with nothing behind
it. This takes coordinates instead. They are still the caller's reading of the chart --
the source says so, calling swing segmentation chart-assisted -- but every claim in a
chain of dates is falsifiable: the session exists, the order holds, and a bar named as a
swing high really is the highest bar in the span its neighbours bound. A misread chart
now comes back as a contradiction naming the date, where a misread flag came back READY.

The chain alternates high, low, high, ... and ends on a high, because that last high is
the structural pivot: the source's entry is price trading "above the high of the pause",
so a chain with no final pause has not described an entry at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
import hashlib
import json
import math
from typing import Any

import pandas as pd


_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
# Two bars can legitimately tie for a span's extreme, and the anchor's own value is the
# one the maximum was taken from, so this only absorbs float representation noise.
_EXTREME_TOLERANCE = 1e-12


def _unresolved(state: str, problems: list[str]) -> dict[str, Any]:
    return {"state": state, "anchors": [], "contractions": [], "base": None, "problems": problems}


def completed_bars(history: Any) -> pd.DataFrame | None:
    """Sort and coerce a price history once, so validation and measurement read one frame.

    Both halves used to normalise separately, which meant a frame given out of order or with
    numeric strings validated against one reading and was measured against another.
    """

    if not isinstance(history, pd.DataFrame) or any(column not in history for column in _REQUIRED_COLUMNS):
        return None
    bars = history.loc[:, _REQUIRED_COLUMNS].copy()
    for column in _REQUIRED_COLUMNS:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    if bars.isna().any().any() or (bars <= 0).any().any():
        return None
    index = pd.DatetimeIndex(bars.index)
    # Two rows under one label make a bar lookup return a Series, and reading a price off it
    # raises inside the detector -- an internal contract failure where the envelope should carry
    # typed unavailability.
    if index.has_duplicates:
        return None
    # The production provider returns the exchange's own tz-aware index while the fixtures
    # are naive, so a swing date parsed from a string matched one and missed the other.
    if index.tz is not None:
        index = index.tz_convert(None) if index.tz is not None else index
    bars.index = index.normalize()
    return bars if bars.index.is_monotonic_increasing else bars.sort_index()


def bars_fingerprint(history: Any) -> str | None:
    """One digest of the completed bars, so three surfaces can name the same input.

    A chain proposed by `ticker.swings`, the chart a person approved it from, and the setup
    that re-cut it all run over bars the provider could have revised in between. Without this
    a declaration that used to match and now does not is indistinguishable from a rule change:
    same fingerprint means the rules moved, a different one means the data did.
    """
    bars = completed_bars(history)
    if bars is None:
        return None
    records = [
        {"date": stamp.date().isoformat(), **{column: float(row[column]) for column in _REQUIRED_COLUMNS}}
        for stamp, row in bars.iterrows()
    ]
    canonical = json.dumps(
        {"columns": _REQUIRED_COLUMNS, "bars": records}, separators=(",", ":"), sort_keys=True, allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _session(bars: pd.DataFrame, value: Any) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(value).normalize()
    except (TypeError, ValueError):
        return None
    return stamp if stamp in bars.index else None


def _iso(stamp: pd.Timestamp) -> str:
    return stamp.date().isoformat() if isinstance(stamp.date(), date) else str(stamp)


def resolve_structure(history: Any, anchors: Sequence[Any]) -> dict[str, Any]:
    """Validate an alternating chain of swing dates against the completed bars.

    Returns ``resolved`` with the contractions and base the chain describes, ``contradicted``
    with the offending dates named, or ``unavailable`` when there is nothing to check.
    """
    declared = [value for value in (anchors or []) if str(value).strip()]
    if not declared:
        return _unresolved("unavailable", ["no swing chain was declared"])

    bars = completed_bars(history)
    if bars is None:
        return _unresolved("unavailable", ["completed daily OHLCV is missing or invalid"])

    problems: list[str] = []
    if len(declared) < 3 or len(declared) % 2 == 0:
        problems.append(
            "the swing chain must alternate high and low and end on a high, so it needs an odd count of at least three dates"
        )

    stamps: list[pd.Timestamp] = []
    for value in declared:
        stamp = _session(bars, value)
        if stamp is None:
            problems.append(f"{value} is not a completed session in the price history")
        else:
            stamps.append(stamp)
    if len(stamps) != len(declared):
        return _unresolved("contradicted", problems)

    for earlier, later in zip(stamps, stamps[1:]):
        if earlier >= later:
            problems.append(f"{_iso(later)} does not come after {_iso(earlier)}")
    if problems:
        return _unresolved("contradicted", problems)

    resolved: list[dict[str, Any]] = []
    for position, stamp in enumerate(stamps):
        kind = "high" if position % 2 == 0 else "low"
        left = stamps[position - 1] if position > 0 else stamp
        right = stamps[position + 1] if position + 1 < len(stamps) else stamp
        span = bars.loc[left:right]
        if kind == "high":
            price = float(bars.at[stamp, "High"])
            extreme = float(span["High"].max())
        else:
            price = float(bars.at[stamp, "Low"])
            extreme = float(span["Low"].min())
        if not math.isclose(price, extreme, rel_tol=_EXTREME_TOLERANCE):
            problems.append(
                f"{_iso(stamp)} is declared a swing {kind} but is not the {kind} of the span its neighbours bound"
            )
        resolved.append({"date": _iso(stamp), "kind": kind, "price": price})

    contractions: list[dict[str, Any]] = []
    for position in range(0, len(resolved) - 1, 2):
        high, low = resolved[position], resolved[position + 1]
        if high["price"] <= low["price"]:
            problems.append(f"the contraction beginning {high['date']} does not decline")
            continue
        contractions.append(
            {
                "high_date": high["date"],
                "high": high["price"],
                "low_date": low["date"],
                "low": low["price"],
                "depth_pct": (high["price"] - low["price"]) / high["price"] * 100,
                # The recovery ends where the next swing high stands, which is what makes
                # "volume on the final contraction" a window rather than a phrase.
                "recovery_end": resolved[position + 2]["date"],
            }
        )

    if problems:
        return _unresolved("contradicted", problems)

    base_high = resolved[0]["price"]
    base_low = min(item["low"] for item in contractions)
    start, end = stamps[0], stamps[-1]
    return {
        "state": "resolved",
        "anchors": resolved,
        "contractions": contractions,
        "base": {
            "start": _iso(start),
            "end": _iso(end),
            "high": base_high,
            "low": base_low,
            "depth_pct": (base_high - base_low) / base_high * 100,
            "duration_sessions": int(len(bars.loc[start:end])),
            # The last declared high is the pivot: the source's trigger is price trading
            # above the high of the final pause, not above a rolling window's maximum.
            "pivot": resolved[-1]["price"],
            "pivot_date": resolved[-1]["date"],
        },
        "problems": [],
    }


__all__ = ["completed_bars", "resolve_structure"]
