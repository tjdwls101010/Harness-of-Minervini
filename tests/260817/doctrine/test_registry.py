from __future__ import annotations

import json
import unittest

from scripts.minervini import doctrine


class DoctrineRegistryTests(unittest.TestCase):
    def test_get_claim_returns_standard_gate_without_mixing_audit_provenance(self) -> None:
        result = doctrine.get_claim("eligibility.standard_trend_template")

        self.assertEqual(result["claim"]["id"], "eligibility.standard_trend_template")
        self.assertEqual(result["claim"]["kind"], "hard_gate")
        self.assertEqual(result["claim"]["failure"]["effect"], "reject")
        self.assertEqual(result["claim"]["missing"]["effect"], "incomplete")
        self.assertEqual(len(result["claim"]["rule"]["criteria"]), 8)
        self.assertNotIn("provenance", result["claim"])
        self.assertIn("provenance", result)

    def test_list_excludes_quarantined_rules_unless_an_audit_requests_them(self) -> None:
        active_ids = {item["claim"]["id"] for item in doctrine.list()}
        audit_ids = {item["claim"]["id"] for item in doctrine.list(include_quarantined=True)}

        self.assertNotIn("quarantine.ch12_failure_cascade", active_ids)
        self.assertIn("quarantine.ch12_failure_cascade", audit_ids)

    def test_validate_reports_a_complete_registry(self) -> None:
        result = doctrine.validate()

        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertGreaterEqual(result["claim_count"], 11)

    def test_all_executable_claims_are_exposed_to_runtime_consumers(self) -> None:
        claims = {item["claim"]["id"] for item in doctrine.list()}

        self.assertEqual(
            claims,
            {
                "scope.data_integrity",
                "eligibility.standard_stage2",
                "eligibility.standard_trend_template",
                "eligibility.recent_ipo_primary_base",
                "setup.vcp_supply_contraction",
                "fundamentals.power_play_exception",
                "risk.initial_stop_and_reward",
                "risk.hard_stop_and_no_average_down",
                "risk.profit_protection_at_3r",
                "tactic.early_entry_confirmation_debt",
                "management.ema21_sma50_roles",
            },
        )

    def test_recent_ipo_route_never_waives_a_known_standard_failure(self) -> None:
        result = doctrine.get_claim("eligibility.recent_ipo_primary_base")

        self.assertIn("no known standard gate failure", result["claim"]["rule"]["conditions"])
        self.assertEqual(result["claim"]["missing"]["effect"], "incomplete")

    def test_power_play_exception_is_limited_to_fundamentals_policy(self) -> None:
        result = doctrine.get_claim("fundamentals.power_play_exception")

        self.assertEqual(
            result["claim"]["rule"]["does_not_waive"],
            [
                "technical_eligibility",
                "market_alignment",
                "vcp_quality",
                "risk_controls",
                "accounting_integrity",
                "going_concern_risk",
                "excessive_dilution",
            ],
        )

    def test_early_entry_requires_confirmation_debt_and_exact_invalidation(self) -> None:
        result = doctrine.get_claim("tactic.early_entry_confirmation_debt")

        self.assertEqual(
            result["claim"]["required_inputs"],
            [
                "technical_eligibility",
                "early_entry_trigger",
                "confirmation_debt",
                "future_pivot_or_breakout",
                "invalidation",
            ],
        )

    def test_management_roles_and_weak_failure_cascade_remain_distinct(self) -> None:
        management = doctrine.get_claim("management.ema21_sma50_roles")
        cascade = doctrine.get_claim("quarantine.ch12_failure_cascade")

        self.assertEqual(management["claim"]["rule"]["roles"]["ema_21"], "default trade management")
        self.assertTrue(cascade["claim"]["quarantine"]["is_quarantined"])

    def test_risk_spine_defends_breakeven_after_three_r(self) -> None:
        result = doctrine.get_claim("risk.profit_protection_at_3r")

        self.assertIn("three R", result["claim"]["rule"]["summary"])

    def test_runtime_registry_payloads_do_not_embed_source_tags_or_long_source_text(self) -> None:
        payload = json.dumps(doctrine.list(include_quarantined=True))

        self.assertNotIn("[M]", payload)
        self.assertNotIn("[TL]", payload)


if __name__ == "__main__":
    unittest.main()
