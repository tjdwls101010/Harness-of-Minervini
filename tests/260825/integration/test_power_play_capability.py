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


class AGapNamesWhatWouldActuallyCloseIt(unittest.TestCase):
    """Two gaps here are not chart readings, and calling them one is how a gate leaks.

    A flag with six sessions needs six more, not an eye; a criterion the two readings of the
    structure answer differently needs the top settled, not an eye either. Reported as
    `chart_reading_required`, both would be closed by whatever approval seam eventually answers
    the chart -- and the twelve-session minimum would have been waived by a reading of something
    else entirely.
    """

    def test_a_flag_that_has_not_finished_says_so_rather_than_asking_for_a_chart(self):
        payload = run(power_play_series(flag_sessions=6))
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}

        self.assertEqual(
            reasons["fundamentals.power_play_exception.flag_minimum_sessions"],
            "flag_still_forming",
        )

    def test_a_criterion_the_two_readings_answer_differently_says_that(self):
        payload = run(power_play_series(advance_pct=102.0, flag_depth_pct=8.0))
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}
        contested = payload["data"]["contested_criteria"]

        self.assertTrue(contested)
        for condition in contested:
            self.assertEqual(
                reasons[f"fundamentals.power_play_exception.{condition}"],
                "peak_identity_disputed",
            )


class TheEnvelopeCitesWhatDecidedIt(unittest.TestCase):
    def test_the_candidate_convention_is_in_the_doctrine_ids(self):
        """It moves verdicts, so it belongs in the provenance a reader audits against.

        Where the chain of tops stops decides which criteria may be contested and, through that,
        whether a rejection stands. Leaving it out cites only the source's own claim for a verdict
        this harness's own convention helped reach.
        """
        payload = run(power_play_series())

        self.assertIn("convention.power_play_top_candidates", payload["doctrine_ids"])
        self.assertIn("convention.trading_week", payload["doctrine_ids"])


class AFailureHeldBackByAnotherTopSaysSo(unittest.TestCase):
    """Withholding a measured failure is not the same as waiting for a chart.

    A top the distance excluded from contesting still reads these bars as a structure that
    stands, so the failure the highest top measured cannot carry the verdict. That gap closes
    when the tops are settled, never when someone reads the chart -- and reported as
    `chart_reading_required` it would be closed by whatever approval seam eventually answers the
    volume, which is the shape the still-forming flag already had to be kept out of.
    """

    def _payload(self):
        return run(
            power_play_series(
                dormant_price=10.0, flag_sessions=20, flag_depth_pct=8.0, later_high=21.0 / 0.9 + 0.01
            )
        )

    def test_the_gap_names_the_top_that_held_it_back(self):
        payload = self._payload()
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}

        self.assertEqual(
            reasons["fundamentals.power_play_exception.advance_minimum_pct"],
            "structure_stands_under_another_top",
        )

    def test_the_machine_channel_withholds_it_too(self):
        payload = self._payload()
        advance = next(
            signal for signal in payload["signals"]
            if signal["id"] == "fundamentals.power_play_exception.advance_minimum_pct"
        )

        self.assertEqual(advance["state"], "unavailable")
        self.assertEqual(advance["withheld"], "structure_stands_under_another_top")
