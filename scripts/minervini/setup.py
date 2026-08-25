"""Decide a setup state from evidence that had to be positively present.

The old reducer produced `ready` when nothing was marked failed or missing. That is how
twenty-two drifting bars and two caller-supplied `pass` flags reached the top verdict:
there was nothing to object to because there was nothing there. Each route now names the
evidence it must have, and `ready` is that list being satisfied. A setup cannot back into
readiness by having no objections.

Contrast evidence never arrives here. A gate belonging to a practitioner this harness reads
for comparison reports `contrast_pass` or `contrast_fail`, words no state set below
contains, so handing one in would not be ignored -- it would read as missing evidence and
turn somebody else's disagreement into this harness's incompleteness.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from . import doctrine


_PASS = {"pass", "ready", "confirmed", "eligible", "supports", "observed", "complete"}
_FAIL = {"fail", "failed", "avoid", "contradicts", "broken", "invalid"}
_WAIT = {"wait", "pending", "watch", "not_triggered"}
_MISSING = {"unavailable", "needs_input", "needs_chart", "incomplete", "unknown"}
# Reported evidence carries no verdict by design: a band says where a measurement sat, a
# marker says how far it is from a value the source declined to bound.
_REPORTED = {"reported", "within_source_range", "beyond_source_range", "short_of_source_range"}

# What each route must positively have before it can be called ready. Every entry names a
# claim, so the reason a setup is not ready is always a sentence from the source.
_STANDARD_EVIDENCE = (
    "setup.demand_supply_volume_asymmetry",
    "setup.pivot_volume_contraction",
    "setup.contractions_must_contract",
    "setup.structural_pivot_and_trigger",
)
_ROUTES = {
    "completed_pivot": _STANDARD_EVIDENCE,
    "vcp_cheat": _STANDARD_EVIDENCE,
    # An early entry is taken before the pivot, so the trigger is the confirmation it owes
    # rather than evidence it already has. The supply gates still apply: they are about the
    # base, not about when the trade is taken.
    "tl_early": _STANDARD_EVIDENCE[:-1],
}


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


def _precise_level(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    item = _mapping(value)
    price = item.get("price")
    condition = item.get("condition")
    if isinstance(price, (int, float)) and price > 0 and isinstance(condition, str) and condition.strip():
        return item
    return None


def _canonical_kind(value: Any) -> str:
    kind = str(value or "").strip().lower().replace("-", "_")
    return {
        "pivot_breakout": "completed_pivot",
        "breakout": "completed_pivot",
        "cheat": "vcp_cheat",
        "3c_cheat": "vcp_cheat",
        "early": "tl_early",
    }.get(kind, kind)


def _rejects(claim_id: str) -> bool:
    """Whether a known failure of this claim rejects rather than counting against readiness."""

    return doctrine.get_claim(claim_id)["claim"]["kind"] == "hard_gate"


def _early_entry_debt(entry: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    debt = entry.get("confirmation_debt")
    items = [str(item) for item in debt if str(item).strip()] if isinstance(debt, list) else []
    later_pivot = _precise_level(entry.get("minervini_later_pivot"))
    invalidation = _precise_level(entry.get("invalidation"))
    resolved = {
        **entry,
        "kind": "tl_early",
        "tactic": "[TL-EARLY]",
        "confirmation_debt": items,
        "minervini_later_pivot": later_pivot,
        "invalidation": invalidation,
    }
    missing = []
    if entry.get("opt_in") is not True:
        missing.append("tl_early_opt_in")
    if not items:
        missing.append("confirmation_debt")
    if later_pivot is None:
        missing.append("minervini_later_pivot")
    if invalidation is None:
        missing.append("precise_invalidation")
    return resolved, missing


def evaluate_setup(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify measured setup evidence without making the final investment verdict."""

    payload = _mapping(evidence)
    structure = payload.get("structure") if isinstance(payload.get("structure"), Mapping) else {}
    measurements = payload.get("measurements") if isinstance(payload.get("measurements"), Mapping) else {}
    signals = [item for item in (payload.get("signals") or []) if isinstance(item, Mapping)]
    by_id = {str(item.get("id")): item for item in signals}

    entry = _mapping(payload.get("entry"))
    kind = _canonical_kind(entry.get("kind")) or "completed_pivot"
    entry["kind"] = kind
    entry_missing: list[str] = []
    if kind == "tl_early":
        entry, entry_missing = _early_entry_debt(entry)
    required = _ROUTES.get(kind)
    if required is None:
        required = ()
        entry_missing = [*entry_missing, "entry_trigger"]

    failed: list[str] = []
    missing: list[str] = []
    unsatisfied: list[str] = []
    for claim_id in required:
        item = by_id.get(claim_id)
        if item is None:
            missing.append(claim_id)
            continue
        state = str(item.get("state", ""))
        if state in _PASS:
            continue
        if state in _FAIL:
            (failed if _rejects(claim_id) else unsatisfied).append(claim_id)
        elif state in _MISSING:
            missing.append(claim_id)
        else:
            unsatisfied.append(claim_id)

    if str(structure.get("state")) != "resolved":
        missing.append("base_structure")
    missing.extend(entry_missing)

    if failed:
        setup_state = "avoid"
    elif missing:
        setup_state = "incomplete"
    elif unsatisfied:
        setup_state = "wait"
    else:
        setup_state = "ready"

    return {
        "setup_state": setup_state,
        "entry": entry,
        "structure": structure,
        "measurements": measurements,
        "signals": signals,
        "required_evidence": list(required),
        "failed": failed,
        "unsatisfied": unsatisfied,
        "missing": missing,
    }


__all__ = ["evaluate_setup"]
