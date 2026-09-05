"""HOLD is not the whole answer for a position; what to do while holding is the rest of it."""

from __future__ import annotations

from tests.harness import held

import unittest

from scripts.minervini.risk import reduce_risk


AS_OF = "2026-08-21"


class ThreeRProtectionIsAnAction(unittest.TestCase):
    """Initial risk is 6; three R is reached at 118."""

    def test_a_position_that_reached_three_r_is_told_to_raise_its_stop_to_entry(self) -> None:
        result = reduce_risk(held(max_high_since_entry=119.0))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertTrue(result["risk_controls"]["breakeven_protection_required"])
        self.assertEqual(
            result["management_actions"],
            [
                {
                    "action": "RAISE_STOP",
                    "doctrine_id": "risk.profit_protection_at_3r",
                    "to_at_least": 100.0,
                    "evidence": {"r_multiple_reached": 3.1666666667, "measured_from": "max_high_since_entry"},
                }
            ],
        )

    def test_reaching_three_r_counts_even_after_price_gives_some_of_it_back(self) -> None:
        # The high was reached; profits are principal from that moment, and a retreat
        # to 110 is exactly the loss the rule exists to stop.
        result = reduce_risk(held(max_high_since_entry=119.0, current_price=110.0))

        self.assertEqual([action["action"] for action in result["management_actions"]], ["RAISE_STOP"])

    def test_a_position_short_of_three_r_has_nothing_to_do_yet(self) -> None:
        result = reduce_risk(held(max_high_since_entry=117.0))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertFalse(result["risk_controls"]["breakeven_protection_required"])
        self.assertEqual(result["management_actions"], [])
        self.assertEqual(result["risk_controls"]["r_multiple_reached"], 2.8333333333)

    def test_without_a_measured_high_the_current_price_is_the_floor_of_what_was_reached(self) -> None:
        result = reduce_risk(held(current_price=118.0))

        self.assertEqual(result["management_actions"][0]["evidence"], {"r_multiple_reached": 3.0, "measured_from": "current_price"})

    def test_a_stop_already_at_or_above_entry_needs_no_raising(self) -> None:
        result = reduce_risk(held(max_high_since_entry=125.0, stop_price=101.0, stop_effective_date="2026-08-14", completed_price_path={"state": "clear", "checked_level": 101.0, "from": "2026-08-14", "through": AS_OF, "bars_checked": 5}))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["management_actions"], [])
        self.assertFalse(result["risk_controls"]["breakeven_protection_required"])


class ANumberNeverRoundsAcrossItsOwnGate(unittest.TestCase):
    """Round p3a: a High one part in ten billion short of 3R read as `3.0` beside `required: false`."""

    def test_just_short_of_three_r_is_published_short_of_three_r(self) -> None:
        result = reduce_risk(held(max_high_since_entry=117.99999999994))

        self.assertFalse(result["risk_controls"]["breakeven_protection_required"])
        self.assertEqual(result["management_actions"], [])
        self.assertLess(result["risk_controls"]["r_multiple_reached"], 3.0)

    def test_the_same_holds_for_the_prospective_stop_ceiling(self) -> None:
        result = reduce_risk(
            {
                "mode": "prospective",
                "market": {"state": "favorable"},
                "eligibility": {"state": "pass"},
                "setup": {"state": "ready"},
                "fundamentals": {"state": "pass"},
                "entry_price": 100.0,
                "stop_price": 89.99999999999,
                "upside_price": 130.0,
                "average_gain_pct": 24.0,
            }
        )

        self.assertIn("initial_stop_pct", result["failed"])
        self.assertGreater(result["risk_controls"]["initial_stop_pct"], 10.0)


class ActionsBelongToAHeldPosition(unittest.TestCase):
    def test_a_sell_carries_no_management_actions(self) -> None:
        # The bars found the breach, rather than a caller asserting one the same bars cleared.
        result = reduce_risk(held(max_high_since_entry=130.0, completed_price_path={"state": "breached", "basis": "completed_daily_low", "checked_level": 94.0, "governing_role": "stop", "from": "2026-08-10", "through": "2026-08-14", "breach_date": "2026-08-14", "breach_low": 93.0}))

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["management_actions"], [])

    def test_an_incomplete_position_carries_no_management_actions(self) -> None:
        result = reduce_risk(held(max_high_since_entry=130.0, completed_price_path=None))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["management_actions"], [])

    def test_a_prospective_entry_has_no_position_to_manage(self) -> None:
        result = reduce_risk({"mode": "prospective", "eligibility": {"state": "pass"}})

        self.assertNotIn("management_actions", result)


if __name__ == "__main__":
    unittest.main()
