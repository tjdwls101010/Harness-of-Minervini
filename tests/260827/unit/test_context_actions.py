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
        block = result["management_evidence"]["base_count_context"]
        self.assertEqual(block["base_count"], 5)
        self.assertEqual(block["band"]["state"], "within_source_range")
        self.assertEqual(block["disclaimer_doctrine_id"], "basecount.role_and_disclaimer")

    def test_a_sixth_base_sits_past_the_band_and_still_creates_no_action(self) -> None:
        result = reduce_risk(held(base_count=6))

        self.assertEqual(actions(result), [])
        self.assertEqual(result["management_evidence"]["base_count_context"]["band"]["state"], "above_source_range")


if __name__ == "__main__":
    unittest.main()
