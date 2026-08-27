"""What the reducer does with structure that deteriorated while the stop held."""

from __future__ import annotations

import unittest

from scripts.minervini.risk import reduce_risk


AS_OF = "2026-08-21"
ROLES = "management.ema21_sma50_roles"
TWENTY = "management.close_below_20_day_average_lowers_probability"
LARGEST = "management.largest_decline_since_stage2_start"


def trail(state: str, **extra: object) -> dict:
    record = {"state": state, "audited_from": "2026-08-10", "through": AS_OF, "average": 104.0, "last_close": 101.0, "last_close_distance_pct": -2.8846153846, "closes_below_in_a_row": 2 if state == "breached" else 0, "breach_date": AS_OF if state == "breached" else None, "quality": None}
    if state == "breached":
        record["quality"] = {"close_distance_pct": -2.8846153846, "closing_range_pct": 50.0, "second_close_above_first_close": False, "second_close_above_first_low": False}
    record.update(extra)
    return record


def measured(*, selected: str | None = None, ema21: str = "clear", sma50: str = "clear", twenty: str = "above", largest_daily: bool = False) -> dict:
    return {
        "moving_average_trail": {"doctrine_id": ROLES, "binds": False, "selected": selected, "ema21": trail(ema21), "sma50": trail(sma50)},
        "twenty_day_average": {"doctrine_id": TWENTY, "state": twenty, "date": AS_OF, "average": 103.0, "close": 101.0, "close_distance_pct": -1.9417475728},
        "largest_decline_since_stage2_start": {
            "doctrine_id": LARGEST, "binds": True, "state": "reported", "stage2_start": "2026-03-02",
            "daily": {"state": "reported", "largest_pct": -7.5, "date": AS_OF if largest_daily else "2026-05-04", "last_session_is_largest": largest_daily, "volume_ratio": 3.0, "volume_baseline_sessions": 50, "volume_signal": {"state": "reported"}},
            "weekly": {"state": "reported", "largest_pct": None, "week_ending": AS_OF, "latest_completed_week_is_largest": False},
        },
    }


def held(**overrides: object) -> dict:
    payload = {
        "mode": "active",
        "as_of": AS_OF,
        "entry_price": 100.0,
        "entry_date": "2026-08-10",
        # The 20-day rule the source states begins "Once the stock successfully breaks out",
        # so these fixtures declare the breakout the position was entered on.
        "breakout_date": "2026-08-10",
        "stop_price": 94.0,
        "current_price": 101.0,
        "completed_price_path": {"state": "clear", "checked_level": 94.0, "from": "2026-08-10", "through": AS_OF, "bars_checked": 9},
    }
    payload.update(overrides)
    return payload


def actions(result: dict) -> list[tuple[str, str, str]]:
    return [(action["action"], action["doctrine_id"], action.get("reason")) for action in result["management_actions"]]


