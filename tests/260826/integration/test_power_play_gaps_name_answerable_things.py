"""Every gap that says "chart" has to name a key somebody can answer.

A criterion left to a reader reads `needs_chart` on any reading that measured it, and the several
reasons a reading is never asked -- a split in its span, a rejection the bars already reached, a
structure the payout reordered -- are invisible in that word. Read off the criteria alone, a
contesting top that was never asked reported the criterion as a chart nobody has opened: the
envelope asked for a picture, pointed at ticker.chart, and would have refused the answer that came
back, because no key exists for that reading.

Its silence is still not consent. What changes is the name on the gap and where the reader is
sent, not whether the criterion is held.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.power_play_evidence import power_play_fingerprint
from scripts.minervini.setup_structure import bars_fingerprint
from tests.series import a_top_only_a_neighbour_confirms_series


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


class ATopTheBarsAlreadyThrewOut(unittest.TestCase):
    """The lower top here rejects on the six-week limit, so it is issued no key at all -- and it
    never gave the volume criterion an answer either."""

    def setUp(self) -> None:
        self.frame = a_top_only_a_neighbour_confirms_series()
        runtime = Runtime(price_history=lambda ticker, requested: snapshot(self.frame))
        request = {
            "ticker": "TEST",
            "as_of": self.frame.index[-1].date().isoformat(),
            "no_cache": True,
        }
        first = execute("ticker.power-play", request, runtime=runtime)
        self.payload = execute(
            "ticker.power-play",
            {
                **request,
                "chart_readings": [
                    f'{question["key"]}=observed' for question in first["data"]["chart_questions"]
                ],
                "drawn_bars": bars_fingerprint(self.frame),
                "measured_bars": power_play_fingerprint(self.frame),
            },
            runtime=runtime,
        )

    def test_the_fixture_really_rejects_the_lower_top(self) -> None:
        self.assertEqual(
            [rejection["peak_date"] for rejection in self.payload["data"]["reading_rejections"]],
            ["2026-04-17"],
        )

    def test_every_key_this_run_issued_has_been_answered(self) -> None:
        self.assertEqual(
            [
                question["condition"]
                for question in self.payload["data"]["chart_questions"]
                if question["answered"] is None
            ],
            [],
        )

    def test_so_no_gap_asks_for_another_chart(self) -> None:
        reasons = {item["reason"] for item in self.payload["missing"]}

        self.assertNotIn("chart_unread_under_another_top", reasons)
        self.assertIn("structure_rejected_under_another_top", reasons)
        self.assertEqual(self.payload["next_capabilities"], [])

    def test_and_the_criterion_is_still_held(self) -> None:
        """The name moved, not the verdict. A top that rejects has not agreed to anything."""
        self.assertEqual(self.payload["data"]["power_play_state"], "incomplete")

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
