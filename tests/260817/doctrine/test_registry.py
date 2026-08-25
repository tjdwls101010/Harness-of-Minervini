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

    def test_the_registry_holds_no_quarantined_rule_and_the_audit_view_agrees(self) -> None:
        # The one quarantined record, a Chapter 12 failure cascade, was deleted once
        # re-sourcing found no supporting passage in either corpus. Quarantine is for
        # material too weakly sourced to execute, not for material with no source at all.
        active_ids = {item["claim"]["id"] for item in doctrine.list()}
        audit_ids = {item["claim"]["id"] for item in doctrine.list(include_quarantined=True)}

        self.assertEqual(active_ids, audit_ids)
        self.assertNotIn("quarantine.ch12_failure_cascade", audit_ids)

    def test_validate_reports_a_complete_registry(self) -> None:
        result = doctrine.validate()

        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertGreaterEqual(result["claim_count"], 11)

    def test_every_claim_a_reducer_depends_on_is_exposed_to_runtime_consumers(self) -> None:
        claims = {item["claim"]["id"] for item in doctrine.list()}

        # The registry grew past a hundred records; naming them all here would only
        # restate the file. These are the ones a reducer will fail without.
        self.assertLessEqual(
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
            claims,
        )

    def test_recent_ipo_route_never_waives_a_known_standard_failure(self) -> None:
        result = doctrine.get_claim("eligibility.recent_ipo_primary_base")

        conditions = " | ".join(result["claim"]["rule"]["conditions"])
        self.assertIn("no known standard", conditions)
        self.assertIn("constructive consolidation near", conditions)
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
        # "in less than eight weeks", the source's own words. The condition used to paraphrase
        # them as "under eight weeks" while the threshold beside it compiled to `<=`, so exactly
        # eight weeks passed a criterion the sentence excludes.
        self.assertIn(
            "advance is at least 100 percent in less than eight weeks",
            result["claim"]["rule"]["conditions"],
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

    def test_management_averages_keep_their_separate_roles(self) -> None:
        management = doctrine.get_claim("management.ema21_sma50_roles")

        self.assertEqual(management["claim"]["rule"]["roles"]["ema_21"], "default trade management")
        self.assertEqual(management["claim"]["rule"]["trigger"], "two completed closes below the selected management average")
        # A practice-layer default, so it can inform a judgment but never reject a candidate.
        self.assertEqual(management["claim"]["layer"], "practice")
        self.assertNotEqual(management["claim"]["kind"], "hard_gate")

    def test_risk_spine_defends_breakeven_after_three_r(self) -> None:
        result = doctrine.get_claim("risk.profit_protection_at_3r")

        self.assertIn("three R", result["claim"]["rule"]["summary"])

    def test_runtime_registry_payloads_carry_no_source_tags_and_no_source_text(self) -> None:
        records = doctrine.list(include_quarantined=True)
        payload = json.dumps(records)

        self.assertNotIn("[M]", payload)
        self.assertNotIn("[TL]", payload)
        # Provenance is the audit half of a record and is returned beside the claim,
        # never inside it, so an executable claim carries no source text of its own.
        executable = json.dumps([record["claim"] for record in records])
        self.assertNotIn("quotations", executable)
        self.assertTrue(all("provenance" in record for record in records))


if __name__ == "__main__":
    unittest.main()
