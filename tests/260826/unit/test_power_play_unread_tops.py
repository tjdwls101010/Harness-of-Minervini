"""A top the loaded history ends before is a top nobody read, in both directions.

The chain already refuses to reject while one of these stands: a lower top nobody could reach
behind has not consented to the rejection by being silent. The same silence cannot be counted as
consent to a qualification either -- and until a reader could answer the two chart criteria,
nothing here could reach `qualified`, so the asymmetry had nowhere to show.

The quantifiers are genuinely asymmetric -- rejecting takes every reading, qualifying takes one --
but that asymmetry is about readings that were *read*. A top the walk never measured is not a
reading on either side of it.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import a_top_the_history_ends_before_series


def answered(history):
    evidence = build_power_play_evidence(history)
    keys = {question["key"]: "observed" for question in evidence["chart_questions"]}
    return build_power_play_evidence(history, chart_readings=keys)


class TheUnreadTopKeepsItsVote(unittest.TestCase):
    def test_the_fixture_really_does_run_out_of_history(self) -> None:
        evidence = build_power_play_evidence(a_top_the_history_ends_before_series())

        self.assertTrue(evidence["readings_ran_out_of_history"])
        self.assertEqual(evidence["readings"], 1)

    def test_answering_every_chart_it_asked_still_does_not_qualify(self) -> None:
        verdict = evaluate_power_play(answered(a_top_the_history_ends_before_series()))

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertIn("lower_top_left_unread", verdict["missing"])

    def test_what_closes_it_is_history_and_nothing_else(self) -> None:
        """Reported under its own cause, because a reader sent to a chart finds nothing to read."""
        from datetime import datetime, timezone

        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = a_top_the_history_ends_before_series()
        prices = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True, "corporate_actions": True, "distributions": True},
            ),
        )
        runtime = Runtime(price_history=lambda ticker, requested: prices)
        request = {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "no_cache": True}
        first = execute("ticker.power-play", request, runtime=runtime)
        keys = [f'{q["key"]}=observed' for q in first["data"]["chart_questions"]]
        payload = execute("ticker.power-play", {**request, "chart_readings": keys}, runtime=runtime)

        reasons = {item["id"]: item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons["lower_top_left_unread"], "history_ends_before_lower_top")
        self.assertEqual(payload["status"], "partial")


class TheGapsUnderOneUnreadTopEachNameTheirOwnCause(unittest.TestCase):
    def test_a_failure_it_withholds_and_a_chart_it_never_needed_are_told_apart(self) -> None:
        """One structure, two kinds of gap, and a reader who fixes the wrong one has fixed nothing.

        The depth gate failed and the rejection is held back only because a top nobody could read
        might have stood -- more history closes that. The two chart criteria never got a key,
        because the reading they belong to was already out when the questions were handed round;
        reading a chart closes nothing there.
        """
        from datetime import datetime, timezone

        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = a_top_the_history_ends_before_series(flag_depth_pct=40.0)
        prices = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True},
            ),
        )
        payload = execute(
            "ticker.power-play",
            {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "no_cache": True},
            runtime=Runtime(price_history=lambda ticker, requested: prices),
        )

        reasons = {item["id"].split(".")[-1]: item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons["flag_maximum_decline_gate_pct"], "history_ends_before_lower_top")
        self.assertEqual(reasons["launch_volume_character"], "rejected_before_a_chart_was_needed")
        self.assertEqual(reasons["lower_top_left_unread"], "history_ends_before_lower_top")
        self.assertEqual(payload["next_capabilities"], [])


if __name__ == "__main__":
    unittest.main()
