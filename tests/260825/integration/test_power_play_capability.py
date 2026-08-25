"""The Power Play envelope: what the bars settle, what they refuse, and what neither is.

The exception this capability measures is the only route in the harness that lets a stock
through without verified fundamentals, so the envelope has to keep three things apart -- a
criterion that failed on measurement, a reading nobody has made yet, and a history that was
not in a position to say. Folding any two of them together is how the exception used to be
opened by typing one word.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from tests.series import power_play_series, reverse_split_series


def run(frame) -> dict:
    meta = SnapshotMeta(
        provider="fixture-prices",
        retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        as_of=frame.index[-1].date(),
        coverage={"completed_only": True, "corporate_actions": "Stock Splits" in frame},
    )
    runtime = Runtime(price_history=lambda ticker, requested: ProviderSnapshot(frame, meta))
    return execute(
        "ticker.power-play",
        {"ticker": "TEST", "as_of": meta.as_of.isoformat(), "no_cache": True},
        runtime=runtime,
    )


class TheEnvelopeKeepsTheThreeApart(unittest.TestCase):
    def test_a_measured_failure_is_a_finished_answer(self):
        payload = run(power_play_series(flag_depth_pct=40.0))

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["power_play_state"], "not_qualified")
        self.assertEqual(payload["next_capabilities"], [])

    def test_an_unread_chart_is_not_a_failure_and_says_what_would_settle_it(self):
        payload = run(power_play_series())

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["data"]["power_play_state"], "incomplete")
        self.assertEqual(payload["data"]["failed"], [])
        self.assertIn("ticker.chart", payload["next_capabilities"])

    def test_each_gap_reports_the_cause_it_actually_had(self):
        payload = run(power_play_series())
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}

        self.assertNotIn("corporate_action_evidence", reasons)
        self.assertEqual(
            reasons["fundamentals.power_play_exception.launch_volume_character"],
            "chart_reading_required",
        )

    def test_a_history_that_cannot_say_whether_a_split_happened_reports_that(self):
        payload = run(power_play_series(corporate_actions=False))
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}

        self.assertEqual(reasons["corporate_action_evidence"], "corporate_action_evidence_missing")

    def test_a_split_inside_the_span_is_a_different_gap_from_a_missing_column(self):
        payload = run(reverse_split_series())
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}

        self.assertEqual(
            reasons["corporate_action_evidence"],
            "corporate_action_inside_the_measured_span",
        )

    def test_the_signals_carry_the_claim_that_owns_each_criterion(self):
        payload = run(power_play_series())

        for signal in payload["signals"]:
            self.assertEqual(signal["doctrine_id"], "fundamentals.power_play_exception")


if __name__ == "__main__":
    unittest.main()
