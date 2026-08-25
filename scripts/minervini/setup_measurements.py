"""Measure a declared base from completed bars, with no doctrine in the room.

Phase 1 made the registry the single owner of every limit. A measurement function that
also read limits would put the same number in two places, and two copies of one judgment
drift -- which is the defect Phase 0 spent three commits removing elsewhere. So the window
lengths this needs arrive as an argument and nothing here decides anything: it returns
numbers, and the reducer compares them with what the registry says.

Every number is ``None`` rather than a substitute when the history cannot support it. A
short average that looks like a 50-day average is worse than an admitted gap.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


_SESSIONS_PER_WEEK = 5


def _window(bars: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return bars.loc[pd.Timestamp(start) : pd.Timestamp(end)]


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _baseline(volume: pd.Series, sessions: int, end: str) -> float | None:
    history = volume.loc[: pd.Timestamp(end)]
    if sessions <= 0 or len(history) < sessions:
        return None
    return float(history.iloc[-sessions:].mean())


def _up_down_volume(bars: pd.DataFrame) -> dict[str, float | None]:
    """Both halves of the source's sentence: the totals, and whether any up day spiked.

    "The volume must be much bigger on up days than on down days, and a few of the price
    spikes to the upside should be large, dwarfing the contractions that have occurred on
    relatively lower volume." A base whose up-day total edges ahead while no up day ever
    prints a large bar satisfies the first clause and not the second.
    """
    change = bars["Close"].diff()
    up_days = bars.loc[change > 0, "Volume"]
    down_days = bars.loc[change < 0, "Volume"]
    return {
        "up_day_volume": float(up_days.sum()),
        "down_day_volume": float(down_days.sum()),
        "largest_up_day_volume": float(up_days.max()) if len(up_days) else None,
        "largest_down_day_volume": float(down_days.max()) if len(down_days) else None,
    }


def measure(bars: pd.DataFrame, structure: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a resolved structure and its bars to the numbers the setup reducer reads."""

    contractions = list(structure.get("contractions") or [])
    base = structure.get("base")
    if not contractions or not isinstance(base, Mapping):
        return {
            "contraction_depths_pct": [],
            "successive_depth_ratios": [],
            "contraction_count": 0,
            "contractions_contract": None,
            "base_depth_pct": None,
            "base_duration_weeks": None,
            "final_contraction_volume_ratio": None,
            "up_day_volume": None,
            "down_day_volume": None,
            "largest_up_day_volume": None,
            "largest_down_day_volume": None,
            "up_down_volume_ratio": None,
            "largest_up_to_down_volume_ratio": None,
            "pivot_area_volume_ratio_to_base": None,
            "breakout_date": None,
            "sessions_since_breakout": None,
            "sessions_after_pivot": None,
            "pause_held_to_breakout": None,
            "breakout_held": None,
            "pivot_extension_at_breakout_pct": None,
            "daily_range_median_pct": None,
            "close_change_median_pct": None,
            "left_side_sessions": None,
            "right_side_sessions": None,
            "right_to_left_session_ratio": None,
            "right_side_contraction_count": None,
            "pivot": None,
            "pivot_cleared": None,
            "pivot_extension_pct": None,
            "breakout_volume_ratios": {},
            "closing_range_pct": None,
            "overhead_supply_high": None,
            "overhead_supply_above_pivot_pct": None,
            "last_close": None,
        }

    depths = [float(item["depth_pct"]) for item in contractions]
    ratios = [
        later / earlier
        for earlier, later in zip(depths, depths[1:])
        if earlier > 0
    ]

    base_window = _window(bars, base["start"], base["end"])
    final = contractions[-1]
    final_window = _window(bars, final["high_date"], final["recovery_end"])
    earlier_base = base_window.loc[base_window.index < pd.Timestamp(final["high_date"])]
    baseline_sessions = int(spec.get("volume_baseline_sessions") or 0)
    baseline = _baseline(bars["Volume"], baseline_sessions, base["end"])

    volume_sides = _up_down_volume(base_window)
    # Tightness is read where the source reads it -- the final contraction on the right
    # side, just before the purchase -- so no session count has to be invented for it.
    tightness_window = final_window

    # The source's hazard is a right side that develops too fast for supply to be worked
    # through -- "V-shaped price action or the absence of proper right-side development".
    # It names no ratio, so both halves and their ratio are reported and nothing is decided.
    low_date = min(contractions, key=lambda item: item["low"])["low_date"]
    left_sessions = len(_window(bars, base["start"], low_date))
    right_sessions = len(_window(bars, low_date, base["end"]))
    right_side = [item for item in contractions if item["high_date"] >= low_date]

    pivot = float(base["pivot"])
    # The breakout is the session the stock left the base, not whatever bar the history
    # happens to end on. Reading the last bar meant a pivot from two months ago could be
    # paired with today's volume and called a current breakout.
    after_pivot = bars.loc[bars.index > pd.Timestamp(base["pivot_date"])]
    cleared = after_pivot.loc[after_pivot["Close"] > pivot]
    breakout_label = cleared.index[0] if len(cleared) else None
    breakout = bars.loc[breakout_label] if breakout_label is not None else None
    since_breakout = bars.loc[bars.index > breakout_label] if breakout_label is not None else bars.iloc[0:0]
    before_breakout = after_pivot.loc[after_pivot.index < breakout_label] if breakout_label is not None else after_pivot
    last = bars.iloc[-1]
    # A chain declared from a late high leaves whatever traded higher before it above the
    # entry, and the source is explicit about what that is: buyers waiting to get out at
    # breakeven. Every anchor is checked against its own span, so this is the one thing the
    # structure check cannot see, and it is reported rather than decided.
    prior = bars.loc[: pd.Timestamp(base["start"])].iloc[:-1]
    prior_high = float(prior["High"].max()) if len(prior) else None
    breakout_baselines = tuple(spec["breakout_volume_baseline_sessions"])
    span = (float(breakout["High"]) - float(breakout["Low"])) if breakout is not None else None

    return {
        "contraction_depths_pct": depths,
        "successive_depth_ratios": ratios,
        "contraction_count": len(depths),
        # Reported as its own fact because a "VCP" whose contractions widen is not a
        # narrower VCP; it is a different pattern wearing the name. One contraction has no
        # successive pair in it, so the rule is unobserved rather than vacuously satisfied --
        # otherwise the shortest possible declaration clears what a longer one has to earn.
        "contractions_contract": None if len(depths) < 2 else all(later < earlier for earlier, later in zip(depths, depths[1:])),
        "base_depth_pct": float(base["depth_pct"]),
        "base_duration_weeks": round(int(base["duration_sessions"]) / _SESSIONS_PER_WEEK, 4),
        "final_contraction_volume_baseline_sessions": baseline_sessions,
        "final_contraction_volume_ratio": _ratio(float(final_window["Volume"].mean()) if len(final_window) else None, baseline),
        **volume_sides,
        "up_down_volume_ratio": _ratio(volume_sides["up_day_volume"], volume_sides["down_day_volume"]),
        "largest_up_to_down_volume_ratio": _ratio(volume_sides["largest_up_day_volume"], volume_sides["largest_down_day_volume"]),
        # "Every correct pivot point will develop with a contraction in volume" is a
        # comparison inside the base, which is what makes it evaluable without borrowing the
        # fifty-day marker's number to decide with. The comparison runs against what came
        # before the pivot area rather than against the base as a whole, so a base with one
        # contraction -- where the two windows are the same window -- reports nothing instead
        # of reporting a ratio of one and calling it a failure to contract.
        "pivot_area_volume_ratio_to_base": _ratio(
            float(final_window["Volume"].mean()) if len(final_window) else None,
            float(earlier_base["Volume"].mean()) if len(earlier_base) else None,
        ),
        "daily_range_median_pct": float(((tightness_window["High"] - tightness_window["Low"]) / tightness_window["High"] * 100).median()) if len(tightness_window) else None,
        "close_change_median_pct": float((tightness_window["Close"].pct_change().abs() * 100).median()) if len(tightness_window) > 1 else None,
        "left_side_sessions": left_sessions,
        "right_side_sessions": right_sessions,
        "right_to_left_session_ratio": _ratio(float(right_sessions), float(left_sessions)),
        "right_side_contraction_count": len(right_side),
        "pivot": pivot,
        "pivot_date": base["pivot_date"],
        # An intraday touch and a completed close above the pivot are different facts, and
        # this harness reads completed bars, so the close is what it reports.
        "pivot_cleared": breakout_label is not None,
        "breakout_date": breakout_label.date().isoformat() if breakout_label is not None else None,
        "sessions_since_breakout": int(len(since_breakout)) if breakout_label is not None else None,
        "sessions_after_pivot": int(len(after_pivot)),
        # A pause that broke down before it broke out, and a breakout that gave the pivot
        # back afterwards, are both facts about whether the trigger is still live.
        "pause_held_to_breakout": bool((before_breakout["Close"] > float(base["low"])).all()) if breakout_label is not None else None,
        "breakout_held": bool((since_breakout["Close"] > pivot).all()) if breakout_label is not None else None,
        "pivot_extension_at_breakout_pct": ((float(breakout["Close"]) - pivot) / pivot * 100) if breakout is not None else None,
        "pivot_extension_pct": (float(last["Close"]) - pivot) / pivot * 100,
        "breakout_volume_ratios": {
            sessions: _ratio(
                float(breakout["Volume"]),
                _baseline(bars["Volume"].loc[bars.index < breakout_label], int(sessions), str(bars.index[bars.index < breakout_label][-1].date())),
            )
            for sessions in breakout_baselines
        }
        if breakout_label is not None
        else {sessions: None for sessions in breakout_baselines},
        # "Closing range = (Close - Low / High - Low) * 100" is printed without the
        # parentheses the arithmetic needs; the surrounding worked example (high 100, low
        # 90, close 98 gives 80 percent) settles which grouping the source meant.
        "closing_range_pct": (float(breakout["Close"]) - float(breakout["Low"])) / span * 100 if breakout is not None and span and span > 0 else None,
        "last_close": float(last["Close"]),
        "overhead_supply_high": prior_high,
        "overhead_supply_above_pivot_pct": None if prior_high is None else max(0.0, (prior_high - pivot) / pivot * 100),
    }


__all__ = ["measure"]
