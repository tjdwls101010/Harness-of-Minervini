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


def _up_down_volume(bars: pd.DataFrame) -> tuple[float, float]:
    change = bars["Close"].diff()
    up = float(bars.loc[change > 0, "Volume"].sum())
    down = float(bars.loc[change < 0, "Volume"].sum())
    return up, down


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
            "up_down_volume_ratio": None,
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
    baseline_sessions = int(spec.get("volume_baseline_sessions") or 0)
    baseline = _baseline(bars["Volume"], baseline_sessions, base["end"])

    up_volume, down_volume = _up_down_volume(base_window)
    tightness_window = base_window.iloc[-int(spec.get("tightness_window_sessions") or 0) :]

    # The source's hazard is a right side that develops too fast for supply to be worked
    # through -- "V-shaped price action or the absence of proper right-side development".
    # It names no ratio, so both halves and their ratio are reported and nothing is decided.
    low_date = min(contractions, key=lambda item: item["low"])["low_date"]
    left_sessions = len(_window(bars, base["start"], low_date))
    right_sessions = len(_window(bars, low_date, base["end"]))
    right_side = [item for item in contractions if item["high_date"] >= low_date]

    last = bars.iloc[-1]
    pivot = float(base["pivot"])
    breakout_baselines = tuple(spec.get("breakout_volume_baseline_sessions") or (20, 30, 50))
    span = float(last["High"]) - float(last["Low"])

    return {
        "contraction_depths_pct": depths,
        "successive_depth_ratios": ratios,
        "contraction_count": len(depths),
        # Reported as its own fact because a "VCP" whose contractions widen is not a
        # narrower VCP; it is a different pattern wearing the name.
        "contractions_contract": all(later < earlier for earlier, later in zip(depths, depths[1:])),
        "base_depth_pct": float(base["depth_pct"]),
        "base_duration_weeks": round(int(base["duration_sessions"]) / _SESSIONS_PER_WEEK, 4),
        "final_contraction_volume_baseline_sessions": baseline_sessions,
        "final_contraction_volume_ratio": _ratio(float(final_window["Volume"].mean()) if len(final_window) else None, baseline),
        "up_day_volume": up_volume,
        "down_day_volume": down_volume,
        "up_down_volume_ratio": _ratio(up_volume, down_volume),
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
        "pivot_cleared": float(last["Close"]) > pivot,
        "pivot_extension_pct": round((float(last["Close"]) - pivot) / pivot * 100, 6),
        "breakout_volume_ratios": {
            sessions: _ratio(float(last["Volume"]), _baseline(bars["Volume"].iloc[:-1], int(sessions), str(bars.index[-2].date())))
            for sessions in breakout_baselines
        },
        # "Closing range = (Close - Low / High - Low) * 100" is printed without the
        # parentheses the arithmetic needs; the surrounding worked example (high 100, low
        # 90, close 98 gives 80 percent) settles which grouping the source meant.
        "closing_range_pct": (float(last["Close"]) - float(last["Low"])) / span * 100 if span > 0 else None,
    }


__all__ = ["measure"]
