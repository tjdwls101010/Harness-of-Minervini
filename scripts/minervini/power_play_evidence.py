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

from typing import Any

from . import doctrine
from .power_play import measure_power_play


_CLAIM = "fundamentals.power_play_exception"
_WEEK = "convention.trading_week"


def compile_power_play_spec() -> dict[str, Any]:
    """The two search windows, in completed sessions."""

    week = int(doctrine.parameter(_WEEK, "sessions_per_trading_week"))
    return {
        "advance_window_sessions": int(doctrine.threshold(_CLAIM, "advance_maximum_weeks")) * week,
        "flag_window_sessions": int(doctrine.threshold(_CLAIM, "flag_maximum_weeks")) * week,
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


def build_power_play_evidence(history: Any) -> dict[str, Any]:
    """Measure a history and read the criteria against it, deciding nothing."""

    spec = compile_power_play_spec()
    measurements = measure_power_play(history, spec)
    tight_limit = float(doctrine.threshold(_CLAIM, "tight_action_maximum_pct"))
    actions = measurements["corporate_action_sessions"]

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
        "structure": {
            "state": "unavailable" if measurements["rejection"] else "measured",
            "rejection": measurements["rejection"],
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
