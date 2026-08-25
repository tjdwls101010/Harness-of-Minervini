"""Pure verdict reducer for prospective entries and active positions."""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from typing import Any

from . import doctrine


# Enough places to strip binary-float noise from a reported figure and far too many
# to soften any limit the registry states.
_REPORTED_PRECISION = 10
_ENTRY_RISK = "risk.initial_stop_and_reward"
_PROFIT_PROTECTION = "risk.profit_protection_at_3r"

# `waived_by_exception` is deliberately absent. It is the one word in this vocabulary that
# claims an absence of evidence has been forgiven, and it was reachable by writing it: with
# nothing else supplied, `--fundamentals-state waived_by_exception` produced BUY-READY on a
# ticker whose fundamentals nobody had looked at and whose Power Play nothing had measured.
# The exception is real, but it is earned by measurement plus an approved chart, and no
# reducer that reads caller-supplied state words is in a position to check that it was.
_PASS = {"pass", "ready", "confirmed", "eligible", "supports", "observed", "complete", "favorable", "supports_convergence"}
_FAIL = {"fail", "failed", "avoid", "contradicts", "broken", "invalid", "does_not_support_convergence"}
_WAIT = {"wait", "pending", "watch", "not_triggered", "cautious", "defensive"}
_MISSING = {"unavailable", "needs_input", "needs_chart", "incomplete", "unknown"}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _state(value: Any, default: str = "unavailable") -> str:
    if isinstance(value, bool):
        return "pass" if value else "fail"
    if isinstance(value, Mapping):
        setup_state = value.get("setup_state")
        if setup_state is not None:
            value = setup_state
        else:
            value = value.get("state", value.get("status"))
    if value is None:
        return default
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized in _PASS:
        return "pass"
    if normalized in _FAIL:
        return "fail"
    if normalized in _WAIT:
        return "wait"
    if normalized in _MISSING:
        return "unavailable"
    return default


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0 and math.isfinite(value):
        return float(value)
    return None


def _risk_value(payload: Mapping[str, Any], name: str) -> Any:
    risk = payload.get("risk")
    if isinstance(risk, Mapping) and name in risk:
        return risk[name]
    return payload.get(name)


def _prospective(payload: Mapping[str, Any]) -> dict[str, Any]:
    components = {name: _state(payload.get(name)) for name in ("market", "eligibility", "setup", "fundamentals")}
    risk_input = _mapping(payload.get("risk"))
    has_risk_inputs = bool(risk_input) or any(
        payload.get(name) is not None for name in ("entry_price", "stop_price", "upside_price", "target_price", "average_gain_pct")
    )
    risk_state = _state(risk_input, default="pass" if has_risk_inputs else "unavailable")
    failed: list[str] = []
    missing: list[str] = []
    waiting: list[str] = []

    for name in ("eligibility", "setup", "fundamentals"):
        if components[name] == "fail":
            failed.append(name)
        elif components[name] == "unavailable":
            missing.append(name)
        elif components[name] == "wait":
            waiting.append(name)
    if components["market"] == "unavailable":
        missing.append("market")
    elif components["market"] in {"fail", "wait"}:
        waiting.append("market")

    entry = _number(_risk_value(payload, "entry_price"))
    stop = _number(_risk_value(payload, "stop_price"))
    upside = _number(_risk_value(payload, "upside_price")) or _number(_risk_value(payload, "target_price"))
    average_gain = _number(_risk_value(payload, "average_gain_pct"))
    stop_ceiling = doctrine.threshold(_ENTRY_RISK, "initial_stop_ceiling_pct")
    average_gain_multiple = doctrine.threshold(_ENTRY_RISK, "half_average_gain_multiple")
    controls: dict[str, Any] = {
        "initial_stop_pct": None,
        "initial_stop_cap_pct": stop_ceiling,
        "half_average_gain_cap_pct": round(average_gain * average_gain_multiple, 4) if average_gain else None,
        "loss_target": None,
        "reward_to_risk": None,
        "minimum_reward_to_risk": doctrine.threshold(_ENTRY_RISK, "reward_to_risk_minimum"),
        "preferred_reward_to_risk": doctrine.threshold(_ENTRY_RISK, "reward_to_risk_preferred"),
        "breakeven_at_r": doctrine.threshold(_PROFIT_PROTECTION, "breakeven_protection_trigger_r"),
    }

    if risk_state == "fail":
        failed.append("risk")
    elif risk_state == "unavailable":
        missing.append("risk")
    elif risk_state == "wait":
        waiting.append("risk")

    if entry is None:
        missing.append("entry_price")
    if stop is None:
        missing.append("stop_price")
    if upside is None:
        missing.append("upside_price")
    if average_gain is None:
        # The half-average-gain cap is the tighter of the two stop ceilings for most
        # traders, so an absent realized average gain hides a gate rather than relaxing one.
        missing.append("average_gain_pct")
    if entry is not None and stop is not None:
        if stop >= entry:
            failed.append("initial_stop_price")
        else:
            # Rounded for the reader, never for the comparison: a value tidied to the
            # limit before it is checked is a tolerance the gate design forbids.
            stop_pct = (entry - stop) / entry * 100
            controls["initial_stop_pct"] = round(stop_pct, _REPORTED_PRECISION)
            # The source gives the ordinary loss target as a range, so the reading
            # travels with its range instead of collapsing to a pass.
            controls["loss_target"] = doctrine.evaluate_band(_ENTRY_RISK, "ordinary_loss_target_pct", stop_pct)
            if doctrine.evaluate_gate(_ENTRY_RISK, "initial_stop_ceiling_pct", stop_pct)["state"] == "fail":
                failed.append("initial_stop_pct")
            if average_gain is not None and stop_pct > average_gain * average_gain_multiple:
                failed.append("half_average_gain_cap")
            if upside is not None:
                reward_to_risk = (upside - entry) / (entry - stop)
                controls["reward_to_risk"] = round(reward_to_risk, _REPORTED_PRECISION)
                if doctrine.evaluate_gate(_ENTRY_RISK, "reward_to_risk_minimum", reward_to_risk)["state"] == "fail":
                    failed.append("reward_to_risk")
    elif entry is not None and upside is not None and upside <= entry:
        failed.append("upside_price")

    if failed:
        verdict = "AVOID"
    elif missing:
        verdict = "INCOMPLETE"
    elif waiting:
        verdict = "WAIT"
    else:
        verdict = "BUY-READY"
    return {
        "mode": "prospective",
        "verdict": verdict,
        "components": {**components, "risk": risk_state},
        "risk_controls": controls,
        "failed": list(dict.fromkeys(failed)),
        "missing": list(dict.fromkeys(missing)),
        "waiting": list(dict.fromkeys(waiting)),
    }


