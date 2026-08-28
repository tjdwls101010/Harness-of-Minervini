"""`data` is the one envelope field no schema constrains, and it carries the answer.

Every published schema in `schemas/v2/` says `"data": {}`. That is the whole contract for
the field the analyst reads: an envelope carrying `{"bogus": true}` and nothing else is a
valid `ticker.qualify` response, and a key renamed by a refactor is a valid one too. The
eleven fields around it are pinned by name -- `additionalProperties: false` on the shared
envelope -- and the twelfth, the only one whose shape differs per capability, is open.

What can honestly be pinned here is the vocabulary: the set of top-level keys a capability
can ever put under `data`. Not a fixed required list -- `ticker.qualify` emits
`{ticker, eligibility_state}` when the provider fails and a dozen keys when it measures --
and not the nested structure, which is a different slice. A vocabulary refuses the key
nobody declared, which is the half of the defect that has a mechanical answer.

Two shapes travel under one operation, so the schema names both. Any capability can emit
`error_envelope(...)` -- `data={"error": ...}` and nothing else, under `needs_input` from
the CLI's own request check -- and that is not this capability's domain answer wearing a
different status. They are disjoint by construction, so `oneOf` says exactly that: an
envelope is either the error shape or the declared vocabulary, and never a mixture.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from scripts.minervini.contracts import RequestError, error_envelope
from scripts.minervini.operations import execute


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "schemas" / "v2"


def _registry() -> Registry:
    """Every published schema, addressable by its own `$id` so `$ref` resolves offline."""

    return Registry().with_resources(
        (json.loads(path.read_text(encoding="utf-8"))["$id"], Resource.from_contents(json.loads(path.read_text(encoding="utf-8"))))
        for path in sorted(SCHEMAS.glob("*.schema.json"))
    )


def validator(capability: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{capability}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_registry())


class TheClockDeclaresWhatItsDataHolds(unittest.TestCase):
    """One capability with a two-key answer, carrying the mechanism the rest will use."""

    def envelope(self) -> dict:
        return execute("clock", {"as_of": "2025-12-31"})

    def test_the_envelope_the_capability_emits_validates(self) -> None:
        validator("clock").validate(self.envelope())

    def test_a_key_nobody_declared_is_refused(self) -> None:
        payload = self.envelope()
        payload["data"]["bogus"] = True

        with self.assertRaises(Exception) as raised:
            validator("clock").validate(payload)
        self.assertIn("bogus", str(raised.exception))

    def test_an_answer_missing_the_key_it_is_about_is_refused(self) -> None:
        """`date` is what this capability is for; an envelope without it answered nothing."""

        payload = self.envelope()
        del payload["data"]["date"]

        with self.assertRaises(Exception):
            validator("clock").validate(payload)

    def test_the_error_shape_the_cli_emits_still_validates(self) -> None:
        """A refused request is published under the capability's own operation name."""

        payload = error_envelope("clock", RequestError("as_of must be a completed session", "as_of"))

        validator("clock").validate(payload)

    def test_an_error_envelope_carrying_a_domain_key_is_refused(self) -> None:
        """The two shapes are alternatives, not a menu to mix from."""

        payload = error_envelope("clock", RequestError("bad", "as_of"))
        payload["data"]["date"] = "2025-12-31"

        with self.assertRaises(Exception):
            validator("clock").validate(payload)


if __name__ == "__main__":
    unittest.main()
