"""Context that changes what a holder does, and context that only informs them."""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


AS_OF = "2026-08-21"
DEFENSE = "management.market_defense_tightens_stops"
EARNINGS = "management.earnings_awareness_while_holding"
ZANGER = "management.zanger_does_not_hold_through_earnings"
BASE_COUNT = "basecount.typical_top_after_3_to_5_bases"


def held(**extra: object) -> dict:
    stop = float(extra.pop("stop_price", 90.0))
    return {
        "mode": "active",
        "as_of": AS_OF,
        "entry_price": 100.0,
        "entry_date": "2026-08-10",
        "stop_price": stop,
        "current_price": 104.0,
        "completed_price_path": {"state": "clear", "checked_level": stop, "from": "2026-08-10", "through": AS_OF, "bars_checked": 9},
        **extra,
    }


def actions(result: dict) -> list[tuple[str, str]]:
    return [(action["action"], action["doctrine_id"]) for action in result["management_actions"]]


class ADeterioratingMarketTightensTheStop(unittest.TestCase):
    def test_a_defensive_market_raises_the_stop_and_never_sells_the_ticker(self) -> None:
        result = reduce_risk(held(market={"state": "defensive"}))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertIn(("RAISE_STOP", DEFENSE), actions(result))
        action = next(item for item in result["management_actions"] if item["doctrine_id"] == DEFENSE)
        self.assertIs(action["binds"], True)
        self.assertEqual(action["to_at_least"], 94.0)
        self.assertEqual(action["evidence"]["market_state"], "defensive")
        self.assertEqual(action["evidence"]["stop_pct"], 10.0)
        self.assertEqual(action["evidence"]["difficult_market_band"]["source_range"], [5, 6])

    def test_a_stop_already_inside_the_tightened_range_needs_no_raise(self) -> None:
        result = reduce_risk(held(market={"state": "cautious"}, stop_price=94.5))

        self.assertNotIn(DEFENSE, [doctrine_id for _, doctrine_id in actions(result)])
        band = result["management_evidence"]["market_defense"]["difficult_market_band"]
        self.assertEqual(band["state"], "within_source_range")

    def test_a_favorable_market_says_nothing_about_the_stop(self) -> None:
        result = reduce_risk(held(market={"state": "favorable"}))

        self.assertEqual(actions(result), [])
        self.assertEqual(result["management_evidence"]["market_defense"]["market_state"], "favorable")


class EarningsAhead(unittest.TestCase):
    def test_a_report_still_ahead_is_a_review_with_the_contrast_beside_it(self) -> None:
        result = reduce_risk(held(earnings_date="2026-08-27"))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertIn(("REVIEW", EARNINGS), actions(result))
        action = next(item for item in result["management_actions"] if item["doctrine_id"] == EARNINGS)
        self.assertIs(action["binds"], True)
        self.assertEqual(action["evidence"]["earnings_date"], "2026-08-27")
        self.assertEqual(action["evidence"]["days_until"], 6)
        contrast = action["evidence"]["contrast"]
        self.assertEqual(contrast["doctrine_id"], ZANGER)
        self.assertIs(contrast["binds"], False)
        self.assertEqual(contrast["source"], "Zanger")

    def test_a_report_already_behind_the_position_is_evidence_only(self) -> None:
        result = reduce_risk(held(earnings_date="2026-08-12"))

        self.assertEqual(actions(result), [])
        self.assertEqual(result["management_evidence"]["earnings"]["state"], "reported")
        self.assertIs(result["management_evidence"]["earnings"]["ahead"], False)

    def test_an_undeclared_report_is_a_gap_named_as_one(self) -> None:
        result = reduce_risk(held())

        self.assertEqual(result["management_evidence"]["earnings"], {"state": "unavailable", "reason": "earnings_date_not_declared"})


class BaseCountIsPerspectiveNotAVerdict(unittest.TestCase):
    def test_a_late_base_is_reported_against_the_band_and_creates_no_action(self) -> None:
        result = reduce_risk(held(base_count=5))

        self.assertEqual(actions(result), [])
        block = result["base_count_context"]
        self.assertEqual(block["base_count"], 5)
        self.assertEqual(block["band"]["state"], "within_source_range")
        self.assertEqual(block["disclaimer_doctrine_id"], "basecount.role_and_disclaimer")

    def test_a_sixth_base_sits_past_the_band_and_still_creates_no_action(self) -> None:
        result = reduce_risk(held(base_count=6))

        self.assertEqual(actions(result), [])
        self.assertEqual(result["base_count_context"]["band"]["state"], "above_source_range")


