"""Generate static response schemas from the public capability registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .capabilities import CAPABILITIES, Capability


SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


# The shape any capability can be answered by: `error_envelope` publishes the refusal under
# the capability's own operation name, so every schema has to admit it, and it carries the
# one key no capability's domain answer uses.
ERROR_DATA_SCHEMA = {
    "type": "object",
    "properties": {"error": {"type": "object"}},
    "required": ["error"],
    "additionalProperties": False,
}


def data_schema(capability: Capability) -> dict[str, Any]:
    """The declared vocabulary, or nothing when a capability has not declared one yet."""

    if not capability.data_keys:
        return {}
    domain: dict[str, Any] = {
        "type": "object",
        "properties": {key: {} for key in sorted(capability.data_keys)},
        "additionalProperties": False,
    }
    if capability.data_core:
        domain["required"] = sorted(capability.data_core)
    # `oneOf` rather than `anyOf`: the two shapes are disjoint by construction, so an envelope
    # matching both is a domain answer that grew an `error` key, which is neither.
    return {"oneOf": [ERROR_DATA_SCHEMA, domain]}


def capability_schema(capability: Capability) -> dict[str, Any]:
    description = capability.description()
    contract = {key: value for key, value in description.items() if key not in {"name", "schema_id"}}
    properties: dict[str, Any] = {"operation": {"const": capability.name}}
    data = data_schema(capability)
    if data:
        properties["data"] = data
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": capability.schema_id,
        "title": f"Harness of Minervini v2 {capability.name} response",
        "allOf": [
            {"$ref": "envelope.schema.json"},
            {"properties": properties, "required": ["operation"]},
        ],
        "x-capability-contract": contract,
    }


def synchronize(directory: Path | None = None) -> list[Path]:
    destination = directory or Path(__file__).resolve().parents[2] / "schemas" / "v2"
    written: list[Path] = []
    catalog: dict[str, dict[str, str]] = {}
    for name, capability in sorted(CAPABILITIES.items()):
        filename = f"{name}.schema.json"
        path = destination / filename
        path.write_text(json.dumps(capability_schema(capability), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
        catalog[name] = {"schema_file": filename, "schema_id": capability.schema_id}
    # The index goes out with the files it indexes. Written by hand it went stale the first time
    # a capability was added, and running the generator then looked like bringing the directory
    # up to date -- which is worse than a generator that writes none of it.
    index = destination / "catalog.json"
    index.write_text(json.dumps({"capabilities": catalog, "schema_version": SCHEMA_VERSION}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    written.append(index)
    return written


if __name__ == "__main__":
    synchronize()


__all__ = ["capability_schema", "data_schema", "synchronize"]
