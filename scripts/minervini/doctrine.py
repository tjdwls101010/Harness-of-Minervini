"""Read the normalized doctrine registry without exposing source prose as runtime rules."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "doctrine" / "claims.json"
_CLAIM_FIELDS = (
    "id",
    "title",
    "kind",
    "status",
    "context",
    "required_inputs",
    "rule",
    "failure",
    "missing",
    "precedence",
    "quarantine",
    "consumers",
)
_REQUIRED_FIELDS = frozenset((*_CLAIM_FIELDS, "provenance", "tests"))
_VALID_KINDS = frozenset({"constitution", "hard_gate", "default", "tactic", "interpretation", "exception", "quarantine"})


def _load_registry() -> dict[str, Any]:
    with _REGISTRY_PATH.open(encoding="utf-8") as registry_file:
        return json.load(registry_file)


def _runtime_claim(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record[field] for field in _CLAIM_FIELDS}


def _result(record: dict[str, Any]) -> dict[str, Any]:
    return {"claim": _runtime_claim(record), "provenance": record["provenance"]}


def get_claim(claim_id: str) -> dict[str, Any]:
    """Return one claim and its audit provenance as separate objects.

    Raises:
        KeyError: If ``claim_id`` is not registered.
    """
    for record in _load_registry()["claims"]:
        if record["id"] == claim_id:
            return _result(record)
    raise KeyError(f"unknown doctrine claim: {claim_id}")


def list(
    *,
    context: str | None = None,
    include_quarantined: bool = False,
) -> list[dict[str, Any]]:
    """List runtime claims, optionally narrowed to one analysis context.

    Quarantined records are audit material and are excluded unless explicitly
    requested.  Every returned item keeps the executable claim separate from
    its provenance metadata.
    """
    records: Iterable[dict[str, Any]] = _load_registry()["claims"]
    if context is not None:
        records = (record for record in records if context in record["context"])
    if not include_quarantined:
        records = (record for record in records if not record["quarantine"]["is_quarantined"])
    return [_result(record) for record in records]


def validate() -> dict[str, Any]:
    """Validate the registry's public contract and executable-claim coverage."""
    registry = _load_registry()
    errors: list[str] = []
    claim_ids: set[str] = set()
    precedence_order = set(registry.get("precedence_order", []))

    if not isinstance(registry.get("schema_version"), str):
        errors.append("registry.schema_version must be a string")
    if not precedence_order:
        errors.append("registry.precedence_order must not be empty")

    for index, record in enumerate(registry.get("claims", [])):
        label = f"claims[{index}]"
        missing_fields = _REQUIRED_FIELDS.difference(record)
        if missing_fields:
            errors.append(f"{label} missing fields: {', '.join(sorted(missing_fields))}")
            continue
        claim_id = record["id"]
        if not isinstance(claim_id, str) or not claim_id:
            errors.append(f"{label}.id must be a non-empty string")
        elif claim_id in claim_ids:
            errors.append(f"duplicate claim id: {claim_id}")
        else:
            claim_ids.add(claim_id)
        if record["kind"] not in _VALID_KINDS:
            errors.append(f"{label}.kind is invalid")
        if record["precedence"].get("tier") not in precedence_order:
            errors.append(f"{label}.precedence.tier is not registered")
        if record["kind"] == "quarantine" and not record["quarantine"].get("is_quarantined"):
            errors.append(f"{label} quarantine kind must be quarantined")
        if record["quarantine"].get("is_quarantined") and record["status"] != "quarantine":
            errors.append(f"{label} quarantined record must have quarantine status")
        if not record["quarantine"].get("is_quarantined") and not record["consumers"]:
            errors.append(f"{label} executable record requires a consumer")
        if not record["quarantine"].get("is_quarantined") and not record["tests"]:
            errors.append(f"{label} executable record requires a test reference")

    return {"valid": not errors, "errors": errors, "claim_count": len(registry.get("claims", []))}


__all__ = ["get_claim", "list", "validate"]
