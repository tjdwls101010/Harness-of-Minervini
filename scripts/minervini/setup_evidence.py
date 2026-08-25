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
    claim = doctrine.get_claim(claim_id)["claim"]
    binds = claim["layer"] == "canonical" and claim.get("attributed_to") == "Minervini"
    return {
        "id": claim_id,
        "doctrine_id": claim_id,
        "role": "observation",
        "binds": binds,
        "state": state if binds else f"contrast_{state}" if state in {"pass", "fail"} else state,
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
    # it is the trigger's other half missing. A breakout that later closed back under the
    # pivot, or a pause that broke its own low on the way there, is not a live trigger either.
    if not expansion > 1:
        return "fail"
    if not measurements.get("breakout_held") or not measurements.get("pause_held_to_breakout"):
        return "fail"
    return "pass"


def _asymmetry_state(measurements: Mapping[str, Any]) -> str:
    """Both clauses of the source's sentence, neither of which carries a number."""

    total = measurements.get("up_down_volume_ratio")
    spike = measurements.get("largest_up_to_down_volume_ratio")
    if total is None or spike is None:
        return "unavailable"
    return "pass" if total > 1 and spike > 1 else "fail"


def _right_side_state(measurements: Mapping[str, Any]) -> str:
    """"The absence of proper right-side development" is the form that needs no ratio.

    The other form the source names is V-shaped price action, and it supplies no ratio for
    that one, so the left-to-right duration ratio travels with this rather than deciding it.
    """
    developed = measurements.get("right_side_contraction_count")
    if developed is None:
        return "unavailable"
    return "pass" if developed >= 1 else "fail"


def build_setup_evidence(
    history: Any,
    swings: Sequence[Any] | None = None,
    *,
    entry_kind: str = "completed_pivot",
    tactic_opt_in: bool = False,
    entry: Mapping[str, Any] | None = None,
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
        _observation(_TIME_COMPRESSION, _right_side_state(measurements), measurements["right_to_left_session_ratio"]),
        # How deep the base ran was measured and then never looked at, so a stock that had
        # more than halved could measure as a clean VCP inside its own ruin.
        doctrine.evaluate_gate(_CORRECTION_DEPTH, "correction_failure_threshold", measurements["base_depth_pct"]),
        doctrine.evaluate_band(_CORRECTION_DEPTH, "healthy_correction_range", measurements["base_depth_pct"]),
        doctrine.evaluate_band(_FOOTPRINT, "consolidation_footprint_duration_weeks", measurements["base_duration_weeks"]),
        _observation(
            _OVERHEAD_SUPPLY,
            "unavailable" if measurements["overhead_supply_above_pivot_pct"] is None else "reported",
            measurements["overhead_supply_above_pivot_pct"],
        ),
        _observation(
            _CHASE_LIMIT,
            "unavailable" if measurements.get("pivot_extension_pct") is None else "reported",
            measurements.get("pivot_extension_pct"),
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
        "signals": signals,
        "contrast": contrast,
        "entry": {"kind": entry_kind, "opt_in": tactic_opt_in is True, **(dict(entry) if isinstance(entry, Mapping) else {})},
    }


def _percent_increase(ratio: float | None) -> float | None:
    """Practitioner standards are stated as a percentage above an average, not as a ratio."""

    return None if ratio is None else (ratio - 1) * 100


__all__ = ["build_setup_evidence", "compile_measurement_spec"]
