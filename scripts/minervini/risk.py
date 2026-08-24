"""Pure verdict reducer for prospective entries and active positions."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from typing import Any


_PASS = {"pass", "ready", "confirmed", "eligible", "supports", "observed", "complete", "favorable", "supports_convergence", "waived_by_exception"}
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
    if isinstance(value, (int, float)) and value > 0:
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

    setup = _mapping(payload.get("setup"))
    fundamentals = _mapping(payload.get("fundamentals"))
    if components["fundamentals"] == "unavailable" and fundamentals.get("power_play_exception") is True and setup.get("power_play_qualified") is True:
        missing.remove("fundamentals")

    entry = _number(_risk_value(payload, "entry_price"))
    stop = _number(_risk_value(payload, "stop_price"))
    upside = _number(_risk_value(payload, "upside_price")) or _number(_risk_value(payload, "target_price"))
    average_gain = _number(_risk_value(payload, "average_gain_pct"))
    controls: dict[str, Any] = {
        "initial_stop_pct": None,
        "initial_stop_cap_pct": 10.0,
        "half_average_gain_cap_pct": round(average_gain / 2, 4) if average_gain else None,
        "loss_target_context": None,
        "reward_to_risk": None,
        "minimum_reward_to_risk": 2.0,
        "breakeven_at_r": 3.0,
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
            stop_pct = (entry - stop) / entry * 100
            controls["initial_stop_pct"] = round(stop_pct, 4)
            if stop_pct <= 7:
                controls["loss_target_context"] = "within_6_to_7_pct_target" if stop_pct >= 6 else "tighter_than_6_to_7_pct_target"
            else:
                controls["loss_target_context"] = "wider_than_6_to_7_pct_target"
            if stop_pct > 10:
                failed.append("initial_stop_pct")
            if average_gain is not None and stop_pct > average_gain / 2:
                failed.append("half_average_gain_cap")
            if upside is not None:
                reward_to_risk = (upside - entry) / (entry - stop)
                controls["reward_to_risk"] = round(reward_to_risk, 4)
                if reward_to_risk < 2:
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


def _valid_entry_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _triggered(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return str(value.get("state", value.get("status", ""))).lower() in {"triggered", "breached"}


def _active(payload: Mapping[str, Any]) -> dict[str, Any]:
    entry = _number(payload.get("entry_price"))
    entry_date = payload.get("entry_date")
    stop = _number(payload.get("stop_price"))
    invalidation = _mapping(payload.get("invalidation"))
    invalidation_price = _number(invalidation.get("price"))
    precise_invalidation = invalidation_price is not None or bool(invalidation.get("condition"))
    # For a long position the higher of the two levels is crossed first, so it is the
    # one a price path has to clear before HOLD means anything.
    protective_levels = [level for level in (stop, invalidation_price) if level is not None]
    protective_level = max(protective_levels) if protective_levels else None
    missing: list[str] = []
    if entry is None:
        missing.append("entry_price")
    if not _valid_entry_date(entry_date):
        missing.append("entry_date")
    if stop is None and not precise_invalidation:
        missing.append("stop_or_invalidation")

    live_stop = _mapping(payload.get("live_stop"))
    live_triggered = bool(payload.get("live_stop_check")) and live_stop.get("partial_session") is True and _triggered(live_stop)
    current = _number(payload.get("current_price"))
    completed_price_path = _mapping(payload.get("completed_price_path"))
    path_state = str(completed_price_path.get("state", "")).strip().lower()
    # A path that predates this field audited the hard stop, which is what it was named after.
    checked_level = _number(completed_price_path.get("checked_level"))
    if checked_level is None:
        checked_level = _number(completed_price_path.get("stop_price")) or stop
    completed_stop = _triggered(payload.get("completed_stop")) or _triggered(payload.get("stop_event")) or path_state in {"triggered", "breached"} or (current is not None and stop is not None and current <= stop)
    invalidation_price_breach = current is not None and invalidation_price is not None and current <= invalidation_price
    invalidation_triggered = _triggered(invalidation) or invalidation_price_breach
    if current is None and not (live_triggered or completed_stop or invalidation_triggered):
        missing.append("current_price")
    path_clears_protection = path_state == "clear" and checked_level is not None and protective_level is not None and checked_level >= protective_level
    if protective_level is not None and not (live_triggered or completed_stop or invalidation_triggered) and not path_clears_protection:
        missing.append("completed_price_path")

    controls = {"breakeven_at_r": 3.0, "breakeven_protection_required": False}
    if missing:
        verdict = "INCOMPLETE"
        reasons: list[str] = []
    else:
        if live_triggered or completed_stop or invalidation_triggered:
            verdict = "SELL"
            reasons = ["live_stop_breach" if live_triggered else "completed_stop_breach" if completed_stop else "invalidation_triggered" if _triggered(invalidation) else "invalidation_breach"]
        else:
            verdict = "HOLD"
            reasons = []
            if entry is not None and stop is not None and current is not None and stop < entry:
                initial_risk = entry - stop
                if initial_risk > 0 and (current - entry) / initial_risk >= 3:
                    controls["breakeven_protection_required"] = True
    return {
        "mode": "active",
        "verdict": verdict,
        "risk_controls": controls,
        "completed_price_path": completed_price_path or None,
        "failed": reasons if not missing else [],
        "missing": missing,
        "waiting": [],
    }


def reduce_risk(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return the only final verdict: prospective or active, from evidence objects."""

    payload = _mapping(evidence)
    return _active(payload) if payload.get("mode") == "active" else _prospective(payload)
