from __future__ import annotations

import json
import pathlib
import unittest

import pandas as pd

from scripts.minervini.setup import evaluate_setup
from scripts.minervini.setup_evidence import build_setup_evidence


FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "setup"


def completed_history(name: str = "completed_breakout.json") -> pd.DataFrame:
    history = pd.DataFrame(json.loads((FIXTURES / name).read_text())).set_index("date")
    history.index = pd.to_datetime(history.index)
    return history


class SetupEvidencePublicSeamTests(unittest.TestCase):
    def test_ohlcv_identifies_a_candidate_trigger_but_never_promotes_a_vcp_label_to_completed_structure(self) -> None:
        evidence = build_setup_evidence(completed_history(), chart_judgments={"vcp_label": "Standard VCP"})

        self.assertEqual(evidence["price_geometry"]["state"], "needs_chart")
        self.assertEqual(evidence["supply_evidence"]["state"], "needs_chart")
        self.assertEqual(evidence["vcp_label"], "Standard VCP")
        self.assertEqual(evidence["entry"]["kind"], "candidate_pivot")
        self.assertEqual(evidence["entry"]["state"], "wait")
        self.assertEqual(evidence["entry"]["candidate_pivot"]["price"], 100.0)
        self.assertEqual(evidence["entry"]["trigger"]["price"], 100.0)
        self.assertEqual(evidence["entry"]["invalidation"]["state"], "needs_chart")
        self.assertEqual(evaluate_setup(evidence)["setup_state"], "incomplete")

    def test_completed_pivot_requires_explicit_geometry_judgment_and_completed_close_above_the_candidate_pivot(self) -> None:
        history = completed_history()
        history.loc[history.index[-1], "Close"] = 99.0
        evidence = build_setup_evidence(
            history,
            chart_judgments={
                "price_geometry": {"state": "pass", "base_depth_pct": 10.0},
                "supply_evidence": {"state": "pass", "volume_dry_up": True},
                "entry": {"kind": "completed_pivot", "state": "confirmed"},
            },
        )

        self.assertEqual(evidence["price_geometry"]["state"], "pass")
        self.assertEqual(evidence["supply_evidence"]["state"], "pass")
        self.assertEqual(evidence["entry"]["kind"], "completed_pivot")
        self.assertEqual(evidence["entry"]["state"], "wait")
        self.assertIn("completed_close_above_candidate_pivot", evidence["entry"]["confirmation_debt"])
        self.assertEqual(evaluate_setup(evidence)["setup_state"], "wait")

    def test_explicit_independent_geometry_supply_and_pivot_confirmation_make_the_existing_reducer_ready(self) -> None:
        evidence = build_setup_evidence(
            completed_history(),
            chart_judgments={
                "price_geometry": {"state": "pass", "base_depth_pct": 10.0},
                "supply_evidence": {"state": "pass", "volume_dry_up": True, "contractions": [18.0, 9.0]},
                "entry": {"kind": "completed_pivot", "state": "confirmed"},
            },
        )

        self.assertEqual(evidence["entry"]["state"], "pass")
        self.assertEqual(evidence["entry"]["price"], 101.0)
        self.assertEqual(evaluate_setup(evidence)["setup_state"], "ready")

    def test_tl_early_keeps_chart_supplied_confirmation_debt_and_requires_the_caller_opt_in(self) -> None:
        judgments = {
            "price_geometry": {"state": "pass"},
            "supply_evidence": {"state": "pass"},
            "entry": {
                "kind": "tl_early",
                "state": "eligible",
                "price": 98.5,
                "confirmation_debt": ["completed Minervini pivot breakout"],
                "minervini_later_pivot": {"price": 100.0, "condition": "break out above the pivot"},
                "invalidation": {"price": 94.0, "condition": "close below the early-entry low"},
            },
        }

        without_opt_in = build_setup_evidence(completed_history(), chart_judgments=judgments)
        with_opt_in = build_setup_evidence(completed_history(), chart_judgments=judgments, tactic_opt_in=True)

        self.assertFalse(without_opt_in["entry"]["opt_in"])
        self.assertTrue(with_opt_in["entry"]["opt_in"])
        self.assertEqual(with_opt_in["entry"]["confirmation_debt"], ["completed Minervini pivot breakout"])
        self.assertEqual(evaluate_setup(without_opt_in)["setup_state"], "wait")
        self.assertEqual(evaluate_setup(with_opt_in)["setup_state"], "ready")

    def test_invalid_or_insufficient_completed_bars_leave_all_visual_claims_unavailable(self) -> None:
        history = completed_history().iloc[:1].drop(columns=["Volume"])

        evidence = build_setup_evidence(history)

        self.assertEqual(evidence["price_geometry"]["state"], "unavailable")
        self.assertEqual(evidence["supply_evidence"]["state"], "unavailable")
        self.assertEqual(evidence["entry"]["state"], "unavailable")
        self.assertEqual(evaluate_setup(evidence)["setup_state"], "incomplete")


if __name__ == "__main__":
    unittest.main()
