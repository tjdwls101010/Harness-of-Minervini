"""Assemble setup evidence: compile the spec, resolve the structure, measure, evaluate.

Four steps with four owners. The registry owns every limit and every window; the structure
resolver owns whether the caller's chart reading survives contact with the bars; the
measurement module owns arithmetic and knows no doctrine; and this module is the only place
they meet. Nothing here decides a setup state -- that is the reducer's job, and it reads
what this returns.

Binding and contrast evidence are separated before either reaches the reducer. A gate
belonging to a practitioner this harness reads for comparison reports `contrast_pass` or
`contrast_fail`, words no reducer's state vocabulary contains; handing one to a reducer
anyway would not make it ignored, it would make it read as missing evidence and turn
somebody else's disagreement into this harness's incompleteness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from . import doctrine
from .setup_measurements import measure
from .setup_structure import completed_bars, resolve_structure


# Each numberless observation names the claim whose sentence states it. The source supplies
# the requirement and no magnitude, so the predicate reads a direction and the required
# text comes from the claim rather than from a string written here.
_VOLUME_ASYMMETRY = "setup.demand_supply_volume_asymmetry"
_UPSIDE_SPIKES = "setup.upside_spikes_dwarf_contractions"
_PIVOT_VOLUME = "setup.pivot_volume_contraction"
_CONTRACTIONS_CONTRACT = "setup.contractions_must_contract"
_PIVOT_TRIGGER = "setup.structural_pivot_and_trigger"
_TIME_COMPRESSION = "setup.time_compression_hazard"
_OVERHEAD_SUPPLY = "setup.overhead_supply_mechanism"
_CHASE_LIMIT = "setup.chase_limit_above_pivot"

_CONTRACTION_COUNT = "setup.vcp_contraction_count"
_HALVING = "setup.successive_contraction_halving"
_DRYUP = "setup.final_contraction_volume_dryup"
_VOLUME_STATE = "setup.volume_state_convention"
_CLOSING_RANGE = "setup.closing_range_formula"
_CORRECTION_DEPTH = "market.correction_depth_healthy_leader"
_FOOTPRINT = "setup.consolidation_footprint_3_to_60_weeks"
_FAILURE_RESET = "setup.failure_reset_types"
_CHAIN_COMPLETENESS = "setup.declared_chain_completeness"

_RYAN_BREAKOUT = ("practitioners.breakout_volume.ryan_25pct_min_100_200pct_ideal", "breakout_volume_increase_min")
_ZANGER_BREAKOUT = ("practitioners.breakout_volume.zanger_50pct_over_20day_avg", "breakout_volume_increase_over_20d_avg_min")
_MINERVINI_BREAKOUT = ("practitioners.breakout_volume.minervini_eclipse_50d_avg_or_50pct", "breakout_volume_increase_over_50d_avg_min")


def compile_measurement_spec() -> dict[str, Any]:
    """Read the windows the measurements need from the claims that name them.

    These select which series to compute, not what to conclude, which is why they are
    registered as references and why compiling them here keeps the measurement module free
    of the registry entirely.
    """
    swing = int(doctrine.threshold(_VOLUME_STATE, "swing_baseline_sessions"))
    position = int(doctrine.threshold(_VOLUME_STATE, "position_baseline_sessions"))
    return {
        "volume_baseline_sessions": int(doctrine.threshold(_DRYUP, "volume_baseline_sessions")),
        "breakout_volume_baseline_sessions": (swing, position),
    }


def _summary(claim_id: str) -> str:
    return str(doctrine.get_claim(claim_id)["claim"]["rule"]["summary"])


_REPORTED_PRECISION = 10


def _reported(value: Any) -> Any:
    """Round for the reader only; every comparison above ran on the measurement itself."""

    if isinstance(value, float):
        return round(value, _REPORTED_PRECISION)
    if isinstance(value, list):
        return [_reported(item) for item in value]
    return value


def _observation(claim_id: str, state: str, measured: Any) -> dict[str, Any]:
    """One claim the source states without a number, evaluated on direction alone.

    Binding is read from the registry rather than asserted here. A numberless observation
    is still somebody's standard, and stamping every one of them as binding would be the
    same shortcut `evaluate_gate` refuses to take.
    """
    binding = doctrine.binds(claim_id)
    return {
        "id": claim_id,
        "doctrine_id": claim_id,
        "role": "observation",
        "binds": binding,
        "state": state if binding else f"contrast_{state}" if state in {"pass", "fail"} else state,
        "measured": _reported(measured),
        "required": _summary(claim_id),
    }


def _direction(measured: float | None, satisfied: bool) -> str:
    if measured is None:
        return "unavailable"
    return "pass" if satisfied else "fail"


def _trigger_state(measurements: Mapping[str, Any], expansion: float | None) -> str:
    """Whether the base produced a live breakout, at the session it actually happened on."""

    if measurements.get("pivot") is None:
        return "unavailable"
    if not measurements.get("pivot_cleared"):
        return "not_triggered"
    if expansion is None:
        return "unavailable"
    # Clearing the pivot without expanding volume is not the trigger the source describes;
    # it is the trigger's other half missing. Neither is a breakout out of a pause that had
    # already taken out the base's own low on its way there.
    if not expansion > 1:
        return "fail"
    if not measurements.get("pause_low_held_to_breakout") or not measurements.get("pivot_is_highest_to_breakout"):
        return "fail"
    # `setup.failure_reset_types` says a pivot failure can reset and recover within a small
    # number of days, so a slip below the pivot is counted rather than held against the base
    # forever; what the trigger reads is where price stands now.
    if not measurements.get("currently_above_pivot"):
        return "not_triggered"
    return "pass"


def _asymmetry_state(measurements: Mapping[str, Any]) -> str:
    """The clause the source states with "must": volume bigger on up days than on down days."""

    total = measurements.get("up_down_volume_ratio")
    if total is None:
        return "unavailable"
    return "pass" if total > 1 else "fail"


def _completeness_state(structure: Mapping[str, Any], reading: str | None, source: str | None) -> str:
    """Whether something other than the chain's own author vouched for the chain.

    A caller may say their segmentation is partial -- admitting a gap costs them nothing and
    tells the truth. They may not say it is complete: the reading exists to check the chain,
    and a check the checked party performs is the flag this rewrite removed with a longer
    description on it. `complete` is accepted only from an independent segmentation, which is
    what the swing detector will supply.
    """
    if str(structure.get("state")) != "resolved":
        return "unavailable"
    if reading == "partial":
        return "fail"
    if reading == "complete" and source == "independent_segmentation":
        return "pass"
    return "needs_chart"


def _proximity_state(measurements: Mapping[str, Any], reading: str | None) -> str:
    """The source states the limit and withholds the number, so the reader supplies the call.

    What the measurement can still refuse is a reading of "at the pivot" on an entry the
    stock left behind: if price has closed above the pivot for sessions since the breakout,
    the entry under discussion is not the breakout's.
    """
    if measurements.get("pivot_extension_pct") is None:
        return "unavailable"
    if reading == "chased":
        return "fail"
    if reading == "at_pivot":
        # "As close to the pivot as possible" has a closest available point, and it is the
        # breakout. How much further than that stops being close the source declines to say,
        # but price standing further from the pivot than it did when it left the base is not
        # a reading the bars leave open.
        if not measurements.get("pivot_cleared"):
            return "fail"
        now = measurements.get("pivot_extension_pct")
        at_breakout = measurements.get("pivot_extension_at_breakout_pct")
        if now is None or at_breakout is None:
            return "unavailable"
        return "pass" if now <= at_breakout else "fail"
    return "needs_chart"


def _quieting_state(measurements: Mapping[str, Any]) -> str:
    """"If the stock's price and volume don't quiet down on the right side ... too risky."

    The volume half of that sentence is the pivot-volume contraction, which needs no number
    because a contraction either happened or it did not. The price half says "quiets down
    noticeably", and a strict less-than is not that word: it passed a base whose pause was
    two ten-thousandths of a percentage point tighter. Both medians and the close-to-close
    change are reported, and the reading is the analyst's.
    """
    return "unavailable" if measurements.get("daily_range_median_pct") is None else "reported"


def _spike_state(measurements: Mapping[str, Any]) -> str:
    """The clause the source states with "should", about price rather than volume, in the plural.

    An earlier version compared the largest up-day volume with the largest down-day volume,
    which answers a sentence nobody wrote. Comparing the two largest returns answers the
    right sentence in the singular. "A few of the price spikes ... dwarfing the contractions"
    is plural and comparative, and neither the count nor the comparison with a multi-session
    contraction has a threshold anywhere, so this reports what it counted.
    """
    return "unavailable" if measurements.get("up_days_exceeding_largest_decline") is None else "reported"


def _right_side_state(measurements: Mapping[str, Any], judgment: str | None) -> str:
    """One named form of time compression is measurable; the other is genuinely visual.

    "V-shaped price action or the absence of proper right-side development." The absence is
    an absence and needs no ratio. The V is a shape the source never puts a ratio on, so a
    right side that did develop pauses is unresolved until someone reads the chart -- and a
    reading of "constructive" is refused when the bars show no pause at all, because that is
    the form the measurement can see.
    """
    developed = measurements.get("right_side_contraction_count")
    if developed is None:
        return "unavailable"
    if developed < 1:
        return "fail"
    if judgment == "compressed":
        return "fail"
    if judgment == "constructive":
        return "pass"
    return "needs_chart"


def build_setup_evidence(
    history: Any,
    swings: Sequence[Any] | None = None,
    *,
    entry_kind: str = "completed_pivot",
    tactic_opt_in: bool = False,
    entry: Mapping[str, Any] | None = None,
    right_side_development: str | None = None,
    chain_completeness: str | None = None,
    completeness_source: str | None = None,
    entry_proximity: str | None = None,
) -> dict[str, Any]:
    """Build the mapping :func:`setup.evaluate_setup` reads, plus the contrast beside it."""

    spec = compile_measurement_spec()
    # One normalisation for both halves: sorting and coercing separately let a frame given
    # out of order validate against one reading and be measured against another.
    bars = completed_bars(history)
    structure = resolve_structure(bars if bars is not None else history, list(swings or []))
    measurements = measure(bars if bars is not None else pd.DataFrame(), structure, spec)

    ratios = measurements.get("breakout_volume_ratios") or {}
    position_sessions = spec["breakout_volume_baseline_sessions"][1]
    swing_sessions = spec["breakout_volume_baseline_sessions"][0]
    expansion = ratios.get(position_sessions)

    signals = [
        _observation(_VOLUME_ASYMMETRY, _asymmetry_state(measurements), measurements["up_down_volume_ratio"]),
        _observation(
            _UPSIDE_SPIKES,
            _spike_state(measurements),
            {
                "largest_up_day_return_pct": measurements["largest_up_day_return_pct"],
                "largest_down_day_return_pct": measurements["largest_down_day_return_pct"],
                "up_days_exceeding_largest_decline": measurements["up_days_exceeding_largest_decline"],
                "contraction_depths_pct": measurements["contraction_depths_pct"],
            },
        ),
        _observation(_CHAIN_COMPLETENESS, _completeness_state(structure, chain_completeness, completeness_source), {"structure": structure.get("state"), "source": completeness_source}),
        # Measured inside the base. Borrowing the fifty-day marker's number to decide with
        # would put a value the registry marked undecidable back into a verdict.
        _observation(
            _PIVOT_VOLUME,
            _direction(measurements["pivot_area_volume_ratio_to_base"], (measurements["pivot_area_volume_ratio_to_base"] or 0) < 1),
            measurements["pivot_area_volume_ratio_to_base"],
        ),
        _observation(
            _CONTRACTIONS_CONTRACT,
            "unavailable" if measurements["contractions_contract"] is None else ("pass" if measurements["contractions_contract"] else "fail"),
            measurements["contraction_depths_pct"],
        ),
        _observation(_PIVOT_TRIGGER, _trigger_state(measurements, expansion), measurements.get("pivot_extension_pct")),
        _observation(_TIME_COMPRESSION, _right_side_state(measurements, right_side_development), measurements["right_to_left_session_ratio"]),
        # How deep the base ran was measured and then never looked at, so a stock that had
        # more than halved could measure as a clean VCP inside its own ruin.
        doctrine.evaluate_gate(_CORRECTION_DEPTH, "correction_failure_threshold", measurements["peak_to_low_correction_pct"]),
        doctrine.evaluate_band(_CORRECTION_DEPTH, "healthy_correction_range", measurements["peak_to_low_correction_pct"]),
        doctrine.evaluate_band(_FOOTPRINT, "consolidation_footprint_duration_weeks", measurements["base_duration_weeks"]),
        _observation(
            _OVERHEAD_SUPPLY,
            _quieting_state(measurements),
            {
                "pause_daily_range_median_pct": measurements["daily_range_median_pct"],
                "base_daily_range_median_pct": measurements["base_daily_range_median_pct"],
                "pause_close_change_median_pct": measurements["close_change_median_pct"],
                "overhead_supply_above_pivot_pct": measurements["overhead_supply_above_pivot_pct"],
                "overhead_supply_high": measurements["overhead_supply_high"],
            },
        ),
        _observation(
            _FAILURE_RESET,
            "unavailable" if measurements.get("failed_pivot_attempts") is None else "reported",
            measurements.get("failed_pivot_attempts"),
        ),
        _observation(
            _CHASE_LIMIT,
            _proximity_state(measurements, entry_proximity),
            {
                "pivot_extension_pct": measurements.get("pivot_extension_pct"),
                "pivot_extension_at_breakout_pct": measurements.get("pivot_extension_at_breakout_pct"),
                "sessions_since_breakout": measurements.get("sessions_since_breakout"),
            },
        ),
        doctrine.evaluate_band(_CONTRACTION_COUNT, "contraction_count", measurements["contraction_count"] or None),
        doctrine.evaluate_marker(_HALVING, "successive_depth_ratio", measurements["successive_depth_ratios"][-1] if measurements["successive_depth_ratios"] else None),
        doctrine.evaluate_marker(_DRYUP, "final_contraction_volume_ratio", measurements["final_contraction_volume_ratio"]),
        doctrine.evaluate_marker(*_MINERVINI_BREAKOUT, _percent_increase(expansion)),
    ]

    contrast = [
        doctrine.evaluate_gate(*_RYAN_BREAKOUT, _percent_increase(expansion)),
        doctrine.evaluate_gate(*_ZANGER_BREAKOUT, _percent_increase(ratios.get(swing_sessions))),
        doctrine.evaluate_marker(_CLOSING_RANGE, "closing_range_midpoint_pct", measurements["closing_range_pct"]),
    ]

    return {
        "structure": structure,
        "measurements": measurements,
        # Named separately from the measurements so a reader can see at a glance how much of
        # this verdict came from a person. Everything else is measured and cannot be declared
        # away; these three cover only what completed bars cannot settle.
        "declared_readings": {
            name: value
            for name, value in (
                ("right_side_development", right_side_development),
                ("chain_completeness", chain_completeness),
                ("entry_proximity", entry_proximity),
            )
            if value is not None
        },
        "signals": signals,
        "contrast": contrast,
        "entry": {"kind": entry_kind, "opt_in": tactic_opt_in is True, **(dict(entry) if isinstance(entry, Mapping) else {})},
    }


def _percent_increase(ratio: float | None) -> float | None:
    """Practitioner standards are stated as a percentage above an average, not as a ratio."""

    return None if ratio is None else (ratio - 1) * 100


__all__ = ["build_setup_evidence", "compile_measurement_spec"]
