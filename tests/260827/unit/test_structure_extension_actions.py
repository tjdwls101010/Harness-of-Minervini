"""Which of the strength measurements become actions, and which stay evidence."""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


AS_OF = "2026-08-21"
PAUSE = "management.tl_base_extension_pause_zone"
FAILED_VOLUME = "management.low_volume_breakout_then_high_volume_selling"
KEY_REVERSAL = "management.tl_key_reversal_criteria"


def held(management: dict) -> dict:
    return {
        "mode": "active",
        "as_of": AS_OF,
        "entry_price": 100.0,
        "entry_date": "2026-08-10",
        "breakout_date": "2026-08-10",
        "stop_price": 94.0,
        # Below 3R on purpose: profit protection has its own tests, and these assert the
        # whole action list so a stray RAISE_STOP would hide which rule fired.
        "current_price": 112.0,
        "completed_price_path": {"state": "clear", "checked_level": 94.0, "from": "2026-08-10", "through": AS_OF, "bars_checked": 9},
        "management": management,
    }


def band(state: str) -> dict:
    return {"id": f"{PAUSE}.pause_zone_pct", "doctrine_id": PAUSE, "role": "band", "state": state, "source_range": [20.0, 25.0], "direction": "inside_is_better"}


def actions(result: dict) -> list[tuple[str, str, str | None]]:
    return [(action["action"], action["doctrine_id"], action.get("reason")) for action in result["management_actions"]]


class TheBaseExtensionPauseZone(unittest.TestCase):
    def test_inside_the_zone_is_a_traderlion_review(self) -> None:
        result = reduce_risk(held({"base_extension": {"doctrine_id": PAUSE, "binds": False, "state": "reported", "base_top": 100.0, "extension_pct": 22.0, "max_extension_pct": 23.22, "band": band("within_source_range")}}))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(actions(result), [("REVIEW", PAUSE, "base_extension_pause_zone")])
        review = result["management_actions"][0]
        self.assertIs(review["binds"], False)
        self.assertEqual(review["source"], "[TL]")
        self.assertEqual(review["evidence"]["extension_pct"], 22.0)

    def test_without_a_declared_breakout_the_review_is_withheld_by_name(self) -> None:
        # The pause zone is an extension from the base measured after the breakout. Without a
        # declared breakout the extension is still reported, but ordering a review off it would
        # read post-breakout doctrine into a position that has not broken out.
        payload = held({"base_extension": {"doctrine_id": PAUSE, "binds": False, "state": "reported", "base_top": 100.0, "extension_pct": 22.0, "max_extension_pct": 23.22, "band": band("within_source_range")}})
        del payload["breakout_date"]
        result = reduce_risk(payload)

        self.assertEqual(result["management_actions"], [])
        self.assertEqual(result["management_evidence"]["base_extension"]["action_withheld_reason"], "breakout_date_not_declared")

    def test_a_breakout_the_bars_cannot_find_withholds_the_review_too(self) -> None:
        # A date the caller typed is not a session the market held. When the measurements
        # report no completed bar on it, the anchor these rules hang from does not exist.
        payload = held({
            "base_extension": {"doctrine_id": PAUSE, "binds": False, "state": "reported", "base_top": 100.0, "extension_pct": 22.0, "max_extension_pct": 23.22, "band": band("within_source_range")},
            "key_reversal": {"state": "unavailable", "reason": "no_completed_bar_on_breakout_date"},
        })
        result = reduce_risk(payload)

        self.assertEqual(result["management_actions"], [])
        self.assertEqual(result["management_evidence"]["base_extension"]["action_withheld_reason"], "no_completed_bar_on_breakout_date")

    def test_past_the_zone_or_short_of_it_is_evidence_only(self) -> None:
        for state in ("above_source_range", "below_source_range"):
            result = reduce_risk(held({"base_extension": {"doctrine_id": PAUSE, "binds": False, "state": "reported", "base_top": 100.0, "extension_pct": 30.0, "max_extension_pct": 31.0, "band": band(state)}}))

            self.assertEqual(result["management_actions"], [], state)
            self.assertEqual(result["management_evidence"]["base_extension"]["band"]["state"], state)


class FailedVolumeConfirmation(unittest.TestCase):
    def test_selling_heavier_than_the_breakout_is_a_review_that_names_sell_or_reduce(self) -> None:
        block = {"doctrine_id": FAILED_VOLUME, "binds": True, "state": "reported", "breakout_date": "2026-08-10", "breakout_volume_ratio": 0.8, "heaviest_down_session": {"date": "2026-08-14", "volume_ratio": 2.0}, "selling_volume_exceeded_breakout_volume": True, "qualitative_conditions_unresolved": ["breakout_was_on_low_volume", "selling_was_on_high_volume"]}
        result = reduce_risk(held({"failed_volume_confirmation": block}))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(actions(result), [("REVIEW", FAILED_VOLUME, "failed_volume_confirmation")])
        review = result["management_actions"][0]
        self.assertIs(review["binds"], True)
        self.assertIs(review["reduce_or_sell"], True)
        self.assertEqual(review["evidence"]["heaviest_down_session"]["volume_ratio"], 2.0)

    def test_the_event_not_occurring_is_evidence_only(self) -> None:
        block = {"doctrine_id": FAILED_VOLUME, "binds": True, "state": "reported", "breakout_date": "2026-08-10", "breakout_volume_ratio": 0.8, "heaviest_down_session": {"date": "2026-08-14", "volume_ratio": 0.5}, "selling_volume_exceeded_breakout_volume": False}
        result = reduce_risk(held({"failed_volume_confirmation": block}))

        self.assertEqual(result["management_actions"], [])
        self.assertIn("failed_volume_confirmation", result["management_evidence"])


class MeasurementsThatStayMeasurements(unittest.TestCase):
    def test_a_key_reversal_vector_is_carried_and_never_acted_on(self) -> None:
        block = {"doctrine_id": KEY_REVERSAL, "binds": False, "since": "2026-08-10", "date": AS_OF, "features": {"gap_up_filled_and_reversed": True, "highest_volume_since": True, "widest_range_since": True, "closed_below_prior_low": True, "closing_range_pct": 8.3, "visually_extended": None, "trend_line_of_highs_breached": None}, "computable_criteria_met": 3, "needs_chart": True}
        result = reduce_risk(held({"key_reversal": block, "gaps_since_breakout": {"state": "reported"}, "climax": {"state": "reported"}, "moving_average_extension": {"state": "reported"}}))

        self.assertEqual(result["management_actions"], [])
        for key in ("key_reversal", "gaps_since_breakout", "climax", "moving_average_extension"):
            self.assertIn(key, result["management_evidence"])


if __name__ == "__main__":
    unittest.main()
