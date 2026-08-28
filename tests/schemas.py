"""Validate an envelope against the schema this harness publishes for its capability.

The schemas in `schemas/v2/` are the contract external consumers read, and until a validator
ran against them nothing proved they say what they mean -- a constraint written at the wrong
depth is inert, and a test that only compares the schema against the declaration it was baked
from agrees with itself. `jsonschema` is a test-only dependency for exactly that reason.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SCHEMAS = pathlib.Path(__file__).resolve().parents[1] / "schemas" / "v2"


def _published() -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(SCHEMAS.glob("*.schema.json"))]


def _registry() -> Registry:
    """Every published schema, addressable by its own `$id` so `$ref` resolves offline."""

    return Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in _published())


def validator(capability: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{capability}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_registry())
