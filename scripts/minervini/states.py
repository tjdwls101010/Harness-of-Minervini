"""State readers with separate vocabularies for each decision plane."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

SETUP_STATES = {
    "pass": frozenset({"complete", "confirmed", "eligible", "observed", "pass", "ready", "supports"}),
    "fail": frozenset({"avoid", "broken", "contradicts", "fail", "failed", "invalid"}),
    "wait": frozenset({"not_triggered", "pending", "wait", "watch"}),
    "unavailable": frozenset({"incomplete", "needs_chart", "needs_input", "unavailable", "unknown"}),
}

RISK_STATES = {
    "pass": frozenset({"complete", "confirmed", "eligible", "favorable", "observed", "pass", "ready", "supports", "supports_convergence"}),
    "fail": frozenset({"avoid", "broken", "contradicts", "does_not_support_convergence", "fail", "failed", "invalid"}),
    "wait": frozenset({"cautious", "defensive", "not_triggered", "pending", "wait", "watch"}),
    "unavailable": frozenset({"incomplete", "needs_chart", "needs_input", "unavailable", "unknown"}),
}

MARKET_STATES = frozenset(
    {
        "supports",
        "contradicts",
        "mixed",
        "observed",
        "unavailable",
        "needs_input",
        "needs_chart",
        "not_applicable",
    }
)


def mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def state(value: Any, default: str = "unavailable", alias: str | None = None, *, vocabulary: Mapping[str, frozenset[str]] = RISK_STATES) -> str:
    if isinstance(value, bool):
        return "pass" if value else "fail"
    if isinstance(value, Mapping):
        # A plane's own capability names its verdict after the plane -- `setup_state`,
        # `eligibility_state` -- so a caller pasting that payload in is understood. The alias
        # is per plane rather than shared: read for every object, `setup_state` spoke for the
        # risk plane too, and `{"state": "fail", "setup_state": "ready"}` turned a declared
        # risk failure into a pass.
        aliased = value.get(alias) if alias else None
        if aliased is not None:
            value = aliased
        else:
            value = value.get("state", value.get("status"))
    if value is None:
        return default
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized in vocabulary["pass"]:
        return "pass"
    if normalized in vocabulary["fail"]:
        return "fail"
    if normalized in vocabulary["wait"]:
        return "wait"
    if normalized in vocabulary["unavailable"]:
        return "unavailable"
    return default


def status_word(value: Any) -> str:
    """The one way this module reads a state, so two readers cannot disagree."""

    if not isinstance(value, Mapping):
        return ""
    return str(value.get("state", value.get("status", ""))).strip().lower()