class TheGoldenCase(unittest.TestCase):
    """The stop was never touched and the structure went bad. HOLD alone would be the wrong answer."""

    def test_untouched_stop_with_two_closes_under_the_ema_and_a_close_under_the_20_day_is_hold_plus_review(self) -> None:
        result = reduce_risk(held(management=measured(ema21="breached", twenty="below")))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(
            actions(result),
            [("REVIEW", ROLES, "two_closes_below_ema21"), ("REVIEW", TWENTY, "close_below_20_day_average")],
        )
        review = result["management_actions"][0]
        self.assertIs(review["binds"], False)
        self.assertEqual(review["source"], "[TL]")
        self.assertEqual(review["evidence"]["breach_date"], AS_OF)
        self.assertEqual(review["evidence"]["quality"]["closing_range_pct"], 50.0)
        self.assertIs(result["management_actions"][1]["binds"], True)
        self.assertEqual(result["management_evidence"]["twenty_day_average"]["close_distance_pct"], -1.9417475728)

    def test_without_a_declared_breakout_the_twenty_day_rule_is_withheld_and_says_so(self) -> None:
        payload = held(management=measured(ema21="clear", twenty="below"))
        payload.pop("breakout_date")
        result = reduce_risk(payload)

        self.assertEqual(actions(result), [])
        block = result["management_evidence"]["twenty_day_average"]
        self.assertEqual(block["state"], "below")
        self.assertEqual(block["action_withheld_reason"], "breakout_date_not_declared")

    def test_a_breakout_date_the_bars_could_not_find_withholds_it_the_same_way(self) -> None:
        # The measurements already said no completed session printed on the declared date.
        # An action read from that anchor would be read from a session nobody traded.
        payload = held(management={**measured(ema21="clear", twenty="below"), "gaps_since_breakout": {"state": "unavailable", "reason": "no_completed_bar_on_breakout_date"}})
        result = reduce_risk(payload)

        self.assertEqual(actions(result), [])
        self.assertEqual(result["management_evidence"]["twenty_day_average"]["action_withheld_reason"], "no_completed_bar_on_breakout_date")

    def test_a_breakout_the_history_begins_after_withholds_it_as_well(self) -> None:
        # The other way a declared anchor is absent: the provider's history starts later
        # than the date, so no session on it was ever seen.
        payload = held(management={**measured(ema21="clear", twenty="below"), "gaps_since_breakout": {"state": "unavailable", "reason": "history_starts_after_breakout_date"}})
        result = reduce_risk(payload)

        self.assertEqual(actions(result), [])
        self.assertEqual(result["management_evidence"]["twenty_day_average"]["action_withheld_reason"], "history_starts_after_breakout_date")

    def test_the_earlier_exit_names_the_failure_when_both_happened(self) -> None:
        # The declared average closed the position on the 3rd; the stop printed on the 22nd.
        # A level a position that no longer existed could not have reached is not its exit.
        management = measured(selected="ema21", ema21="breached", twenty="above")
        management["moving_average_trail"]["ema21"]["breach_date"] = "2025-12-03"
        payload = held(management_average="ema21", management=management)
        payload["completed_price_path"] = {"state": "breached", "checked_level": 80.0, "governing_role": "stop", "from": "2025-12-01", "through": "2025-12-22", "breach_date": "2025-12-22", "bars_checked": 15}
        result = reduce_risk(payload)

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["management_average_exit"])

    def test_the_stop_still_names_it_when_the_stop_came_first(self) -> None:
        management = measured(selected="ema21", ema21="breached", twenty="above")
        management["moving_average_trail"]["ema21"]["breach_date"] = "2025-12-22"
        payload = held(management_average="ema21", management=management)
        payload["completed_price_path"] = {"state": "breached", "checked_level": 80.0, "governing_role": "stop", "from": "2025-12-01", "through": "2025-12-03", "breach_date": "2025-12-03", "bars_checked": 3}
        result = reduce_risk(payload)

        self.assertEqual(result["failed"], ["completed_stop_breach"])

    def test_the_same_structure_with_the_ema_declared_as_the_exit_plan_is_a_sell(self) -> None:
        result = reduce_risk(held(management_average="ema21", management=measured(selected="ema21", ema21="breached", twenty="below")))

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["management_average_exit"])
        self.assertEqual(result["management_actions"], [])
        self.assertEqual(result["management_evidence"]["moving_average_trail"]["ema21"]["breach_date"], AS_OF)


class TheAverageNotChosenIsStillReviewEvidence(unittest.TestCase):
    def test_a_breach_of_the_other_average_is_review_not_sell(self) -> None:
        result = reduce_risk(held(management_average="ema21", management=measured(selected="ema21", sma50="breached")))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(actions(result), [("REVIEW", ROLES, "two_closes_below_sma50")])

    def test_a_clear_trail_says_nothing(self) -> None:
        result = reduce_risk(held(management=measured()))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["management_actions"], [])


