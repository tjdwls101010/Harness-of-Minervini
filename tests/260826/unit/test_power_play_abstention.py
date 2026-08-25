"""An unanswered question is not a dissent, and neither is a payout's abstention.

Both look like disagreement to a comparison that only asks whether two readings say different
words. They are not: one reading saying `needs_chart` while another says `pass` is one chart read
and one not read, and a reading whose answer the dividend decided has declined to give one.

The distinction decides what a reader is told to go and do. Reported as a disputed peak, the fix
is to settle which top the structure hangs from -- a question the bars answer and no chart can.
Reported as a chart still unread under a contesting top, the fix is to read that top's chart,
which is the thing that actually closes it.
"""

from __future__ import annotations

import unittest

from scripts.minervini.power_play import evaluate_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.readings import power_play_answers
from tests.series import (
    a_payout_decided_criterion_under_a_lower_top_series,
    two_tops_that_both_await_the_chart_series,
)


class AnUnreadTopAbstains(unittest.TestCase):
    def _answer_one(self, history, index):
        evidence = build_power_play_evidence(history)
        keys = {
            question["key"]: "observed"
            for question in evidence["chart_questions"]
            if question["reading"] == index
        }
        self.assertTrue(keys)
        return build_power_play_evidence(history, **power_play_answers(history, keys))

    def test_answering_the_highest_top_does_not_dispute_the_peak(self) -> None:
        verdict = evaluate_power_play(self._answer_one(two_tops_that_both_await_the_chart_series(), 0))

        self.assertEqual(verdict["peak_identity"], "settled")
        self.assertEqual(verdict["contested_criteria"], [])

    def test_it_still_blocks_and_names_the_top_whose_chart_is_unread(self) -> None:
        """The criterion cannot close while a top that may contest it has not been looked at."""
        verdict = evaluate_power_play(self._answer_one(two_tops_that_both_await_the_chart_series(), 0))

        self.assertEqual(verdict["power_play_state"], "incomplete")
        self.assertIn(
            "fundamentals.power_play_exception.launch_volume_character",
            verdict["missing"],
        )
        self.assertEqual(
            verdict["awaiting_chart_under_another_top"],
            ["launch_volume_character"],
        )

    def test_the_signal_says_which_of_the_two_things_withdrew_it(self) -> None:
        verdict = evaluate_power_play(self._answer_one(two_tops_that_both_await_the_chart_series(), 0))
        volume = next(
            signal for signal in verdict["signals"]
            if signal["id"].endswith("launch_volume_character")
        )

        self.assertEqual(volume["withheld"], "chart_unread_under_another_top")


class APayoutAbstainsFromEitherSide(unittest.TestCase):
    def test_a_criterion_the_payout_decided_on_the_highest_top_is_not_a_dispute(self) -> None:
        """The comparison used to ignore only the lower reading's abstention.

        With the payout deciding the *primary* reading's answer, the same silence was counted as
        the primary dissenting from the tops below it, and the reader was sent to settle a top
        when the dividend calendar is what moved.
        """
        history = a_payout_decided_criterion_under_a_lower_top_series().iloc[:-8]
        evidence = build_power_play_evidence(history)

        self.assertIn("advance_minimum_pct", evidence["payout_sensitive_criteria"])
        self.assertNotIn("advance_minimum_pct", evidence["contested_criteria"])


class TheReaderIsSentSomewhereUseful(unittest.TestCase):
    def test_a_chart_unread_under_another_top_still_points_at_the_chart(self) -> None:
        """It is closed by looking at a picture, so the capability that draws one is named."""
        from datetime import datetime, timezone

        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
        from scripts.minervini.setup_structure import bars_fingerprint

        frame = two_tops_that_both_await_the_chart_series()
        prices = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True},
            ),
        )
        runtime = Runtime(price_history=lambda ticker, requested: prices)
        request = {"ticker": "TEST", "as_of": prices.meta.as_of.isoformat(), "no_cache": True}
        first = execute("ticker.power-play", request, runtime=runtime)
        one = [
            f'{q["key"]}=observed' for q in first["data"]["chart_questions"] if q["reading"] == 0
        ]
        payload = execute(
            "ticker.power-play",
            {**request, "chart_readings": one, "drawn_bars": bars_fingerprint(frame)},
            runtime=runtime,
        )

        reasons = {item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons, {"chart_unread_under_another_top"})
        self.assertIn("ticker.chart", payload["next_capabilities"])


if __name__ == "__main__":
    unittest.main()


class WhichSilenceIsHoldingTheCriterion(unittest.TestCase):
    """The three ways a contesting top can fail to agree, each read off the same comparison.

    Tested against the classification directly rather than through a fixture per case. Two of the
    three arrive through fixtures elsewhere in this module; the payout one is a shape no fixture
    in this repository produces -- a payout that decides a *lower* top's answer while leaving the
    highest top's alone and the chain's ordering intact -- and a rule nothing exercises is a rule
    nothing checks. What is pinned here is the contract the function states: which cause wins when
    several tops disagree in different ways, and that agreement is required rather than assumed.
    """

    def _classify(self, primary, *contesting):
        from scripts.minervini.power_play_evidence import _how_the_tops_disagree

        return _how_the_tops_disagree(primary, [dict(other) for other in contesting])

    def test_a_different_answer_is_a_dissent(self) -> None:
        self.assertEqual(self._classify({"a": "pass"}, {"a": "fail"}), {"a": "dissent"})

    def test_an_answer_the_payout_withdrew_is_not(self) -> None:
        self.assertEqual(self._classify({"a": "pass"}, {"a": "unavailable"}), {"a": "payout"})

    def test_nor_is_a_chart_nobody_read(self) -> None:
        self.assertEqual(self._classify({"a": "pass"}, {"a": "needs_chart"}), {"a": "chart"})

    def test_a_top_that_agrees_holds_nothing(self) -> None:
        self.assertEqual(self._classify({"a": "pass"}, {"a": "pass"}), {})

    def test_a_dissent_outranks_a_silence(self) -> None:
        """Whatever the quiet tops did, one of them said the criterion reads the other way."""
        self.assertEqual(
            self._classify({"a": "pass"}, {"a": "needs_chart"}, {"a": "fail"}),
            {"a": "dissent"},
        )

    def test_the_highest_top_s_own_gap_is_not_reported_as_the_tops_disagreeing(self) -> None:
        """It already blocks under its own name, and comparing an abstention says nothing."""
        self.assertEqual(self._classify({"a": "needs_chart"}, {"a": "pass"}), {})
        self.assertEqual(self._classify({"a": "unavailable"}, {"a": "pass"}), {})

    def test_a_criterion_no_top_may_contest_is_never_held(self) -> None:
        """The caller passes only the readings inside the contest distance, so an empty list is
        the whole of what "no top may contest this" means here."""
        self.assertEqual(self._classify({"a": "pass"}), {})
