from __future__ import annotations

import json
import pathlib
import unittest

from scripts.minervini.risk import reduce_risk
from scripts.minervini.setup import evaluate_setup


FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "setup_risk"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class SetupPublicSeamTests(unittest.TestCase):
    def test_vcp_label_without_separate_supply_evidence_is_incomplete_not_ready(self) -> None:
        result = evaluate_setup(fixture("vcp_label_only.json"))

        self.assertEqual(result["setup_state"], "incomplete")
        self.assertEqual(result["price_geometry"]["state"], "pass")
        self.assertEqual(result["supply_evidence"]["state"], "unavailable")
        self.assertIn("supply_evidence", result["missing"])

    def test_completed_pivot_with_geometry_and_supply_is_ready(self) -> None:
        result = evaluate_setup(fixture("completed_pivot.json"))

        self.assertEqual(result["setup_state"], "ready")
        self.assertEqual(result["entry"]["kind"], "completed_pivot")
        self.assertEqual(result["entry"]["confirmation_debt"], [])

    def test_tl_early_keeps_confirmation_debt_later_pivot_and_precise_invalidation(self) -> None:
        result = evaluate_setup(fixture("tl_early.json"))

        self.assertEqual(result["setup_state"], "ready")
        self.assertEqual(result["entry"]["tactic"], "[TL-EARLY]")
        self.assertEqual(result["entry"]["confirmation_debt"], ["completed Minervini pivot breakout"])
        self.assertEqual(result["entry"]["minervini_later_pivot"]["price"], 100.2)
        self.assertEqual(result["entry"]["invalidation"]["price"], 96.0)

    def test_tl_early_without_precise_invalidation_waits(self) -> None:
        evidence = fixture("tl_early.json")
        del evidence["entry"]["invalidation"]

        result = evaluate_setup(evidence)

        self.assertEqual(result["setup_state"], "wait")
        self.assertIn("precise_invalidation", result["missing"])


class RiskReducerPublicSeamTests(unittest.TestCase):
    def test_converged_prospective_evidence_is_buy_ready(self) -> None:
        result = reduce_risk(fixture("prospective_ready.json"))

        self.assertEqual(result["verdict"], "BUY-READY")
        self.assertEqual(result["risk_controls"]["initial_stop_pct"], 6.0)
        self.assertEqual(result["risk_controls"]["reward_to_risk"], 2.0)
        self.assertEqual(result["risk_controls"]["loss_target_context"], "within_6_to_7_pct_target")

    def test_complete_price_risk_evidence_does_not_need_a_duplicate_pass_flag(self) -> None:
        evidence = fixture("prospective_ready.json")
        del evidence["risk"]["state"]

        result = reduce_risk(evidence)

        self.assertEqual(result["verdict"], "BUY-READY")

    def test_known_eligibility_failure_beats_other_missing_evidence(self) -> None:
        result = reduce_risk({"mode": "prospective", "eligibility": {"state": "fail"}})

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("eligibility", result["failed"])

    def test_missing_critical_prospective_evidence_is_incomplete(self) -> None:
        result = reduce_risk({"mode": "prospective", "eligibility": {"state": "pass"}})

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertIn("market", result["missing"])

    def test_insufficient_reward_to_risk_is_avoid(self) -> None:
        evidence = fixture("prospective_ready.json")
        evidence["risk"]["upside_price"] = 111.9

        result = reduce_risk(evidence)

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("reward_to_risk", result["failed"])

    def test_stop_over_ten_percent_or_half_average_gain_is_avoid(self) -> None:
        evidence = fixture("prospective_ready.json")
        evidence["risk"].update({"stop_price": 89.0, "average_gain_pct": 16.0})

        result = reduce_risk(evidence)

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("initial_stop_pct", result["failed"])
        self.assertIn("half_average_gain_cap", result["failed"])

    def test_active_requires_entry_date_and_stop_or_invalidation(self) -> None:
        result = reduce_risk({"mode": "active", "as_of": "2026-08-21", "entry_price": 100.0})

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertCountEqual(result["missing"], ["entry_date", "stop_or_invalidation", "current_price"])

    def test_active_live_stop_breach_requires_explicit_live_check(self) -> None:
        evidence = {
            "mode": "active",
            "as_of": "2026-08-21",
            "entry_price": 100.0,
            "entry_date": "2026-08-10",
            "stop_price": 94.0,
            "live_stop": {"state": "triggered", "partial_session": True},
        }

        self.assertEqual(reduce_risk(evidence)["verdict"], "INCOMPLETE")
        evidence["live_stop_check"] = True
        self.assertEqual(reduce_risk(evidence)["verdict"], "SELL")

    def test_active_hold_requires_a_clear_completed_price_path(self) -> None:
        result = reduce_risk(
            {
                "mode": "active",
                "as_of": "2026-08-14",
                "entry_price": 100.0,
                "entry_date": "2026-08-10",
                "stop_price": 94.0,
                "current_price": 98.0,
                "completed_price_path": {
                    "state": "clear",
                    "checked_level": 94.0,
                    "from": "2026-08-10",
                    "through": "2026-08-14",
                    "bars_checked": 5,
                },
            }
        )

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual(result["missing"], [])

    def test_active_current_price_above_stop_without_completed_path_is_incomplete(self) -> None:
        result = reduce_risk(
            {
                "mode": "active",
                "as_of": "2026-08-21",
                "entry_price": 100.0,
                "entry_date": "2026-08-10",
                "stop_price": 94.0,
                "current_price": 98.0,
            }
        )

        self.assertEqual(result["verdict"], "INCOMPLETE")
        self.assertEqual(result["missing"], ["completed_price_path"])

    def test_active_completed_current_price_at_or_below_stop_is_sell(self) -> None:
        result = reduce_risk(
            {
                "mode": "active",
                "as_of": "2026-08-21",
                "entry_price": 100.0,
                "entry_date": "2026-08-10",
                "stop_price": 94.0,
                "current_price": 94.0,
            }
        )

        self.assertEqual(result["verdict"], "SELL")
        self.assertEqual(result["failed"], ["completed_stop_breach"])

    def test_active_completed_stop_or_invalidation_trigger_is_sell(self) -> None:
        evidence = {
            "mode": "active",
            "as_of": "2026-08-21",
            "entry_price": 100.0,
            "entry_date": "2026-08-10",
            "invalidation": {"price": 94.0, "state": "triggered"},
        }

        self.assertEqual(reduce_risk(evidence)["verdict"], "SELL")


if __name__ == "__main__":
    unittest.main()
