"""R is measured from the stop the trade started with; the TraderLion profile is the trader's to opt into."""

from __future__ import annotations

from tests.harness import held as shared_held

import unittest

from scripts.minervini.risk import reduce_risk


AS_OF = "2026-08-21"
TL_HALF = "management.tl_stage12_half_at_five_percent"
STRENGTH = "management.tl_sell_into_strength_at_average_gain_and_r_multiples"


def held(**overrides: object) -> dict:
    return shared_held(**{"current_price": 103.0, **overrides})


def raised(**overrides: object) -> dict:
    """The same position after its stop was lifted to 101 on the 14th."""

    audits = [
        {"role": "initial_stop", "level": 94.0, "effective_from": "2026-08-10", "through": "2026-08-13", "bars_checked": 4, "state": "clear"},
        {"role": "stop", "level": 101.0, "effective_from": "2026-08-14", "through": AS_OF, "bars_checked": 5, "state": "clear"},
    ]
    return held(
        stop_price=101.0,
        stop_effective_date="2026-08-14",
        completed_price_path={"state": "clear", "checked_level": 101.0, "from": "2026-08-14", "through": AS_OF, "bars_checked": 5, "audits": audits},
        **overrides,
    )


def actions(result: dict) -> list[tuple[str, str]]:
    return [(action["action"], action["doctrine_id"]) for action in result["management_actions"]]


class TheTraderLionProfileIsOptIn(unittest.TestCase):
    def test_at_five_percent_the_profile_says_sell_half_and_move_the_rest_to_breakeven(self) -> None:
        result = reduce_risk(held(max_high_since_entry=106.0, management_profile="tl_stage12"))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(actions(result), [("REDUCE", TL_HALF), ("RAISE_STOP", TL_HALF)])
        reduce, raise_stop = result["management_actions"]
        self.assertEqual(reduce["fraction"], 0.5)
        self.assertEqual(raise_stop["to_at_least"], 100.0)
        for action in (reduce, raise_stop):
            self.assertIs(action["binds"], False)
            self.assertEqual(action["source"], "[TL]")
            self.assertEqual(action["evidence"]["gain_pct_reached"], 6.0)
            self.assertEqual(action["evidence"]["measured_from"], "max_high_since_entry")
            self.assertEqual(action["evidence"]["state"], "contrast_pass")

    def test_the_same_bars_without_the_profile_say_nothing_from_traderlion(self) -> None:
        result = reduce_risk(held(max_high_since_entry=106.0))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["management_actions"], [])

    def test_short_of_five_percent_the_profile_has_nothing_due(self) -> None:
        result = reduce_risk(held(max_high_since_entry=104.9, management_profile="tl_stage12"))

        self.assertEqual(result["management_actions"], [])

    def test_the_profile_never_touches_the_verdict(self) -> None:
        breached = reduce_risk(held(max_high_since_entry=106.0, management_profile="tl_stage12", completed_price_path={"state": "breached", "basis": "completed_daily_low", "checked_level": 94.0, "governing_role": "stop", "from": "2026-08-10", "through": "2026-08-14", "breach_date": "2026-08-14", "breach_low": 93.0}))

        self.assertEqual(breached["verdict"], "SELL")
        self.assertEqual(breached["management_actions"], [])

    def test_both_rules_reached_report_both_with_their_own_claims(self) -> None:
        result = reduce_risk(held(max_high_since_entry=119.0, management_profile="tl_stage12"))

        self.assertEqual(
            actions(result),
            [("RAISE_STOP", "risk.profit_protection_at_3r"), ("REDUCE", TL_HALF), ("RAISE_STOP", TL_HALF)],
        )

    def test_a_profile_the_harness_does_not_know_is_a_request_it_cannot_read(self) -> None:
        result = reduce_risk(held(max_high_since_entry=106.0, management_profile="tl_stage3"))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("management_profile", result["missing"])