def _status_word(value: Any) -> str:
    """The one way this module reads a state, so two readers cannot disagree."""

    if not isinstance(value, Mapping):
        return ""
    return str(value.get("state", value.get("status", ""))).strip().lower()


def _triggered(value: Any) -> bool:
    return _status_word(value) in {"triggered", "breached"}


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _audit_records(path: Mapping[str, Any], path_state: str) -> list[dict[str, Any]]:
    """Per-level audit records; a single-level path counts as one record."""

    audits = path.get("audits")
    if isinstance(audits, list):
        return [dict(item) for item in audits if isinstance(item, Mapping)]
    if not path:
        return []
    return [
        {
            "level": path.get("checked_level"),
            "role": "stop",
            "effective_from": path.get("from"),
            "through": path.get("through"),
            "bars_checked": path.get("bars_checked"),
            "state": path_state,
        }
    ]


def _audited(records: list[Mapping[str, Any]], level: float, required_from: date | None, as_of: date | None) -> bool:
    """Whether some record cleared ``level`` over every session from ``required_from`` to ``as_of``."""

    if required_from is None or as_of is None:
        return False
    for record in records:
        audited_level = _number(record.get("level"))
        if audited_level is None or audited_level < level:
            continue
        if _status_word(record) != "clear":
            continue
        # A window that starts late leaves the sessions before it unexamined, and one
        # that ends early cannot speak for the sessions after it.
        effective_from = _iso_date(record.get("effective_from"))
        through = _iso_date(record.get("through"))
        if effective_from is None or through is None:
            continue
        if effective_from > required_from or through < as_of:
            continue
        bars = record.get("bars_checked")
        if not isinstance(bars, int) or isinstance(bars, bool) or bars < 1:
            continue
        return True
    return False


def _exit_plan(payload: Mapping[str, Any]) -> tuple[float | None, bool]:
    """The invalidation's auditable level and whether it carries a real condition."""

    invalidation = _mapping(payload.get("invalidation"))
    condition = invalidation.get("condition")
    return _number(invalidation.get("price")), isinstance(condition, str) and bool(condition.strip())


def declares_exit_plan(evidence: Mapping[str, Any]) -> bool:
    """Whether an exit level or condition was actually declared.

    A mapping that carries only a status declares no level and no condition, so
    there is nothing for a "triggered" flag to be a trigger of.
    """

    payload = _mapping(evidence)
    invalidation_price, has_condition = _exit_plan(payload)
    return payload.get("stop_price") is not None or invalidation_price is not None or has_condition


def settled_breach(evidence: Mapping[str, Any]) -> bool:
    """Whether the evidence already settles the verdict without completed price history.

    The operation asks this before fetching bars: a breach it would never look at
    is a request that can only downgrade a terminal SELL to a partial one.
    """

    payload = _mapping(evidence)
    if payload.get("mode") != "active":
        return False
    invalidation = _mapping(payload.get("invalidation"))
    invalidation_price, _ = _exit_plan(payload)
    stop = _number(payload.get("stop_price"))
    current = _number(payload.get("current_price"))
    levels = [level for level in (stop, invalidation_price) if level is not None]
    live_stop = _mapping(payload.get("live_stop"))
    return (
        (bool(payload.get("live_stop_check")) and live_stop.get("partial_session") is True and _triggered(live_stop))
        or _triggered(payload.get("completed_stop"))
        or _triggered(payload.get("stop_event"))
        or _triggered(payload.get("completed_price_path"))
        or (declares_exit_plan(payload) and _triggered(invalidation))
        or (current is not None and bool(levels) and current <= max(levels))
    )