class TheDeclaredExitPlanHasToBeAuditable(unittest.TestCase):
    def test_a_selected_average_the_bars_could_not_read_leaves_hold_unestablished(self) -> None:
        unread = measured(selected="sma50")
        unread["moving_average_trail"]["sma50"] = {"state": "unavailable", "reason": "insufficient_history_for_average", "sessions_required": 50}
        result = reduce_risk(held(management_average="sma50", management=unread))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("management_average_trail", result["missing"])

    def test_a_selected_average_with_no_measurement_at_all_is_the_same_gap(self) -> None:
        result = reduce_risk(held(management_average="ema21"))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("management_average_trail", result["missing"])

    def test_an_average_the_harness_does_not_measure_is_a_request_it_cannot_read(self) -> None:
        result = reduce_risk(held(management_average="sma200", management=measured()))

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("management_average", result["missing"])

    def test_a_breach_of_the_declared_average_outranks_a_stop_path_nobody_audited(self) -> None:
        result = reduce_risk(held(management_average="ema21", management=measured(selected="ema21", ema21="breached"), completed_price_path=None))

        self.assertEqual(result["verdict"], "SELL")


class TheLargestDeclineOfTheAdvance(unittest.TestCase):
    def test_the_last_session_being_the_largest_decline_is_review_that_needs_the_chart(self) -> None:
        result = reduce_risk(held(management=measured(largest_daily=True)))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(actions(result), [("REVIEW", LARGEST, "largest_decline_since_stage2_start")])
        review = result["management_actions"][0]
        self.assertIs(review["needs_chart"], True)
        self.assertEqual(review["evidence"]["daily"]["largest_pct"], -7.5)

    def test_an_earlier_largest_decline_is_evidence_but_not_an_action(self) -> None:
        result = reduce_risk(held(management=measured()))

        self.assertEqual(result["management_actions"], [])
        self.assertEqual(result["management_evidence"]["largest_decline_since_stage2_start"]["daily"]["largest_pct"], -7.5)


if __name__ == "__main__":
    unittest.main()


class TwoExitsOnOneSessionDidNotHappenAtOneMoment(unittest.TestCase):
    """Inside a session the order is the prices', not the words'."""

    def payload(self, **evidence) -> dict:
        return {
            "mode": "active",
            "as_of": "2025-12-31",
            "entry_price": 100.0,
            "entry_date": "2025-12-01",
            "stop_price": 90.0,
            "management_average": "ema21",
            **evidence,
        }

    def test_a_live_breach_precedes_an_average_that_closed_the_same_day(self) -> None:
        result = reduce_risk(self.payload(
            live_stop_check=True,
            live_stop={"state": "triggered", "partial_session": True},
            management={"moving_average_trail": {"ema21": {"state": "breached", "breach_date": "2025-12-31"}}},
        ))

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["live_stop_breach"])

    def test_a_stop_taken_out_intraday_precedes_an_average_that_closed_the_same_day(self) -> None:
        result = reduce_risk(self.payload(
            completed_price_path={"state": "breached", "basis": "completed_daily_low", "breach_date": "2025-12-31", "governing_role": "stop"},
            management={"moving_average_trail": {"ema21": {"state": "breached", "breach_date": "2025-12-31"}}},
        ))

        self.assertEqual(result["failed"], ["completed_stop_breach"])

    def test_a_stop_the_bars_measured_names_it_before_the_same_session_s_assertion(self) -> None:
        result = reduce_risk(self.payload(
            live_stop_check=True,
            live_stop={"state": "triggered", "partial_session": True},
            completed_price_path={"state": "breached", "basis": "completed_daily_low", "breach_date": "2025-12-31", "governing_role": "stop"},
        ))

        self.assertEqual(result["failed"], ["completed_stop_breach"])

    def test_a_level_read_from_the_close_yields_to_a_live_breach_the_same_day(self) -> None:
        result = reduce_risk(self.payload(
            invalidation={"price": 95.0},
            live_stop_check=True,
            live_stop={"state": "triggered", "partial_session": True},
            completed_price_path={"state": "breached", "basis": "completed_daily_close", "breach_date": "2025-12-31", "governing_role": "invalidation"},
        ))

        self.assertEqual(result["failed"], ["live_stop_breach"])

    def test_an_average_that_closed_first_still_owns_an_earlier_day(self) -> None:
        result = reduce_risk(self.payload(
            live_stop_check=True,
            live_stop={"state": "triggered", "partial_session": True},
            management={"moving_average_trail": {"ema21": {"state": "breached", "breach_date": "2025-12-23"}}},
        ))

        self.assertEqual(result["failed"], ["management_average_exit"])
