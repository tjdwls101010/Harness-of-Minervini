"""A known breach outranks absent evidence, but never a request that contradicts itself."""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


AS_OF = "2026-08-21"


def audit(level: float, effective_from: str, through: str = AS_OF, state: str = "clear") -> dict:
    return {"role": "stop", "level": level, "effective_from": effective_from, "through": through, "bars_checked": 8, "state": state}


def position(**overrides: object) -> dict:
    payload = {
        "mode": "active",
        "as_of": AS_OF,
        "entry_price": 100.0,
        "entry_date": "2026-08-10",
        "current_price": 98.0,
        "stop_price": 95.0,
    }
    payload.update(overrides)
    return payload


class StaleAuditTests(unittest.TestCase):
    def test_a_path_that_stops_before_the_decision_date_cannot_establish_hold(self) -> None:
        result = reduce_risk(position(completed_price_path={"state": "clear", "audits": [audit(95.0, "2026-08-10", through="2026-08-14")]}))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("completed_price_path", result["missing"])

    def test_an_audit_starting_after_its_own_level_took_effect_leaves_the_gap_open(self) -> None:
        result = reduce_risk(position(completed_price_path={"state": "clear", "audits": [audit(95.0, "2026-08-17")]}))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("completed_price_path", result["missing"])

    def test_a_full_window_audit_establishes_hold(self) -> None:
        result = reduce_risk(position(completed_price_path={"state": "clear", "audits": [audit(95.0, "2026-08-10")]}))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["missing"], [])

    def test_active_reduction_needs_the_decision_date_it_is_measured_against(self) -> None:
        payload = position(completed_price_path={"state": "clear", "audits": [audit(95.0, "2026-08-10")]})
        del payload["as_of"]

        result = reduce_risk(payload)

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("as_of", result["missing"])


class AnchorIntegrityTests(unittest.TestCase):
    def test_a_breach_cannot_sell_a_position_that_does_not_exist_yet(self) -> None:
        result = reduce_risk(position(entry_date="2026-09-01", completed_stop={"state": "triggered"}))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("entry_date_after_as_of", result["missing"])

    def test_a_breach_cannot_sell_against_a_plan_that_was_never_declared(self) -> None:
        payload = position(completed_stop={"state": "triggered"})
        del payload["stop_price"]

        result = reduce_risk(payload)

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("stop_or_invalidation", result["missing"])

    def test_a_stop_that_predates_its_own_entry_is_contradictory(self) -> None:
        result = reduce_risk(position(stop_effective_date="2026-08-01", completed_price_path={"state": "clear", "audits": [audit(95.0, "2026-08-01")]}))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("stop_effective_date_before_entry_date", result["missing"])

    def test_a_breach_still_outranks_merely_absent_evidence(self) -> None:
        payload = position(completed_stop={"state": "triggered"})
        del payload["current_price"]

        result = reduce_risk(payload)

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["missing"], [])


if __name__ == "__main__":
    unittest.main()