class TheProfilePromisesAPairAndDeliversAPair(unittest.TestCase):
    def test_a_position_with_only_an_invalidation_still_gets_both_actions(self) -> None:
        # No hard stop is declared; the breakeven half of the rule is then "set one at entry".
        result = reduce_risk(
            held(
                stop_price=None,
                invalidation={"price": 90.0, "condition": "completed close below the base low"},
                completed_price_path={"state": "clear", "checked_level": 90.0, "from": "2026-08-10", "through": AS_OF, "bars_checked": 9},
                max_high_since_entry=107.06,
                management_profile="tl_stage12",
            )
        )

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(actions(result), [("REDUCE", TL_HALF), ("RAISE_STOP", TL_HALF)])

    def test_without_a_measured_high_the_profile_reads_the_last_close(self) -> None:
        result = reduce_risk(held(current_price=106.0, management_profile="tl_stage12"))

        self.assertEqual(actions(result), [("REDUCE", TL_HALF), ("RAISE_STOP", TL_HALF)])
        self.assertEqual(result["management_actions"][0]["evidence"]["measured_from"], "current_price")


class RIsMeasuredFromTheInitialStop(unittest.TestCase):
    def test_a_raised_stop_with_the_initial_stop_declared_still_measures_r(self) -> None:
        result = reduce_risk(raised(max_high_since_entry=119.0, initial_stop_price=94.0))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["risk_controls"]["initial_risk"], 6.0)
        self.assertEqual(result["risk_controls"]["initial_risk_basis"], "initial_stop_price")
        self.assertEqual(result["risk_controls"]["r_multiple_reached"], 3.1666666667)
        # Protection is already in place: the stop stands above entry.
        self.assertFalse(result["risk_controls"]["breakeven_protection_required"])
        self.assertEqual(result["management_actions"], [])

    def test_a_raised_stop_without_the_initial_stop_cannot_say_what_r_is(self) -> None:
        result = reduce_risk(raised(max_high_since_entry=119.0))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertIsNone(result["risk_controls"]["initial_risk"])
        self.assertIsNone(result["risk_controls"]["initial_risk_basis"])
        self.assertIsNone(result["risk_controls"]["r_multiple_reached"])

    def test_an_unraised_stop_is_its_own_initial_stop(self) -> None:
        result = reduce_risk(held(max_high_since_entry=119.0))

        self.assertEqual(result["risk_controls"]["initial_risk"], 6.0)
        self.assertEqual(result["risk_controls"]["initial_risk_basis"], "stop_price")

    def test_an_initial_stop_at_or_above_entry_is_not_a_position_this_reducer_can_read(self) -> None:
        result = reduce_risk(held(initial_stop_price=100.0))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("initial_stop_price", result["missing"])

    def test_a_stop_that_differs_from_the_initial_stop_was_raised_on_some_date(self) -> None:
        result = reduce_risk(held(stop_price=101.0, initial_stop_price=94.0))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("stop_effective_date", result["missing"])


class SellingIntoStrengthHasReferencePointsNotTriggers(unittest.TestCase):
    def test_the_average_gain_and_r_multiple_are_reported_beside_the_position(self) -> None:
        result = reduce_risk(held(max_high_since_entry=115.0, current_price=110.0, average_gain_pct=12.0))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(
            result["management_evidence"]["strength_references"],
            {
                "doctrine_id": STRENGTH,
                "binds": False,
                "return_pct": 10.0,
                "max_return_pct": 15.0,
                "r_multiple": 1.6666666667,
                "max_r_multiple": 2.5,
                "average_gain_pct": 12.0,
                "distance_to_average_gain_pct": -2.0,
            },
        )
        self.assertEqual(result["management_actions"], [])

    def test_without_the_trader_s_average_gain_the_distance_is_unknown_not_zero(self) -> None:
        result = reduce_risk(held(max_high_since_entry=115.0, current_price=110.0))

        references = result["management_evidence"]["strength_references"]
        self.assertIsNone(references["average_gain_pct"])
        self.assertIsNone(references["distance_to_average_gain_pct"])
        self.assertEqual(references["return_pct"], 10.0)


if __name__ == "__main__":
    unittest.main()
