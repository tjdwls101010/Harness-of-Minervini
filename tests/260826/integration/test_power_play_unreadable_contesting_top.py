"""A top the split left unreadable is not a chart anybody can go and read.

No key is issued for a reading whose span holds a corporate action -- a reader cannot corroborate
price action the split manufactured. So a criterion that reading holds open cannot arrive under
the chart's name: the envelope would ask for a picture, point at ticker.chart, and refuse the
answer that came back, because there is no key to answer with.

Its silence is still not consent. The criteria it measured are arithmetic about the action rather
than about the stock, so matching the highest top's answer is not agreement with it either.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from tests.series import power_play_series


def snapshot(frame):
    return ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            as_of=frame.index[-1].date(),
            coverage={"completed_only": True},
        ),
    )


class TheChartDebtItUsedToManufacture(unittest.TestCase):
    def setUp(self) -> None:
        # A marginal new high hands the search a second top, and the split sits inside that
        # lower top's span rather than the highest one's.
        self.frame = power_play_series(flag_sessions=30, marginal_new_high_at=-3, split_at=19)
        self.payload = execute(
            "ticker.power-play",
            {
                "ticker": "TEST",
                "as_of": self.frame.index[-1].date().isoformat(),
                "no_cache": True,
            },
            runtime=Runtime(price_history=lambda ticker, requested: snapshot(self.frame)),
        )

    def test_the_fixture_really_leaves_a_contesting_top_unreadable(self) -> None:
        self.assertEqual(self.payload["data"]["unreadable_readings"], ["2026-04-30"])
        self.assertEqual(self.payload["data"]["power_play_state"], "incomplete")

    def test_no_gap_claims_to_be_waiting_on_a_chart(self) -> None:
        reasons = {item["reason"] for item in self.payload["missing"]}

        self.assertNotIn("chart_unread_under_another_top", reasons)
        self.assertIn("corporate_action_under_another_top", reasons)

    def test_and_nobody_is_sent_to_draw_one(self) -> None:
        """Every question this run asked is the empty list, so naming ticker.chart would send a
        reader off for an answer the request boundary refuses."""
        self.assertEqual(self.payload["data"]["chart_questions"], [])
        self.assertEqual(self.payload["next_capabilities"], [])

    def test_the_machine_channel_never_reads_more_certain_than_the_verdict(self) -> None:
        """A signal reading `pass` or `fail` beside a gap that says the criterion is held is a
        second, contradicting answer -- and the one a consumer reads without the envelope. What it
        may still read is the measurement's own abstention: `needs_chart` decides nothing.
        """
        held = {item["id"]: item["reason"] for item in self.payload["missing"]}
        signals = {signal["id"]: signal for signal in self.payload["signals"]}

        for claim_id, reason in held.items():
            if claim_id not in signals:
                continue
            with self.subTest(claim_id=claim_id):
                self.assertNotIn(signals[claim_id]["state"], ("pass", "fail"))
                if signals[claim_id]["state"] == "unavailable":
                    self.assertEqual(signals[claim_id]["withheld"], reason)


if __name__ == "__main__":
    unittest.main()
