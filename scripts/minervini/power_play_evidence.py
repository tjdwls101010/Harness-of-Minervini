"""Wire the Power Play measurements to the claim they are read against.

The measurement module knows no doctrine and takes its windows as an argument; this is where
those windows come from. Both are the source's own limits -- eight weeks of advance, six of
flag -- converted to sessions through a registered parameter rather than a constant, because
whether a thirty-one session flag is inside six weeks is a verdict that conversion decides.

Enforcing a limit by not looking past it is not the same as forgiving what lies beyond. The
advance is searched inside the eight weeks the criterion allows, so a stock that took nine
weeks to double reports whatever it managed in eight and fails on that number.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import doctrine
from .power_play import measure_power_play, reading_rejects


_CLAIM = "fundamentals.power_play_exception"
_WEEK = "convention.trading_week"


def compile_power_play_spec() -> dict[str, Any]:
    """The two search windows, in completed sessions."""

    week = int(doctrine.parameter(_WEEK, "sessions_per_trading_week"))
    return {
        "advance_window_sessions": int(doctrine.threshold(_CLAIM, "advance_maximum_weeks")) * week,
        "flag_window_sessions": int(doctrine.threshold(_CLAIM, "flag_maximum_weeks")) * week,
        # Carried rather than re-derived, so the module that reports durations in weeks converts
        # them the same way the windows were compiled.
        "sessions_per_trading_week": week,
    }





def _summary(claim_id: str) -> str:
    return str(doctrine.get_claim(claim_id)["claim"]["rule"]["summary"])


def _observation(condition: str, state: str, measured: Any, required: str) -> dict[str, Any]:
    """One criterion the source states without a magnitude, reported under its own name.

    The id carries the condition and the doctrine_id carries the claim, because four separate
    criteria live inside this one exception and a signal named only after the claim would have
    them overwrite each other. Prefix lookup finds the claim from the id, which is how the rest
    of the engine already resolves a threshold's owner.
    """
    return {
        "id": f"{_CLAIM}.{condition}",
        "doctrine_id": _CLAIM,
        "role": "observation",
        "binds": doctrine.binds(_CLAIM),
        "state": state,
        "measured": measured,
        "required": required,
    }


def _volume_state(ratio: float | None) -> str:
    """"An explosive price move commences on huge volume."

    No magnitude is attached to "huge", so no ratio here can pass it -- but an advance with no
    expanded session anywhere in it did not commence on huge volume under any reading of which
    session was its first, and observing that needs no number. Everything above that line is the
    chart's to answer.
    """
    if ratio is None:
        return "unavailable"
    return "needs_chart" if ratio > 1 else "fail"


def _tightness_state(depth: float | None, limit: float) -> str:
    """"very tight price action that doesn't correct ... more than 10 percent, or ... VCP."

    An or, and evaluating the tight half alone would turn the source's alternative into a
    requirement. A flag inside ten percent satisfies the criterion on measurement. One outside it
    has not failed the criterion; it has fallen to the other branch, and whether a flag shows VCP
    character over twelve to thirty sessions is not something these bars settle.
    """
    if depth is None:
        return "unavailable"
    return "pass" if depth <= limit else "needs_chart"


def _criteria(measurements: Mapping[str, Any], tight_limit: float) -> dict[str, str]:
    """How each criterion reads on one set of measurements, without the payloads."""

    return {
        "advance_minimum_pct": doctrine.evaluate_gate(_CLAIM, "advance_minimum_pct", measurements["advance_pct_closes"])["state"],
        "advance_maximum_weeks": doctrine.evaluate_gate(_CLAIM, "advance_maximum_weeks", measurements["advance_weeks"])["state"],
        "flag_minimum_sessions": doctrine.evaluate_gate(_CLAIM, "flag_minimum_sessions", measurements["flag_sessions"])["state"],
        "flag_maximum_weeks": doctrine.evaluate_gate(_CLAIM, "flag_maximum_weeks", measurements["flag_weeks"])["state"],
        "flag_maximum_decline_gate_pct": doctrine.evaluate_gate(_CLAIM, "flag_maximum_decline_gate_pct", measurements["flag_depth_pct"])["state"],
        "launch_volume_character": _volume_state(measurements["advance_peak_volume_ratio"]),
        "flag_tightness_or_vcp": _tightness_state(measurements["flag_depth_pct"], tight_limit),
    }


def _rejects(measurements: Mapping[str, Any], tight_limit: float) -> bool:
    """Whether this reading rejects on the strength of its own span.

    Each reading carries its own corporate-action span, because the two structures cover
    different sessions and a split inside one of them says nothing about the other.
    """
    unmoved = (
        measurements["corporate_action_evidence"] == "present"
        and not measurements["corporate_action_sessions"]
    )
    return reading_rejects(_criteria(measurements, tight_limit), corporate_action_unmoved=unmoved)


def build_power_play_evidence(history: Any) -> dict[str, Any]:
    """Measure a history and read the criteria against it, deciding nothing.

    The structure is found rather than declared, so the same bars are read twice: once from the
    highest top of the search span, and once from the highest top below it. When the two readings
    answer the criteria the same way, which one the search happened to land on did not matter.
    When they differ, the verdict rests on a choice the bars did not make, and the source names
    no size below which a new high stops counting -- a hundredth of a percent above the last high
    restarts the flag and turns twenty sessions into four. Neither is vouched for then.

    The same rule the segmentation already runs on its own parameters, for the same reason.
    """

    spec = compile_power_play_spec()
    measurements = measure_power_play(history, spec)
    tight_limit = float(doctrine.threshold(_CLAIM, "tight_action_maximum_pct"))
    actions = measurements["corporate_action_sessions"]
    alternate = (
        measure_power_play(history, spec, below=measurements["peak_high"], before=measurements["peak_date"])
        if measurements["peak_high"] is not None
        else measurements
    )
    # An earlier top the search span does not contain is not a competing reading of this
    # structure; there is nothing to disagree with.
    primary_criteria = _criteria(measurements, tight_limit)
    contested = (
        {
            condition
            for condition, state in primary_criteria.items()
            if _criteria(alternate, tight_limit)[condition] != state
        }
        if alternate["rejection"] is None
        else set()
    )

    signals = [
        # The close-to-close reading, because the criterion is about the stock's price rather
        # than about the widest pair of prints inside two sessions. Read on the extremes, a single
        # intraday wick to half the peak reported a hundred and four percent advance on a stock
        # whose close moved half a percent. The extremes reading travels in the measurements.
        doctrine.evaluate_gate(_CLAIM, "advance_minimum_pct", measurements["advance_pct_closes"]),
        doctrine.evaluate_gate(_CLAIM, "advance_maximum_weeks", measurements["advance_weeks"]),
        doctrine.evaluate_gate(_CLAIM, "flag_minimum_sessions", measurements["flag_sessions"]),
        doctrine.evaluate_gate(_CLAIM, "flag_maximum_weeks", measurements["flag_weeks"]),
        doctrine.evaluate_gate(_CLAIM, "flag_maximum_decline_gate_pct", measurements["flag_depth_pct"]),
        doctrine.evaluate_band(_CLAIM, "flag_duration_weeks", measurements["flag_weeks"]),
        doctrine.evaluate_band(_CLAIM, "flag_maximum_decline_pct", measurements["flag_depth_pct"]),
        _observation(
            "launch_volume_character",
            _volume_state(measurements["advance_peak_volume_ratio"]),
            {
                "advance_peak_volume_ratio": measurements["advance_peak_volume_ratio"],
                "advance_peak_volume_date": measurements["advance_peak_volume_date"],
                "launch_volume_ratio": measurements["launch_volume_ratio"],
                "advance_volume_ratio": measurements["advance_volume_ratio"],
            },
            "the advance commences on huge volume",
        ),
        _observation(
            "flag_tightness_or_vcp",
            _tightness_state(measurements["flag_depth_pct"], tight_limit),
            {"flag_depth_pct": measurements["flag_depth_pct"], "tight_action_maximum_pct": tight_limit},
            f"the flag corrects no more than {tight_limit} percent, or shows VCP characteristics",
        ),
    ]
    return {
        # Whether every reading of these bars rejects, whatever each one rejected on. Computed
        # here because it is a fact about the two readings, and the reducer only ever sees one.
        "rejected_under_every_reading": bool(contested)
        and _rejects(measurements, tight_limit)
        and _rejects(alternate, tight_limit),
        "structure": {
            "state": "unavailable" if measurements["rejection"] else "measured",
            "rejection": measurements["rejection"],
        },
        "peak_identity": "disputed" if contested else "settled",
        # Which criteria the choice of top actually moved. The reducer reads this rather than the
        # summary word, because agreeing on the verdict is not agreeing on every criterion: two
        # readings can both reject and still disagree about which limit did it, and reporting the
        # primary reading's version of that as a confident failure is a finding about the search.
        "contested_criteria": sorted(contested),
        "alternate_peak": None if not contested else {
            "peak_date": alternate["peak_date"],
            "peak_high": alternate["peak_high"],
            "flag_sessions": alternate["flag_sessions"],
            "flag_depth_pct": alternate["flag_depth_pct"],
            "advance_pct_closes": alternate["advance_pct_closes"],
        },
        # Separate from the signals because it is a fact about the input rather than about the
        # stock: a history that does not carry the event column has not reported "no split".
        "corporate_action_evidence": measurements["corporate_action_evidence"],
        "corporate_action_sessions": actions,
        "spec": spec,
        "measurements": measurements,
        "signals": signals,
    }


__all__ = ["build_power_play_evidence", "compile_power_play_spec"]
