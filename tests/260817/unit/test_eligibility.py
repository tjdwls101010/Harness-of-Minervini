from __future__ import annotations

from tests.paths import FIXTURES as SHARED_FIXTURES

import json
import unittest

from scripts.minervini.eligibility import EligibilityEvidence, evaluate_eligibility


FIXTURES = SHARED_FIXTURES / "eligibility"


def evaluate_fixture(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURES / f"{name}.json").read_text())
    return evaluate_eligibility(EligibilityEvidence.from_mapping(payload)).to_dict()


class EligibilityTruthTableTests(unittest.TestCase):
    def test_standard_route_requires_stage_2_and_all_eight_trend_template_gates(self) -> None:
        result = evaluate_fixture("standard_eligible")

        self.assertEqual(result["route"], "standard")
        self.assertEqual(result["eligibility_state"], "eligible")
        self.assertEqual(
            {signal["state"] for signal in result["signals"]},
            {"pass"},
        )
        self.assertEqual(
            result["doctrine_ids"],
            ["eligibility.standard_stage2", "eligibility.standard_trend_template"],
        )

    def test_known_standard_failure_avoids_even_when_unrelated_evidence_is_missing(self) -> None:
        result = evaluate_fixture("standard_failure_with_missing")

        self.assertEqual(result["route"], "standard")
        self.assertEqual(result["eligibility_state"], "avoid")
        self.assertIn(
            {"id": "trend_template.relative_strength_minimum", "state": "fail", "doctrine_id": "eligibility.standard_trend_template"},
            result["signals"],
        )
        self.assertIn(
            {"id": "trend_template.price_near_52_week_high", "state": "unavailable", "doctrine_id": "eligibility.standard_trend_template"},
            result["signals"],
        )

    def test_missing_critical_evidence_is_incomplete_without_known_failure(self) -> None:
        result = evaluate_fixture("standard_missing_critical")

        self.assertEqual(result["route"], "standard")
        self.assertEqual(result["eligibility_state"], "incomplete")
        self.assertIn("eligibility.standard_trend_template", result["doctrine_ids"])

    def test_recent_ipo_primary_base_is_limited_to_insufficient_history(self) -> None:
        result = evaluate_fixture("recent_ipo_primary_base_eligible")

        self.assertEqual(result["route"], "recent_ipo_primary_base")
        self.assertEqual(result["eligibility_state"], "eligible")
        self.assertEqual(
            result["doctrine_ids"],
            ["eligibility.standard_stage2", "eligibility.standard_trend_template", "eligibility.recent_ipo_primary_base"],
        )

    def test_primary_base_is_not_considered_when_standard_history_is_sufficient(self) -> None:
        payload = json.loads((FIXTURES / "standard_missing_critical.json").read_text())
        primary_base = json.loads((FIXTURES / "recent_ipo_primary_base_eligible.json").read_text())["primary_base"]
        payload["primary_base"] = primary_base

        result = evaluate_eligibility(EligibilityEvidence.from_mapping(payload)).to_dict()

        self.assertEqual(result["route"], "standard")
        self.assertEqual(result["eligibility_state"], "incomplete")
        self.assertNotIn("eligibility.recent_ipo_primary_base", result["doctrine_ids"])

    def test_recent_ipo_cannot_bypass_a_known_standard_failure(self) -> None:
        result = evaluate_fixture("recent_ipo_known_standard_failure")

        self.assertEqual(result["route"], "standard")
        self.assertEqual(result["eligibility_state"], "avoid")
        self.assertIn(
            {"id": "stage_2", "state": "fail", "doctrine_id": "eligibility.standard_stage2"},
            result["signals"],
        )

    def test_recent_ipo_chart_ambiguity_remains_incomplete_after_quantitative_pass(self) -> None:
        result = evaluate_fixture("recent_ipo_primary_base_needs_chart")

        self.assertEqual(result["route"], "recent_ipo_primary_base")
        self.assertEqual(result["eligibility_state"], "incomplete")
        self.assertIn(
            {"id": "primary_base.quality", "state": "needs_chart", "doctrine_id": "eligibility.recent_ipo_primary_base"},
            result["signals"],
        )

    def test_power_play_cannot_be_passed_as_an_eligibility_route(self) -> None:
        evidence = EligibilityEvidence.from_mapping(json.loads((FIXTURES / "standard_eligible.json").read_text()))

        with self.assertRaises(TypeError):
            evaluate_eligibility(evidence, power_play=True)  # type: ignore[call-arg]

    def test_standard_route_accepts_only_the_source_map_eight_criteria(self) -> None:
        payload = json.loads((FIXTURES / "standard_eligible.json").read_text())
        payload["trend_template"][0]["id"] = "trend_template.unapproved_substitute"

        with self.assertRaisesRegex(ValueError, "canonical eight"):
            EligibilityEvidence.from_mapping(payload)

    def test_route_evidence_cannot_supply_noncanonical_doctrine_ids(self) -> None:
        payload = json.loads((FIXTURES / "standard_eligible.json").read_text())
        payload["stage_2"]["doctrine_id"] = "unapproved.stage_claim"

        with self.assertRaisesRegex(ValueError, "canonical doctrine"):
            EligibilityEvidence.from_mapping(payload)


if __name__ == "__main__":
    unittest.main()
