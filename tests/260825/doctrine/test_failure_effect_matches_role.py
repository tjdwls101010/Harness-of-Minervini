"""A claim that holds a filter cannot also say it has no failure effect.

Promoting a practitioner's "the volume should increase at least 25%" from a population
statistic to the filter it always was left the claim's own prose behind, still saying
"this is descriptive or statistical context, not an executable pass/fail rule". The
registry then described the same claim two ways, and `doctrine show` printed both.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from scripts.minervini import doctrine


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


class FailureEffectMatchesRoleTests(unittest.TestCase):
    def test_no_registered_claim_holds_a_gate_while_declaring_no_failure_effect(self) -> None:
        for record in registry()["claims"]:
            thresholds = record.get("thresholds") or {}
            if any(specification["role"] == "gate" for specification in thresholds.values()):
                with self.subTest(claim=record["id"]):
                    self.assertNotEqual(record["failure"]["effect"], "not_applicable")

    def test_validate_rejects_a_gate_on_a_claim_that_says_failure_does_not_apply(self) -> None:
        broken = registry()
        record = next(item for item in broken["claims"] if item["id"] == "eligibility.standard_trend_template")
        record["failure"]["effect"] = "not_applicable"

        result = doctrine.validate(broken)

        self.assertFalse(result["valid"])
        self.assertTrue(any("failure effect" in error for error in result["errors"]), result["errors"])

    def test_a_contrast_gate_failure_reads_as_review_rather_than_rejection(self) -> None:
        """Ryan's standard failing is worth reading; it is not this harness rejecting a stock."""

        record = doctrine.get_claim("practitioners.breakout_volume.ryan_25pct_min_100_200pct_ideal")["claim"]

        self.assertEqual(record["failure"]["effect"], "needs_review")
        self.assertNotIn("not an executable", record["failure"]["meaning"])


if __name__ == "__main__":
    unittest.main()
