from tests.paths import ROOT

import json
import unittest

from scripts.minervini.capabilities import CAPABILITIES
from scripts.minervini.schema_sync import capability_schema


SCHEMAS = ROOT / "schemas" / "v2"
SCHEMA_VERSION = "2.0.0"
SCHEMA_BASE_ID = "https://harness.minervini.dev/schemas/v2/"
ENVELOPE_KEYS = {
    "schema_version",
    "operation",
    "request",
    "as_of",
    "status",
    "data",
    "signals",
    "missing",
    "sources",
    "doctrine_ids",
    "next_capabilities",
    "side_effects",
}
VALID_STATUSES = {"ok", "partial", "unavailable", "needs_input"}


def schema_filename(capability: str) -> str:
    return f"{capability}.schema.json"


def schema_id(capability: str) -> str:
    return f"{SCHEMA_BASE_ID}{schema_filename(capability)}"


class VersionedSchemaContractTests(unittest.TestCase):
    def test_catalog_exactly_covers_public_capabilities(self) -> None:
        with (SCHEMAS / "catalog.json").open(encoding="utf-8") as handle:
            catalog = json.load(handle)

        self.assertEqual(catalog["schema_version"], SCHEMA_VERSION)
        self.assertEqual(set(catalog["capabilities"]), set(CAPABILITIES))
        self.assertEqual(
            {path.name for path in SCHEMAS.glob("*.schema.json")},
            {"envelope.schema.json", *(schema_filename(capability) for capability in CAPABILITIES)},
        )
        for capability, metadata in catalog["capabilities"].items():
            self.assertEqual(metadata, {
                "schema_id": schema_id(capability),
                "schema_file": schema_filename(capability),
            })

    def test_each_cataloged_capability_has_a_versioned_operation_schema(self) -> None:
        with (SCHEMAS / "catalog.json").open(encoding="utf-8") as handle:
            catalog = json.load(handle)

        for capability, metadata in catalog["capabilities"].items():
            with self.subTest(capability=capability):
                with (SCHEMAS / metadata["schema_file"]).open(encoding="utf-8") as handle:
                    schema = json.load(handle)
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(schema["$id"], metadata["schema_id"])
                self.assertIn({"$ref": "envelope.schema.json"}, schema["allOf"])
                operation_schema = next(item for item in schema["allOf"] if "properties" in item)
                self.assertEqual(operation_schema["properties"]["operation"], {"const": capability})
                description = CAPABILITIES[capability].description()
                expected_contract = {key: value for key, value in description.items() if key not in {"name", "schema_id"}}
                self.assertEqual(schema["x-capability-contract"], expected_contract)
                self.assertEqual(schema, capability_schema(CAPABILITIES[capability]))

    def test_shared_envelope_has_exact_keys_and_status_vocabulary(self) -> None:
        with (SCHEMAS / "envelope.schema.json").open(encoding="utf-8") as handle:
            envelope = json.load(handle)

        self.assertEqual(envelope["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(envelope["$id"], f"{SCHEMA_BASE_ID}envelope.schema.json")
        self.assertFalse(envelope["additionalProperties"])
        self.assertEqual(set(envelope["properties"]), ENVELOPE_KEYS)
        self.assertEqual(set(envelope["required"]), ENVELOPE_KEYS)
        self.assertEqual(set(envelope["properties"]["status"]["enum"]), VALID_STATUSES)

    def test_capability_metadata_exposes_the_catalog_schema_identifier(self) -> None:
        for capability, metadata in self._catalog_capabilities().items():
            with self.subTest(capability=capability):
                self.assertEqual(getattr(CAPABILITIES[capability], "schema_id", None), metadata["schema_id"])
                self.assertEqual(CAPABILITIES[capability].listing().get("schema_id"), metadata["schema_id"])
                self.assertEqual(CAPABILITIES[capability].description().get("schema_id"), metadata["schema_id"])

    @staticmethod
    def _catalog_capabilities() -> dict[str, dict[str, str]]:
        with (SCHEMAS / "catalog.json").open(encoding="utf-8") as handle:
            return json.load(handle)["capabilities"]


if __name__ == "__main__":
    unittest.main()
