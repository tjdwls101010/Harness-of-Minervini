"""Whose standard decides, kept separate from what kind of statement the number is.

Phase 1 forbade a gate on any claim not attributed to Minervini, which stopped another
practitioner's standard from rejecting a candidate but did it by recording Ryan's "the
volume should increase at least 25%" as a population statistic. It is not one. The
registry now records the filter as a filter and marks it non-binding, and these are the
guarantees that replace the old prohibition.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from scripts.minervini import doctrine


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


class BindingAuthorityTests(unittest.TestCase):
    def test_every_threshold_the_reducer_manifest_declares_sits_on_a_binding_claim(self) -> None:
        """The manifest is what the reducers say they read; `threshold()` closes the rest.

        This walks the declaration, not the call sites, so it cannot catch a reducer that
        reaches past the manifest. That path is closed at the seam instead: `threshold()`
        refuses a non-binding value and `evaluate_gate` stamps one as contrast.
        """

        claims = {record["id"]: record for record in registry()["claims"]}
        for claim_id, name, _role in doctrine.REQUIRED_THRESHOLDS:
            record = claims[claim_id]
            with self.subTest(threshold=f"{claim_id}.{name}"):
                self.assertEqual(record["layer"], "canonical")
                self.assertIn(record.get("attributed_to"), (None, "Minervini"))

    def test_a_reducer_cannot_be_pointed_at_a_non_binding_threshold(self) -> None:
        broken = registry()
        record = next(item for item in broken["claims"] if item["id"] == "risk.initial_stop_and_reward")
        record["attributed_to"] = "Zanger"

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("binding" in error for error in result["errors"]), result["errors"])

    def test_a_binding_gate_still_says_pass_and_fail(self) -> None:
        signal = doctrine.evaluate_gate("risk.initial_stop_and_reward", "initial_stop_ceiling_pct", 12.0)

        self.assertTrue(signal["binds"])
        self.assertEqual(signal["state"], "fail")

    def test_a_practice_layer_filter_is_a_gate_that_does_not_bind(self) -> None:
        """TraderLion's "two closes below" is a real rule with a real source behind it."""

        signal = doctrine.evaluate_gate("management.ema21_sma50_roles", "management_closes_below_average", 2)

        self.assertFalse(signal["binds"])
        self.assertEqual(signal["state"], "contrast_pass")


class OneRangeIsOneThresholdTests(unittest.TestCase):
    def test_a_range_the_source_gave_once_is_registered_once(self) -> None:
        """Splitting "3 to as many as 60 weeks" in two loses that it was ever a range.

        Asserting only that the merged band exists would pass with both halves still
        registered beside it, which is the state this replaced.
        """

        for claim_id, merged, replaced in [
            ("setup.consolidation_footprint_3_to_60_weeks", "consolidation_footprint_duration_weeks", ("consolidation_footprint_duration_low", "consolidation_footprint_duration_high")),
            ("basecount.typical_base_duration_5_to_26_weeks", "typical_base_duration_weeks", ("typical_base_duration_low", "typical_base_duration_high")),
            ("basecount.typical_top_after_3_to_5_bases", "typical_base_count_before_top", ("typical_base_count_before_top_low", "typical_base_count_before_top_high")),
        ]:
            with self.subTest(threshold=merged):
                thresholds = doctrine.get_claim(claim_id)["claim"]["thresholds"]
                self.assertEqual(thresholds[merged]["role"], "band")
                self.assertEqual(len(thresholds[merged]["range"]), 2)
                for name in replaced:
                    self.assertNotIn(name, thresholds)


if __name__ == "__main__":
    unittest.main()
