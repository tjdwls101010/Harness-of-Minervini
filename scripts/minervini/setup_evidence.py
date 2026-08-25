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
from .setup_structure import resolve_structure


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


def _observation(claim_id: str, state: str, measured: Any) -> dict[str, Any]:
    """One claim the source states without a number, evaluated on direction alone."""

    return {
        "id": claim_id,
        "doctrine_id": claim_id,
        "role": "observation",
        "binds": True,
        "state": state,
        "measured": measured,
        "required": _summary(claim_id),
    }


def _direction(measured: float | None, satisfied: bool) -> str:
    if measured is None:
        return "unavailable"
    return "pass" if satisfied else "fail"


def _trigger_state(measurements: Mapping[str, Any], expansion: float | None) -> str:
    cleared = measurements.get("pivot_cleared")
    if cleared is None or expansion is None:
        return "unavailable"
    if not cleared:
        return "not_triggered"
    # Clearing the pivot without expanding volume is not the trigger the source describes;
    # it is the trigger's other half missing, which is a failure rather than a wait.
    return "pass" if expansion > 1 else "fail"


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
    structure = resolve_structure(history, list(swings or []))
    bars = history if isinstance(history, pd.DataFrame) else None
    measurements = measure(bars, structure, spec) if bars is not None else measure(pd.DataFrame(), structure, spec)

    ratios = measurements.get("breakout_volume_ratios") or {}
    position_sessions = spec["breakout_volume_baseline_sessions"][1]
    swing_sessions = spec["breakout_volume_baseline_sessions"][0]
    expansion = ratios.get(position_sessions)

    signals = [
        _observation(
            _VOLUME_ASYMMETRY,
            _direction(measurements["up_down_volume_ratio"], (measurements["up_down_volume_ratio"] or 0) > 1),
            measurements["up_down_volume_ratio"],
        ),
        _observation(
            _PIVOT_VOLUME,
            _direction(measurements["final_contraction_volume_ratio"], (measurements["final_contraction_volume_ratio"] or 0) < 1),
            measurements["final_contraction_volume_ratio"],
        ),
        _observation(
            _CONTRACTIONS_CONTRACT,
            "unavailable" if measurements["contractions_contract"] is None else ("pass" if measurements["contractions_contract"] else "fail"),
            measurements["contraction_depths_pct"],
        ),
        _observation(_PIVOT_TRIGGER, _trigger_state(measurements, expansion), measurements.get("pivot_extension_pct")),
        _observation(
            _TIME_COMPRESSION,
            "unavailable" if measurements["right_to_left_session_ratio"] is None else "reported",
            measurements["right_to_left_session_ratio"],
        ),
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
