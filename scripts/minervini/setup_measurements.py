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


def _longest_spell(flags: pd.Series) -> int:
    """The longest unbroken run of True in a boolean series."""

    longest = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    return longest


def _up_down_volume(bars: pd.DataFrame) -> dict[str, float | None]:
    """Both halves of the source's sentence: the totals, and whether any up day spiked.

    "The volume must be much bigger on up days than on down days, and a few of the price
    spikes to the upside should be large, dwarfing the contractions that have occurred on
    relatively lower volume." A base whose up-day total edges ahead while no up day ever
    prints a large bar satisfies the first clause and not the second.
    """
    change = bars["Close"].diff()
    returns = bars["Close"].pct_change() * 100
    up_days = bars.loc[change > 0, "Volume"]
    down_days = bars.loc[change < 0, "Volume"]
    up_returns = returns.loc[change > 0]
    down_returns = returns.loc[change < 0]
    return {
        "up_day_volume": float(up_days.sum()),
        "down_day_volume": float(down_days.sum()),
        "largest_up_day_volume": float(up_days.max()) if len(up_days) else None,
        "largest_down_day_volume": float(down_days.max()) if len(down_days) else None,
        "largest_up_day_return_pct": float(up_returns.max()) if len(up_returns) else None,
        "largest_down_day_return_pct": float(-down_returns.min()) if len(down_returns) else None,
        # "a few of the price spikes to the upside should be large" is plural, so the count
        # is what gets reported; one maximum beating one maximum answers neither the plural
        # nor the comparison with the contractions.
        "up_days_exceeding_largest_decline": int((up_returns > -down_returns.min()).sum()) if len(down_returns) and len(up_returns) else None,
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
            "peak_to_low_correction_pct": None,
            "peak_to_low_correction_low": None,
            "peak_date": None,
            "peak_to_low_correction_low_date": None,
            "peak_high": None,
            "base_duration_weeks": None,
            "final_contraction_volume_ratio": None,
            "up_day_volume": None,
            "down_day_volume": None,
            "largest_up_day_volume": None,
            "largest_down_day_volume": None,
            "largest_up_day_return_pct": None,
            "largest_down_day_return_pct": None,
            "up_days_exceeding_largest_decline": None,
            "up_down_volume_ratio": None,
            "pivot_area_volume_ratio_to_base": None,
            "breakout_date": None,
            "pivot_is_highest_to_breakout": None,
            "sessions_since_breakout": None,
            "sessions_after_pivot": None,
            "pause_low_held_to_breakout": None,
            "breakout_held": None,
            "currently_above_pivot": None,
            "base_failed_after_pivot": None,
            "sessions_below_pivot_after_breakout": None,
            "longest_spell_below_pivot": None,
            "pivot_extension_cents": None,
            "latest_session_range": None,
            "pivot_extension_at_breakout_pct": None,
            "failed_pivot_attempts": None,
            "daily_range_median_pct": None,
            "base_daily_range_median_pct": None,
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
    above = after_pivot["Close"] > pivot
    # The breakout is the first close above the pivot after it. An earlier version took the
    # start of whatever run price was in at the end, which let a failed pivot be renamed a
    # breakout by any later rally: `setup.failure_reset_types` says a pivot failure can reset
    # and recover, and a reset is a new structure somebody has to declare, not a rename.
    cleared = after_pivot.loc[above]
    breakout_label = cleared.index[0] if len(cleared) else None
    failed_attempts = int(((~above).astype(int).diff() == 1).sum()) if len(after_pivot) else 0
    breakout = bars.loc[breakout_label] if breakout_label is not None else None
    # The last anchor's right neighbour is itself, so the resolver never looked past it. A
    # bar between the pivot and the breakout that traded higher means the resistance the
    # entry is measured against was somewhere else.
    to_breakout = after_pivot.loc[after_pivot.index < breakout_label] if breakout_label is not None else after_pivot
    pivot_is_highest = bool((to_breakout["High"] <= pivot).all()) if len(after_pivot) else None
    # The baseline is the volume the breakout expanded against, so it is taken from the bars
    # before it. A breakout with nothing before it has no baseline rather than a short one.
    before = bars.loc[bars.index < breakout_label] if breakout_label is not None else bars.iloc[0:0]
    since_breakout = bars.loc[bars.index > breakout_label] if breakout_label is not None else bars.iloc[0:0]
    before_breakout = after_pivot.loc[after_pivot.index < breakout_label] if breakout_label is not None else after_pivot
    last = bars.iloc[-1]
    # A chain declared from a late high leaves whatever traded higher before it above the
    # entry, and the source is explicit about what that is: buyers waiting to get out at
    # breakeven. Every anchor is checked against its own span, so this is the one thing the
    # structure check cannot see, and it is reported rather than decided.
    prior = bars.loc[: pd.Timestamp(base["start"])].iloc[:-1]
    prior_high = float(prior["High"].max()) if len(prior) else None
    # "The correction for a healthy stock from peak to low": the peak is the stock's, not the
    # caller's. Handing the gate the declared base's depth let a chain declared after a sixty
    # percent collapse read as a ten percent base.
    # ...and the low is the low of that correction: the lowest the stock went after the peak,
    # not the lowest of the contractions the caller chose to declare.
    #
    # A version of this bounded the peak to the leg the base sits in, on the reasoning that a
    # decline the stock had fully recovered from belonged to the previous base. The passage
    # says the opposite in its own next clause: a stock that fell more than half "could fail
    # as it reaches or slightly surpasses a new high. This is due to excessive overhead supply
    # created by the steep price decline." The recovery is when the danger arrives.
    through_base = bars.loc[: pd.Timestamp(base["end"])]
    peak = float(through_base["High"].max())
    peak_label = through_base["High"].idxmax()
    correction_low = float(through_base.loc[peak_label:, "Low"].min())
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
        "peak_to_low_correction_pct": (peak - correction_low) / peak * 100 if peak > 0 else None,
        "peak_to_low_correction_low": correction_low,
        # Dated because the window is the provider's, not the source's: how long ago the peak
        # was is what tells a reader whether this correction is the base's or an older one's.
        "peak_date": peak_label.date().isoformat(),
        "peak_to_low_correction_low_date": through_base.loc[peak_label:, "Low"].idxmin().date().isoformat(),
        "peak_high": peak,
        "base_duration_weeks": round(int(base["duration_sessions"]) / int(spec["sessions_per_trading_week"]), 4),
        "final_contraction_volume_baseline_sessions": baseline_sessions,
        "final_contraction_volume_ratio": _ratio(float(final_window["Volume"].mean()) if len(final_window) else None, baseline),
        **volume_sides,
        "up_down_volume_ratio": _ratio(volume_sides["up_day_volume"], volume_sides["down_day_volume"]),
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
        "base_daily_range_median_pct": float(((base_window["High"] - base_window["Low"]) / base_window["High"] * 100).median()) if len(base_window) else None,
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
        "pivot_is_highest_to_breakout": pivot_is_highest,
        "breakout_date": breakout_label.date().isoformat() if breakout_label is not None else None,
        "sessions_since_breakout": int(len(since_breakout)) if breakout_label is not None else None,
        "sessions_after_pivot": int(len(after_pivot)),
        # Between the pivot and the breakout price is still in the pause the pivot topped. A
        # close under that pause's low means the low the caller declared was not the last one,
        # so the declaration is stale rather than the shakeout the source wants to see -- a
        # shakeout undercuts a prior low inside the base, before the pause completed.
        "pause_low_held_to_breakout": bool((before_breakout["Close"] >= float(final["low"])).all()) if breakout_label is not None else None,
        "breakout_held": bool((since_breakout["Close"] >= pivot).all()) if breakout_label is not None else None,
        # `setup.failure_reset_types` says a pivot failure can reset and recover, so where
        # price stands now is a different fact from whether it ever slipped, and the trigger
        # reads this one while the attempts are counted beside it.
        "currently_above_pivot": bool(float(last["Close"]) > pivot),
        # Two failure kinds, counted apart: a close under the base's own low is the one the
        # source says needs a whole new base, and no later rally makes the declared structure
        # the one being bought.
        "base_failed_after_pivot": bool((since_breakout["Close"] < float(base["low"])).any()) if breakout_label is not None else None,
        "sessions_below_pivot_after_breakout": int((since_breakout["Close"] <= pivot).sum()) if breakout_label is not None else None,
        # A total cannot tell one long spell under water from several brief ones, and "within
        # a small number of days" is about a spell.
        "longest_spell_below_pivot": _longest_spell(since_breakout["Close"] <= pivot) if breakout_label is not None else None,
        "pivot_extension_cents": (float(last["Close"]) - pivot) * 100,
        # Where a declared entry price sits against the session. Reported, never decisive: a
        # daily bar does not prove every price between its extremes traded.
        "latest_session_range": [float(last["Low"]), float(last["High"])],
        "failed_pivot_attempts": failed_attempts,
        "pivot_extension_at_breakout_pct": ((float(breakout["Close"]) - pivot) / pivot * 100) if breakout is not None else None,
        "pivot_extension_pct": (float(last["Close"]) - pivot) / pivot * 100,
        "breakout_volume_ratios": {
            sessions: _ratio(float(breakout["Volume"]), _baseline(before["Volume"], int(sessions), str(before.index[-1].date())))
            for sessions in breakout_baselines
        }
        if breakout is not None and len(before)
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
