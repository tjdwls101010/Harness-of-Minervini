"""An active invalidation level must be compared with price, not merely read as a flag."""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


BASE = {
    "mode": "active",
    "entry_price": 100.0,
    "entry_date": "2026-08-10",
}


class ActiveInvalidationPriceTests(unittest.TestCase):
    def test_price_below_the_invalidation_level_sells_without_a_triggered_flag(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "current_price": 90.0,
                "invalidation": {"price": 95.0, "condition": "completed close below the base low"},
            }
        )

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["invalidation_breach"])

    def test_price_above_the_invalidation_level_still_needs_the_completed_path(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "current_price": 98.0,
                "invalidation": {"price": 95.0, "condition": "completed close below the base low"},
            }
        )

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["missing"], ["completed_price_path"])

    def test_a_path_audited_below_the_tightest_level_cannot_establish_hold(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "stop_price": 90.0,
                "current_price": 98.0,
                "invalidation": {"price": 95.0, "condition": "completed close below the base low"},
                "completed_price_path": {
                    "state": "clear",
                    "checked_level": 90.0,
                    "from": "2026-08-10",
                    "through": "2026-08-21",
                    "bars_checked": 10,
                },
            }
        )

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["missing"], ["completed_price_path"])

    def test_a_path_audited_at_the_tightest_level_establishes_hold(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "stop_price": 90.0,
                "current_price": 98.0,
                "invalidation": {"price": 95.0, "condition": "completed close below the base low"},
                "completed_price_path": {
                    "state": "clear",
                    "checked_level": 95.0,
                    "from": "2026-08-10",
                    "through": "2026-08-21",
                    "bars_checked": 10,
                },
            }
        )

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["missing"], [])

    def test_a_breached_completed_path_sells_even_when_the_latest_price_recovered(self) -> None:
        result = reduce_risk(
            {
                **BASE,
                "current_price": 98.0,
                "invalidation": {"price": 95.0, "condition": "completed close below the base low"},
                "completed_price_path": {
                    "state": "breached",
                    "checked_level": 95.0,
                    "breach_date": "2026-08-14",
                    "breach_low": 93.0,
                },
            }
        )

        self.assertEqual(result["verdict"], "SELL")


if __name__ == "__main__":
    unittest.main()
