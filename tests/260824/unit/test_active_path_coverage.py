"""HOLD requires a path that actually audited every protective level the caller declared."""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


BASE = {"mode": "active", "entry_price": 100.0, "entry_date": "2026-08-10", "current_price": 98.0}
COVERAGE = {"from": "2026-08-10", "through": "2026-08-21", "bars_checked": 10}


class PathCoverageTests(unittest.TestCase):
    def test_a_clear_path_without_a_named_audit_level_cannot_establish_hold(self) -> None:
        result = reduce_risk({**BASE, "stop_price": 95.0, "completed_price_path": {"state": "clear", **COVERAGE}})

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["missing"], ["completed_price_path"])

    def test_a_clear_path_without_a_covered_window_cannot_establish_hold(self) -> None:
        result = reduce_risk({**BASE, "stop_price": 95.0, "completed_price_path": {"state": "clear", "checked_level": 95.0}})

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["missing"], ["completed_price_path"])

    def test_each_declared_level_needs_its_own_audit(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "stop_price": 90.0,
                "invalidation": {"price": 95.0, "condition": "completed close below the base low"},
                "completed_price_path": {
                    "state": "clear",
                    "audits": [{"level": 90.0, "role": "stop", "effective_from": "2026-08-10", "through": "2026-08-21", "bars_checked": 10}],
                },
            }
        )

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["missing"], ["completed_price_path"])

    def test_two_audits_covering_both_levels_establish_hold(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "stop_price": 90.0,
                "invalidation": {"price": 95.0, "condition": "completed close below the base low"},
                "completed_price_path": {
                    "state": "clear",
                    "audits": [
                        {"level": 90.0, "role": "stop", "effective_from": "2026-08-10", "through": "2026-08-21", "bars_checked": 10},
                        {"level": 95.0, "role": "invalidation", "effective_from": "2026-08-10", "through": "2026-08-21", "bars_checked": 10},
                    ],
                },
            }
        )

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["missing"], [])


class UnauditableProtectionTests(unittest.TestCase):
    def test_a_condition_only_invalidation_cannot_establish_hold(self) -> None:
        result = reduce_risk({**BASE, "invalidation": {"condition": "completed close below the base low"}})

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("auditable_protective_level", result["missing"])

    def test_an_unusable_invalidation_price_is_not_silently_dropped(self) -> None:
        result = reduce_risk({**BASE, "invalidation": {"price": 0, "condition": "completed close below the base low"}})

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("auditable_protective_level", result["missing"])

    def test_a_missing_plan_is_reported_once_as_a_missing_plan(self) -> None:
        result = reduce_risk({"mode": "active", "entry_price": 100.0, "entry_date": "2026-08-10", "current_price": 98.0})

        self.assertEqual(result["missing"], ["stop_or_invalidation"])


if __name__ == "__main__":
    unittest.main()