def _active(payload: Mapping[str, Any]) -> dict[str, Any]:
    as_of = _iso_date(payload.get("as_of"))
    entry = _number(payload.get("entry_price"))
    entry_date = _iso_date(payload.get("entry_date"))
    stop = _number(payload.get("stop_price"))
    invalidation = _mapping(payload.get("invalidation"))
    invalidation_price, has_condition = _exit_plan(payload)
    declared_plan = declares_exit_plan(payload)
    # A stop raised later is only in force from its own date; the structural
    # invalidation has stood since entry.
    stop_effective_date = _iso_date(payload.get("stop_effective_date"))
    stop_from = stop_effective_date or entry_date
    protective_plan = [
        (level, required_from)
        for level, required_from in ((stop, stop_from), (invalidation_price, entry_date))
        if level is not None
    ]

    # Anchors describe whether the request is a coherent position at all. A breach
    # outranks evidence nobody gathered, but never a request that contradicts itself.
    anchors: list[str] = []
    if as_of is None:
        anchors.append("as_of")
    if entry_date is None:
        anchors.append("entry_date")
    if entry_date is not None and as_of is not None and entry_date > as_of:
        anchors.append("entry_date_after_as_of")
    if stop_effective_date is not None and entry_date is not None and stop_effective_date < entry_date:
        anchors.append("stop_effective_date_before_entry_date")
    if stop_effective_date is not None and as_of is not None and stop_effective_date > as_of:
        anchors.append("stop_effective_date_after_as_of")
    if not declared_plan:
        anchors.append("stop_or_invalidation")

    live_stop = _mapping(payload.get("live_stop"))
    live_triggered = bool(payload.get("live_stop_check")) and live_stop.get("partial_session") is True and _triggered(live_stop)
    current = _number(payload.get("current_price"))
    completed_price_path = _mapping(payload.get("completed_price_path"))
    path_state = _status_word(completed_price_path)
    completed_stop = _triggered(payload.get("completed_stop")) or _triggered(payload.get("stop_event")) or _triggered(completed_price_path) or (current is not None and stop is not None and current <= stop)
    invalidation_price_breach = current is not None and invalidation_price is not None and current <= invalidation_price
    invalidation_triggered = _triggered(invalidation) or invalidation_price_breach
    breached = live_triggered or completed_stop or invalidation_triggered

    gaps: list[str] = []
    if not breached:
        if entry is None:
            # Entry economics decide 3R protection, never whether a level was breached.
            gaps.append("entry_price")
        if current is None:
            gaps.append("current_price")
        if declared_plan and not protective_plan:
            # A condition nobody can evaluate against completed bars, or a price that
            # is not a price, leaves nothing for the audit to clear.
            gaps.append("auditable_protective_level")
        if protective_plan:
            records = _audit_records(completed_price_path, path_state)
            if path_state != "clear" or not all(_audited(records, level, required_from, as_of) for level, required_from in protective_plan):
                gaps.append("completed_price_path")
        if invalidation_price is None and has_condition:
            # HOLD asserts nothing has invalidated the thesis; an exit condition the
            # harness never evaluated cannot be part of that assertion.
            gaps.append("invalidation_condition_not_audited")

    breakeven_at_r = doctrine.threshold(_PROFIT_PROTECTION, "breakeven_protection_trigger_r")
    controls = {"breakeven_at_r": breakeven_at_r, "breakeven_protection_required": False}
    reasons: list[str] = []
    if anchors:
        verdict = "INCOMPLETE"
        missing = anchors + gaps
    elif breached:
        verdict = "SELL"
        missing = []
        reasons = ["live_stop_breach" if live_triggered else "completed_stop_breach" if completed_stop else "invalidation_triggered" if _triggered(invalidation) else "invalidation_breach"]
    elif gaps:
        verdict = "INCOMPLETE"
        missing = gaps
    else:
        verdict = "HOLD"
        missing = []
        if entry is not None and stop is not None and current is not None and stop < entry:
            initial_risk = entry - stop
            if initial_risk > 0 and doctrine.evaluate_gate(_PROFIT_PROTECTION, "breakeven_protection_trigger_r", (current - entry) / initial_risk)["state"] == "pass":
                controls["breakeven_protection_required"] = True
    return {
        "mode": "active",
        "verdict": verdict,
        "risk_controls": controls,
        "completed_price_path": completed_price_path or None,
        "failed": reasons,
        "missing": missing,
        "waiting": [],
    }


def reduce_risk(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return the only final verdict: prospective or active, from evidence objects."""

    payload = _mapping(evidence)
    return _active(payload) if payload.get("mode") == "active" else _prospective(payload)
