"""Every executable claim carries the source text it came from, and owns its numbers."""

from __future__ import annotations

import json
import pathlib
import unittest

from scripts.minervini import doctrine


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


class QuotationTests(unittest.TestCase):
    def test_every_executable_claim_quotes_its_source(self) -> None:
        unsourced = []
        for record in registry()["claims"]:
            # A harness-layer rule has no book behind it and says so; everything else must cite one.
            if record["quarantine"]["is_quarantined"] or record["layer"] == "harness":
                continue
            quotations = record["provenance"].get("quotations")
            if not isinstance(quotations, list) or not quotations:
                unsourced.append(record["id"])
        self.assertEqual(unsourced, [])

    def test_every_quotation_names_a_corpus_a_row_and_real_text(self) -> None:
        defective = []
        for record in registry()["claims"]:
            for index, quotation in enumerate(record["provenance"].get("quotations", [])):
                corpus = quotation.get("corpus")
                row = quotation.get("row")
                text = quotation.get("text")
                if corpus not in {"Minervini", "TraderLion"} or not isinstance(row, int) or not isinstance(text, str) or len(text.strip()) < 20:
                    defective.append(f"{record['id']}[{index}]")
        self.assertEqual(defective, [])

    def test_no_claim_keeps_a_generic_placeholder_corpus(self) -> None:
        placeholders = [
            record["id"]
            for record in registry()["claims"]
            if record["provenance"].get("corpus") in {"canonical_method", "practice_layer", "harness_constitution"}
        ]
        self.assertEqual(placeholders, [])


class ThresholdOwnershipTests(unittest.TestCase):
    def test_a_registered_threshold_is_readable_by_its_claim_and_name(self) -> None:
        self.assertEqual(doctrine.threshold("eligibility.standard_trend_template", "relative_strength_minimum"), 70)

    def test_an_unknown_threshold_name_is_an_error_not_a_default(self) -> None:
        with self.assertRaises(KeyError):
            doctrine.threshold("eligibility.standard_trend_template", "not_a_registered_threshold")

    def test_an_unknown_claim_is_an_error(self) -> None:
        with self.assertRaises(KeyError):
            doctrine.threshold("not.a.claim", "anything")

    def test_every_threshold_points_at_a_quotation_that_exists(self) -> None:
        dangling = []
        for record in registry()["claims"]:
            quotations = record["provenance"].get("quotations", [])
            for name, specification in record.get("thresholds", {}).items():
                index = specification.get("quote_index")
                if not isinstance(index, int) or not 0 <= index < len(quotations):
                    dangling.append(f"{record['id']}.{name}")
        self.assertEqual(dangling, [])

    def test_validate_rejects_a_threshold_whose_quotation_is_missing(self) -> None:
        broken = registry()
        broken["claims"][0]["thresholds"] = {"invented": {"role": "gate", "value": 42, "unit": "percent", "comparator": "<=", "quote_index": 99, "exact": True}}

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("quote_index" in error for error in result["errors"]), result["errors"])

    def test_validate_rejects_an_executable_claim_without_a_quotation(self) -> None:
        broken = registry()
        sourced = next(item for item in broken["claims"] if item["layer"] != "harness" and not item["quarantine"]["is_quarantined"])
        sourced["provenance"]["quotations"] = []

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("quotation" in error for error in result["errors"]), result["errors"])


class LayerTests(unittest.TestCase):
    def test_every_claim_declares_which_layer_it_belongs_to(self) -> None:
        undeclared = [record["id"] for record in registry()["claims"] if record.get("layer") not in {"canonical", "practice", "harness"}]
        self.assertEqual(undeclared, [])

    def test_practice_layer_claims_are_never_hard_gates(self) -> None:
        promoted = [
            record["id"]
            for record in registry()["claims"]
            if record.get("layer") == "practice" and record["kind"] == "hard_gate"
        ]
        self.assertEqual(promoted, [])


class ScopeTests(unittest.TestCase):
    def test_a_position_sizing_claim_is_recorded_but_never_wired_to_a_capability(self) -> None:
        wired = [
            record["id"]
            for record in registry()["claims"]
            if record.get("out_of_scope") == "position_sizing" and record["consumers"] != ["doctrine audit"]
        ]
        self.assertEqual(wired, [])

    def test_validate_refuses_to_wire_an_out_of_scope_claim(self) -> None:
        broken = registry()
        record = next(item for item in broken["claims"] if not item["quarantine"]["is_quarantined"])
        record["out_of_scope"] = "position_sizing"
        record["consumers"] = ["ticker.risk"]

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("out of scope" in error for error in result["errors"]), result["errors"])


class AttributionTests(unittest.TestCase):
    def test_practitioners_who_disagree_are_recorded_separately(self) -> None:
        volume_claims = [
            record
            for record in registry()["claims"]
            if "breakout_volume" in record["id"] and record.get("attributed_to")
        ]

        # Four practitioners give four different breakout-volume standards; a registry
        # that reconciled them into one number would have destroyed the disagreement.
        self.assertGreaterEqual(len({record["attributed_to"] for record in volume_claims}), 3)

    def test_no_attributed_claim_is_a_hard_gate(self) -> None:
        promoted = [
            record["id"]
            for record in registry()["claims"]
            if record.get("attributed_to") and record["kind"] == "hard_gate"
        ]
        self.assertEqual(promoted, [])


if __name__ == "__main__":
    unittest.main()
