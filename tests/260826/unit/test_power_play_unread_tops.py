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
from tests.readings import power_play_answers
from tests.series import a_top_the_history_ends_before_series, power_play_series


def answered(history):
    evidence = build_power_play_evidence(history)
    keys = {question["key"]: "observed" for question in evidence["chart_questions"]}
    return build_power_play_evidence(history, **power_play_answers(history, keys))


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
        from scripts.minervini.power_play_evidence import power_play_fingerprint
        from scripts.minervini.setup_structure import bars_fingerprint

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
        payload = execute(
            "ticker.power-play",
            {**request, "chart_readings": keys, "drawn_bars": bars_fingerprint(frame),
             "measured_bars": power_play_fingerprint(frame)},
            runtime=runtime,
        )

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

        The reason names the *reading* rather than the structure, and the distinction is the whole
        point of the word: the structure is not rejected here, it is one rejected reading held
        open by a top nobody could reach behind. `structure_is_already_rejected` is the finished
        answer and rides on an `ok` envelope; this one rides on a `partial`.
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
        self.assertEqual(
            reasons["launch_volume_character"], "reading_rejected_before_a_chart_was_needed"
        )
        self.assertEqual(reasons["lower_top_left_unread"], "history_ends_before_lower_top")
        self.assertEqual(payload["next_capabilities"], [])
        # And the two criteria whose own reading is out owe nobody anything: no key exists for
        # them and none can, so marking them required tells the reader to close what they cannot.
        owed = {item["id"].split(".")[-1]: item["required"] for item in payload["missing"]}
        self.assertFalse(owed["launch_volume_character"])
        self.assertFalse(owed["flag_tightness_or_vcp"])
        self.assertTrue(owed["lower_top_left_unread"])


class TheGapDoesClose(unittest.TestCase):
    """Said to close on more history, so shown closing on more history.

    Not by the top becoming readable -- it never does, there is nothing behind it -- but by the
    stock trading on until that top falls out of the span the search looks in. Both windows are
    anchored at the last completed bar, so a top far enough back is not a candidate reading of
    this structure at all, which is the same rule that keeps the answer still when a caller loads
    a different amount of history.

    The window that opens is one session wide here, and that is the fixture rather than the rule:
    this structure's flag is already at the six-week limit, so the session after the one that
    frees it is the session the flag runs past it. A structure with room in its flag has as many
    sessions as it has room.
    """

    def _extend(self, frame, sessions):
        import pandas as pd

        index = pd.bdate_range(
            start=frame.index[-1] + pd.tseries.offsets.BDay(1), periods=sessions
        )
        last = frame.iloc[-1]
        tail = pd.DataFrame(
            {column: [float(last[column])] * sessions for column in frame.columns}, index=index
        )
        tail["Stock Splits"] = 0.0
        tail["Dividends"] = 0.0
        return pd.concat([frame, tail])

    def _state(self, sessions):
        history = self._extend(a_top_the_history_ends_before_series(), sessions)
        return evaluate_power_play(answered(history))

    def test_the_top_stays_unread_while_it_is_still_a_candidate(self) -> None:
        verdict = self._state(17)

        self.assertTrue(verdict["readings_ran_out_of_history"])
        self.assertIn("lower_top_left_unread", verdict["missing"])

    def test_one_more_session_puts_it_outside_the_span_and_the_gap_closes(self) -> None:
        verdict = self._state(18)

        self.assertFalse(verdict["readings_ran_out_of_history"])
        self.assertEqual(verdict["power_play_state"], "qualified")

    def test_and_the_session_after_that_the_flag_runs_past_its_limit(self) -> None:
        self.assertEqual(self._state(19)["power_play_state"], "not_qualified")


class TheDistanceIsInclusiveOnBothSidesOfTheChain(unittest.TestCase):
    """A top standing exactly the registered distance below the highest is the last one that may
    still contest. The unread top a few tests up is one half of that; this is the other, and they
    have to agree -- one comparison holds the boundary and the other excludes it, so a reader
    auditing a verdict next to the line would be told two different things about the same number.

    Both prices sit on the float grid deliberately: 18.81 under a peak of 20.9 divides out to
    exactly ten, where 21.0 has no price ten percent below it that arithmetic can reach.
    """

    def test_a_readable_top_exactly_at_the_distance_is_not_the_first_non_contesting_one(self) -> None:
        from scripts.minervini.power_play import measure_power_play
        from scripts.minervini.power_play_evidence import compile_power_play_spec

        history = power_play_series(advance_pct=88.1, later_high=20.9)
        spec = compile_power_play_spec()
        top = measure_power_play(history, spec)
        under = measure_power_play(history, spec, below=top["peak_high"], before=top["peak_date"])
        self.assertEqual((top["peak_high"] - under["peak_high"]) / top["peak_high"] * 100, 10.0)

        evidence = build_power_play_evidence(history)

        self.assertEqual(evidence["readings"], 2)
        self.assertIsNone(evidence["first_non_contesting_reading"])


