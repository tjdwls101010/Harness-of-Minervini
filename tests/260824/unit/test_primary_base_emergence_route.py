"""A Primary Base that has not yet emerged is unfinished timing, never a rejection."""

from __future__ import annotations

from tests.paths import FIXTURES as SHARED_FIXTURES

import json
import unittest

from scripts.minervini.eligibility import EligibilityEvidence, evaluate_eligibility


FIXTURES = SHARED_FIXTURES / "eligibility"


def evidence(emergence_state: str) -> dict:
    payload = json.loads((FIXTURES / "recent_ipo_primary_base_eligible.json").read_text())
    payload["primary_base"]["emergence"] = {
        "id": "primary_base.emergence",
        "state": emergence_state,
        "doctrine_id": "eligibility.recent_ipo_primary_base",
    }
    return payload


class PrimaryBaseEmergenceRouteTests(unittest.TestCase):
    def test_a_base_still_below_its_all_time_high_is_incomplete_not_avoid(self) -> None:
        result = evaluate_eligibility(EligibilityEvidence.from_mapping(evidence("not_triggered"))).to_dict()

        self.assertEqual(result["route"], "recent_ipo_primary_base")
        self.assertEqual(result["eligibility_state"], "incomplete")

    def test_a_triggered_emergence_with_supporting_quality_is_eligible(self) -> None:
        result = evaluate_eligibility(EligibilityEvidence.from_mapping(evidence("pass"))).to_dict()

        self.assertEqual(result["eligibility_state"], "eligible")

    def test_a_failed_structure_claim_still_rejects_the_route(self) -> None:
        payload = evidence("pass")
        payload["primary_base"]["quantitative_claims"][1]["state"] = "fail"

        result = evaluate_eligibility(EligibilityEvidence.from_mapping(payload)).to_dict()

        self.assertEqual(result["eligibility_state"], "avoid")


if __name__ == "__main__":
    unittest.main()
