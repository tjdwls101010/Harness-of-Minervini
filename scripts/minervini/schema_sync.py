"""Generate static response schemas from the public capability registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .capabilities import CAPABILITIES, Capability


SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def capability_schema(capability: Capability) -> dict[str, Any]:
    description = capability.description()
    contract = {key: value for key, value in description.items() if key not in {"name", "schema_id"}}
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": capability.schema_id,
        "title": f"Harness of Minervini v2 {capability.name} response",
        "allOf": [
            {"$ref": "envelope.schema.json"},
            {"properties": {"operation": {"const": capability.name}}, "required": ["operation"]},
        ],
        "x-capability-contract": contract,
    }


def synchronize(directory: Path | None = None) -> list[Path]:
    destination = directory or Path(__file__).resolve().parents[2] / "schemas" / "v2"
    written: list[Path] = []
    for name, capability in sorted(CAPABILITIES.items()):
        path = destination / f"{name}.schema.json"
        path.write_text(json.dumps(capability_schema(capability), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    synchronize()


__all__ = ["capability_schema", "synchronize"]