if __name__ == "__main__":
    unittest.main()


class HowFarBelowTheUnreadTopStandsDecidesWhetherItBlocks(unittest.TestCase):
    """A top nobody read blocks a qualification only where it could have contested one.

    The chain already treats the two directions differently on purpose: objecting to a rejection
    survives the candidate distance, because a structure the chain walked past is still a reading
    under which nothing decisive failed. Contesting does not -- a top far below the highest is a
    different structure the stock has since overtaken, and letting it dispute a limit would leave
    every criterion permanently open.

    Which matters most for the stock this exception was written about. A Power Play is what a
    recent listing does, and a recent listing is exactly the history that ends before its own
    lower tops -- so a blanket block would have closed the capability's central case forever, on a
    top that could never have had a vote.
    """

    def test_the_measurement_still_names_the_top_it_could_not_read(self) -> None:
        """Thrown away, the distance is unknowable and every unread top has to block."""
        from scripts.minervini.power_play import measure_power_play
        from scripts.minervini.power_play_evidence import compile_power_play_spec

        frame = a_top_the_history_ends_before_series()
        spec = compile_power_play_spec()
        peak = measure_power_play(frame, spec)
        unread = measure_power_play(frame, spec, below=peak["peak_high"], before=peak["peak_date"])

        self.assertIsNotNone(unread["rejection"])
        self.assertIsNotNone(unread["peak_high"])
        self.assertLess(unread["peak_high"], peak["peak_high"])

    def test_the_top_it_could_not_read_is_reported_with_its_distance(self) -> None:
        """A boundary a verdict was decided next to has to be one a reader can audit.

        The first top past the candidate distance is reported that way already. This one decides
        whether an unread top withholds the qualification, so it is owed the same.
        """
        near = build_power_play_evidence(a_top_the_history_ends_before_series())
        far = build_power_play_evidence(a_top_the_history_ends_before_series(unread_top_price=15.0))

        self.assertAlmostEqual(near["unread_top"]["distance_pct"], 4.2857, places=3)
        self.assertTrue(near["unread_top_may_contest"])
        self.assertAlmostEqual(far["unread_top"]["distance_pct"], 28.5714, places=3)
        self.assertFalse(far["unread_top_may_contest"])

    def test_a_top_exactly_at_the_distance_still_contests(self) -> None:
        """The boundary itself, which nothing else here stands on.

        The registered figure is where a top stops being a candidate, so a top standing exactly
        that far below is the last one that is still one. Both prices are chosen to put the
        distance on the float grid: 18.81 under a peak of 20.9 divides out to exactly ten, where
        the default peak of 21.0 has no price ten percent below it that arithmetic can reach.
        """
        history = a_top_the_history_ends_before_series(advance_pct=109.0, unread_top_price=18.81)
        evidence = build_power_play_evidence(history)

        self.assertEqual(evidence["unread_top"]["peak_high"], 18.81)
        self.assertEqual(evidence["unread_top"]["distance_pct"], 10.0)
        self.assertTrue(evidence["unread_top_may_contest"])
        self.assertIn("lower_top_left_unread", evaluate_power_play(answered(history))["missing"])

    def test_a_top_too_far_below_to_contest_does_not_block(self) -> None:
        history = a_top_the_history_ends_before_series(unread_top_price=15.0)
        evidence = answered(history)

        self.assertTrue(evidence["readings_ran_out_of_history"])
        self.assertNotIn("lower_top_left_unread", evaluate_power_play(evidence)["missing"])
        self.assertEqual(evaluate_power_play(evidence)["power_play_state"], "qualified")

    def test_a_top_close_enough_to_contest_still_does(self) -> None:
        evidence = answered(a_top_the_history_ends_before_series())

        self.assertIn("lower_top_left_unread", evaluate_power_play(evidence)["missing"])
