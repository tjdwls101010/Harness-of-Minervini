"""Pure setup-evidence reducer for the public ``ticker.setup`` capability."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


_PASS = {"pass", "ready", "confirmed", "eligible", "supports", "observed", "complete"}
_FAIL = {"fail", "failed", "avoid", "contradicts", "broken", "invalid"}
_WAIT = {"wait", "pending", "watch", "not_triggered"}
_MISSING = {"unavailable", "needs_input", "needs_chart", "incomplete", "unknown"}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _state(value: Any, default: str = "unavailable") -> str:
    if isinstance(value, bool):
        return "pass" if value else "fail"
    if isinstance(value, Mapping):
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


def _evidence(value: Any) -> dict[str, Any]:
    item = _mapping(value)
    item["state"] = _state(value)
    return item


def _precise_level(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    item = _mapping(value)
    price = item.get("price")
    condition = item.get("condition")
    if isinstance(price, (int, float)) and price > 0 and isinstance(condition, str) and condition.strip():
        return item
    return None


def _entry_result(entry: Mapping[str, Any] | None) -> tuple[str, dict[str, Any], list[str]]:
    source = _mapping(entry)
    kind = str(source.get("kind", "")).strip().lower().replace("-", "_")
    state = _state(source)
    result = {**source, "kind": kind or None, "state": state, "confirmation_debt": []}

    if kind in {"completed_pivot", "pivot_breakout", "breakout"}:
        result["kind"] = "completed_pivot"
        return ("ready" if state == "pass" else "wait"), result, []
    if kind in {"vcp_cheat", "cheat", "3c_cheat"}:
        result["kind"] = "vcp_cheat"
        return ("ready" if state == "pass" else "wait"), result, []
    if kind in {"tl_early", "early"}:
        debt = source.get("confirmation_debt")
        debt_items = [str(item) for item in debt if str(item).strip()] if isinstance(debt, list) else []
        later_pivot = _precise_level(source.get("minervini_later_pivot"))
        invalidation = _precise_level(source.get("invalidation"))
        result.update(
            {
                "kind": "tl_early",
                "tactic": "[TL-EARLY]",
                "confirmation_debt": debt_items,
                "minervini_later_pivot": later_pivot,
                "invalidation": invalidation,
            }
        )
        missing = []
        if source.get("opt_in") is not True:
            missing.append("tl_early_opt_in")
        if not debt_items:
            missing.append("confirmation_debt")
        if later_pivot is None:
            missing.append("minervini_later_pivot")
        if invalidation is None:
            missing.append("precise_invalidation")
        return ("ready" if state == "pass" and not missing else "wait"), result, missing
    return "wait", result, ["entry_trigger"]


def evaluate_setup(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify setup evidence without making the final investment verdict.

    ``price_geometry`` and ``supply_evidence`` are independent inputs. A VCP
    label is descriptive only: it never supplies the missing volume/contraction
    evidence needed to call a setup ready.
    """

    payload = _mapping(evidence)
    geometry = _evidence(payload.get("price_geometry"))
    supply = _evidence(payload.get("supply_evidence"))
    entry_state, entry, entry_missing = _entry_result(payload.get("entry"))
    failed: list[str] = []
    missing: list[str] = []

    for name, item in (("price_geometry", geometry), ("supply_evidence", supply)):
        if item["state"] == "fail":
            failed.append(name)
        elif item["state"] == "unavailable":
            missing.append(name)

    if failed:
        setup_state = "avoid"
    elif missing:
        setup_state = "incomplete"
    elif geometry["state"] == "wait" or supply["state"] == "wait" or entry_state == "wait":
        setup_state = "wait"
    else:
        setup_state = "ready"

    return {
        "setup_state": setup_state,
        "price_geometry": geometry,
        "supply_evidence": supply,
        "entry": entry,
        "failed": failed,
        "missing": missing + entry_missing,
        "vcp_label": payload.get("vcp_label"),
    }
