from __future__ import annotations

import json
import pathlib
import unittest

from scripts.minervini.risk import reduce_risk


FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "setup_risk"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class RiskReducerPublicSeamTests(unittest.TestCase):
    def test_converged_prospective_evidence_is_buy_ready(self) -> None:
        result = reduce_risk(fixture("prospective_ready.json"))

        self.assertEqual(result["verdict"], "BUY-READY")
        self.assertEqual(result["risk_controls"]["initial_stop_pct"], 6.0)
        self.assertEqual(result["risk_controls"]["reward_to_risk"], 2.0)
        # The source gives the ordinary loss target as a range, so the reading carries
        # its range and where in it the stop landed, not a single pass/fail word.
        loss_target = result["risk_controls"]["loss_target"]
        self.assertEqual(loss_target["state"], "within_source_range")
        self.assertEqual(loss_target["source_range"], [6, 7])
        self.assertEqual(loss_target["measured"], 6.0)
        self.assertEqual(loss_target["band_position"], 0.0)

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
