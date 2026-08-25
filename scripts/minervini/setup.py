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
_BASE_EVIDENCE = (
    "setup.demand_supply_volume_asymmetry",
    "setup.pivot_volume_contraction",
    "setup.contractions_must_contract",
    # Not the V-shape, which the source describes without a ratio, but its other named form:
    # a right side that produced no pause at all is an absence, and an absence needs no
    # threshold to observe.
    "setup.time_compression_hazard",
    "market.correction_depth_healthy_leader.correction_failure_threshold",
    # Not a measurement: the reading that the declared chain is the base's whole structure.
    # Without it a chain that skipped an unfavourable contraction is indistinguishable from
    # an honest one, and issuing READY over a gap the engine knows about is worse than the
    # gap.
    "setup.failure_reset_types",
    "setup.declared_chain_completeness",
    "setup.chase_limit_above_pivot",
)
_ROUTES = {
    "completed_pivot": (*_BASE_EVIDENCE, "setup.structural_pivot_and_trigger"),
}
# Two routes still need their own trigger measured. A cheat is entered inside the base rather
# than at its pivot, so it needs the pause's location and recovery fraction. An early entry
# is taken on a named tactic -- an upside reversal, an oops, a key-level reclaim -- and
# dropping the pivot from its list without measuring one of those left "taken before the
# pivot" indistinguishable from "taken for no stated reason". Borrowing the pivot route's
# evidence would call either one ready on evidence about a different entry.
_UNMEASURED_ROUTES = {"vcp_cheat": "cheat_geometry", "tl_early": "early_trigger"}


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


def _owning_claim(identifier: str) -> str | None:
    """The registered claim a condition belongs to.

    A condition is named either by its claim or by one threshold inside it, so the claim is
    the longest prefix of the name the registry knows.
    """
    parts = identifier.split(".")
    while parts:
        candidate = ".".join(parts)
        try:
            doctrine.get_claim(candidate)
        except KeyError:
            parts.pop()
        else:
            return candidate
    return None


def _rejects(identifier: str) -> bool:
    """Whether a known failure here rejects rather than counting against readiness."""

    claim_id = _owning_claim(identifier)
    return claim_id is not None and doctrine.get_claim(claim_id)["claim"]["kind"] == "hard_gate"


def _early_entry_debt(entry: Mapping[str, Any], price: float | None) -> tuple[dict[str, Any], list[str]]:
    debt = entry.get("confirmation_debt")
    items = [str(item) for item in debt if str(item).strip()] if isinstance(debt, list) else []
    later_pivot = _precise_level(entry.get("minervini_later_pivot"))
    invalidation = _precise_level(entry.get("invalidation"))
    # A level is only the level it is named after if it sits where that name requires. A
    # later pivot at or below the current price is already behind the stock, and an
    # invalidation at or above it is already breached; both validated before this check.
    if price is not None and later_pivot is not None and float(later_pivot["price"]) <= price:
        later_pivot = None
    if price is not None and invalidation is not None and float(invalidation["price"]) >= price:
        invalidation = None
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
    declared = payload.get("declared_readings") if isinstance(payload.get("declared_readings"), Mapping) else {}
    measurements = payload.get("measurements") if isinstance(payload.get("measurements"), Mapping) else {}
    signals = [item for item in (payload.get("signals") or []) if isinstance(item, Mapping)]
    # Only binding evidence can answer a required condition, and two answers to the same
    # condition is a contradiction rather than a race the last writer wins.
    by_id: dict[str, Any] = {}
    contested: set[str] = set()
    for item in signals:
        identifier = str(item.get("id"))
        # Binding has to be claimed and owned. A signal with no flag at all, or one whose
        # doctrine_id names a different claim from the one its id answers, is not this
        # harness's evidence however confident its state word sounds.
        if item.get("binds") is not True or item.get("doctrine_id") != _owning_claim(identifier):
            continue
        if identifier in by_id:
            contested.add(identifier)
        by_id[identifier] = item

    entry = _mapping(payload.get("entry"))
    kind = _canonical_kind(entry.get("kind")) or "completed_pivot"
    entry["kind"] = kind
    entry_missing: list[str] = []
    if kind == "tl_early":
        price = measurements.get("last_close")
        entry, entry_missing = _early_entry_debt(entry, float(price) if isinstance(price, (int, float)) else None)
    required = _ROUTES.get(kind)
    if required is None:
        required = _BASE_EVIDENCE if kind in _UNMEASURED_ROUTES else ()
        entry_missing = [*entry_missing, _UNMEASURED_ROUTES.get(kind, "entry_trigger")]

    failed: list[str] = []
    missing: list[str] = []
    unsatisfied: list[str] = []
    for claim_id in required:
        item = by_id.get(claim_id)
        if item is None or claim_id in contested:
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
        "segmentation": payload.get("segmentation") if isinstance(payload.get("segmentation"), Mapping) else {},
        "measurements": measurements,
        "declared_readings": dict(declared),
        "signals": signals,
        "required_evidence": list(required),
        "failed": failed,
        "unsatisfied": unsatisfied,
        "missing": missing,
    }


__all__ = ["evaluate_setup"]
