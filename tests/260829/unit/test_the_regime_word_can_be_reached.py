"""Which market signals carry the regime verdict, and which only stand beside it.

`favorable` used to require `market_breadth == supports`. The breadth block is scraped from a
live page the harness itself labels context-only, its best state is `observed`, and the
registry holds no breadth threshold to compare it against -- so the favorable word was
unreachable from any snapshot, and the defensive rule's breadth arm was dead code.

What can carry a verdict is what the harness measures against doctrine: the ranked leaders'
own bars, and the trader's own realized traction. The index switch is a real measurement that
can refuse but cannot authorize; breadth stands beside both as context.
"""

from __future__ import annotations

import unittest

from scripts.minervini.market import evaluate_market_snapshot


def _evidence(**overrides: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "breadth": {"state": "observed", "sections": {}},
        "qqq_21ema": {"state": "on"},
        "sectors": [],
        "industries": [],
        "leaders": [{"ticker": "LEAD", "behavior": {"state": "supports"}}],
        "trade_traction": {"state": "supports"},
    }
    evidence.update(overrides)
    return evidence


class RegimeReachabilityTests(unittest.TestCase):
    def test_leaders_and_traction_supporting_under_an_on_switch_reach_favorable(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence())

        self.assertEqual(snapshot["regime"]["judgment"], "favorable")

    def test_breadth_the_scraper_never_returned_does_not_withhold_the_favorable_word(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence(breadth={"state": "unavailable", "sections": {}}))

        self.assertEqual(snapshot["regime"]["judgment"], "favorable")

    def test_the_regime_block_names_which_signals_carried_the_verdict(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence())

        self.assertEqual(
            [item["signal_id"] for item in snapshot["regime"]["evidence"]],
            ["leader_traction", "trade_traction"],
        )
        self.assertEqual(
            [item["signal_id"] for item in snapshot["regime"]["context"]],
            ["qqq_21ema_switch", "market_breadth"],
        )

    def test_an_index_switch_that_has_gone_off_refuses_the_favorable_word_without_carrying_it(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence(qqq_21ema={"state": "off"}))

        self.assertEqual(snapshot["regime"]["judgment"], "cautious")

    def test_traction_and_leaders_both_contradicting_reach_defensive(self) -> None:
        snapshot = evaluate_market_snapshot(
            _evidence(
                leaders=[{"ticker": "LEAD", "behavior": {"state": "contradicts"}}],
                trade_traction={"state": "contradicts"},
            )
        )

        self.assertEqual(snapshot["regime"]["judgment"], "defensive")

    def test_traction_contradicting_under_a_switched_off_index_reaches_defensive(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence(qqq_21ema={"state": "off"}, trade_traction={"state": "contradicts"}))

        self.assertEqual(snapshot["regime"]["judgment"], "defensive")

    def test_a_verdict_bearing_signal_that_was_never_read_leaves_the_regime_incomplete(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence(leaders=[]))

        self.assertEqual(snapshot["regime"]["judgment"], "incomplete")

    def test_traction_the_user_has_not_answered_leaves_the_regime_incomplete(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence(trade_traction=None))

        self.assertEqual(snapshot["regime"]["judgment"], "incomplete")

    def test_a_group_gap_reports_in_evidence_quality_and_does_not_change_the_verdict(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence(sectors=None))

        self.assertEqual(snapshot["regime"]["judgment"], "favorable")
        self.assertEqual(snapshot["evidence_quality"]["status"], "partial")
        self.assertIn("sectors", snapshot["evidence_quality"]["missing_ids"])

    def test_leaders_supporting_against_traction_that_does_not_reaches_cautious(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence(trade_traction={"state": "mixed"}))

        self.assertEqual(snapshot["regime"]["judgment"], "cautious")


if __name__ == "__main__":
    unittest.main()