class BreakevenProtectionIsNeverAnUndeclaredSale(unittest.TestCase):
    """A stop above the last completed close would take the position out at market."""

    PROTECTION = "risk.profit_protection_at_3r"

    def test_three_r_reached_and_given_back_reports_instead_of_ordering(self) -> None:
        payload = held(stop_price=94.0, current_price=95.0, max_high_since_entry=118.0)
        result = reduce_risk(payload)

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual([action for action in result["management_actions"] if action["doctrine_id"] == self.PROTECTION], [])
        withheld = result["risk_controls"]["breakeven_protection_not_placeable"]
        self.assertEqual(withheld["to_at_least"], 100.0)
        self.assertEqual(withheld["current_price"], 95.0)
        self.assertEqual(withheld["reason"], "breakeven_is_above_the_current_price")
        self.assertIs(result["risk_controls"]["breakeven_protection_required"], True)

    def test_still_above_breakeven_the_stop_is_ordered_as_before(self) -> None:
        result = reduce_risk(held(stop_price=94.0, current_price=112.0, max_high_since_entry=118.0))

        action = next(item for item in result["management_actions"] if item["doctrine_id"] == self.PROTECTION)
        self.assertEqual(action["action"], "RAISE_STOP")
        self.assertEqual(action["to_at_least"], 100.0)


class TheDefenseMeasuresTheLevelThatIsActuallyInForce(unittest.TestCase):
    def test_a_widened_stop_is_measured_from_the_initial_level_the_audit_still_reads(self) -> None:
        # A stop is never widened, so 94 kept governing. Measuring the loss from 90 reports a
        # risk the trade does not run, and then orders a raise to the level the path beside
        # it says never stopped governing.
        payload = held(stop_price=90.0, initial_stop_price=94.0, stop_effective_date="2026-08-15", market={"state": "defensive"})
        # Both levels audited clear over the whole position, so the verdict is a HOLD and the
        # question is only which level everything downstream measures from.
        payload["completed_price_path"] = {
            "state": "clear",
            "checked_level": 94.0,
            "from": "2026-08-10",
            "through": AS_OF,
            "bars_checked": 9,
            "audits": [
                {"role": "stop", "level": 90.0, "state": "clear", "effective_from": "2026-08-10", "through": AS_OF, "bars_checked": 9},
                {"role": "initial_stop", "level": 94.0, "state": "clear", "effective_from": "2026-08-10", "through": AS_OF, "bars_checked": 9},
            ],
        }
        result = reduce_risk(payload)

        defense = result["management_evidence"]["market_defense"]
        self.assertEqual(defense["measured_from_stop"], 94.0)
        self.assertAlmostEqual(defense["stop_pct"], 6.0)
        self.assertEqual(defense["difficult_market_band"]["state"], "within_source_range")
        self.assertEqual([action for action in result["management_actions"] if action["doctrine_id"] == DEFENSE], [])

    def test_without_a_last_price_placeability_is_unavailable_rather_than_assumed(self) -> None:
        # The asserted-breach path is where a verdict travels with no last price at all. The
        # block still has to say it cannot establish placeability rather than assume it can.
        payload = held(stop_price=80.0, market={"state": "defensive"}, completed_stop={"state": "triggered"})
        del payload["current_price"]
        del payload["completed_price_path"]
        result = reduce_risk(payload)

        self.assertEqual(result["verdict"], "SELL")
        defense = result["management_evidence"]["market_defense"]
        self.assertIsNone(defense["tighten_to_is_placeable"])
        self.assertEqual(defense["not_placeable_reason"], "current_price_unavailable")

    def test_breakeven_exactly_at_the_last_close_is_not_placeable(self) -> None:
        result = reduce_risk(held(stop_price=94.0, current_price=100.0, max_high_since_entry=118.0))

        self.assertEqual([action for action in result["management_actions"] if action["doctrine_id"] == "risk.profit_protection_at_3r"], [])
        self.assertEqual(result["risk_controls"]["breakeven_protection_not_placeable"]["current_price"], 100.0)


class AnAssertedBreachIsAboutTheDeclaredStop(unittest.TestCase):
    def test_asserting_a_stop_breach_with_no_stop_declared_asserts_nothing(self) -> None:
        # "The stop was hit" names a level. With none declared it names nothing, and an
        # invalidation plan cannot stand in for it.
        payload = {
            "mode": "active",
            "as_of": AS_OF,
            "entry_price": 100.0,
            "entry_date": "2026-08-10",
            "invalidation": {"price": 95.0, "condition": "close below base low"},
            "completed_stop": {"state": "triggered"},
        }
        result = reduce_risk(payload)

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["failed"], [])
        # And the bars are still owed: nothing was settled, so the price path is missing.
        self.assertIn("completed_price_path", result["missing"])

    def test_the_same_assertion_with_a_declared_stop_sells(self) -> None:
        payload = {"mode": "active", "as_of": AS_OF, "entry_price": 100.0, "entry_date": "2026-08-10", "stop_price": 90.0, "completed_stop": {"state": "triggered"}}
        result = reduce_risk(payload)

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["completed_stop_breach"])


if __name__ == "__main__":
    unittest.main()
