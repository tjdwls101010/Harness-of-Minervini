"""An audit only counts for the level and window it actually covers."""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


BASE = {"mode": "active", "entry_price": 100.0, "entry_date": "2026-08-10", "current_price": 98.0}


def audit(role: str, level: float, effective_from: str, state: str = "clear") -> dict:
    return {"role": role, "level": level, "effective_from": effective_from, "through": "2026-08-21", "bars_checked": 8, "state": state}


class AuditWindowTests(unittest.TestCase):
    def test_an_audit_starting_after_a_level_took_effect_leaves_the_gap_open(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "invalidation": {"price": 90.0, "condition": "completed close below the base low"},
                "stop_price": 95.0,
                "stop_effective_date": "2026-08-20",
                "completed_price_path": {"state": "clear", "audits": [audit("stop", 95.0, "2026-08-20")]},
            }
        )

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["missing"], ["completed_price_path"])

    def test_an_unresolved_child_audit_cannot_ride_a_clear_parent(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "stop_price": 95.0,
                "completed_price_path": {"state": "clear", "audits": [audit("stop", 95.0, "2026-08-10", state="unavailable")]},
            }
        )

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["missing"], ["completed_price_path"])

    def test_an_audit_from_the_entry_date_covers_a_level_effective_at_entry(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "invalidation": {"price": 90.0, "condition": "completed close below the base low"},
                "invalidation_price": 90.0,
                "stop_price": 95.0,
                "stop_effective_date": "2026-08-20",
                "completed_price_path": {
                    "state": "clear",
                    "audits": [audit("stop", 95.0, "2026-08-20"), audit("invalidation", 90.0, "2026-08-10")],
                },
            }
        )

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["missing"], [])


class UnauditedConditionTests(unittest.TestCase):
    def test_a_condition_only_invalidation_blocks_hold_even_beside_a_clear_stop(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "stop_price": 90.0,
                "invalidation": {"condition": "completed close below the base low"},
                "completed_price_path": {"state": "clear", "audits": [audit("stop", 90.0, "2026-08-10")]},
            }
        )

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("invalidation_condition_not_audited", result["missing"])

    def test_a_known_invalidation_breach_beats_missing_evidence(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "invalidation": {"condition": "completed close below the base low", "state": "triggered"},
            }
        )

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["invalidation_triggered"])


class NonFiniteInputTests(unittest.TestCase):
    def test_an_infinite_average_gain_cannot_satisfy_the_half_average_cap(self) -> None:
        result = reduce_risk(
            {
                "mode": "prospective",
                "market": {"state": "pass"},
                "eligibility": {"state": "pass"},
                "setup": {"setup_state": "ready"},
                "fundamentals": {"state": "pass"},
                "risk": {"entry_price": 100.0, "stop_price": 91.0, "upside_price": 118.0, "average_gain_pct": float("inf")},
            }
        )

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("average_gain_pct", result["missing"])


if __name__ == "__main__":
    unittest.main()
