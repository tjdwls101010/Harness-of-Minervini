"""The chart question and its answer, across the capability boundary.

Everything the unit seam decides is only reachable if the key travels out in the envelope and the
answer travels back in through a declared field. And one thing only the boundary can get wrong:
an answer that no longer matches has to arrive as a refusal, not as an unchanged verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.minervini.contracts import RequestError
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.setup_structure import bars_fingerprint
from tests.series import power_play_series, two_tops_that_both_await_the_chart_series


def run(frame, **overrides) -> dict:
    if "chart_readings" in overrides and "drawn_bars" not in overrides:
        overrides["drawn_bars"] = bars_fingerprint(frame)
    prices = ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            as_of=frame.index[-1].date(),
            coverage={"completed_only": True, "corporate_actions": True, "distributions": True},
        ),
    )
    request = {
        "ticker": "TEST",
        "as_of": prices.meta.as_of.isoformat(),
        "no_cache": True,
        **overrides,
    }
    return execute(
        "ticker.power-play",
        request,
        runtime=Runtime(price_history=lambda ticker, requested: prices),
    )


class TheQuestionLeavesAndTheAnswerReturns(unittest.TestCase):
    def test_the_envelope_names_the_questions_it_is_waiting_on(self) -> None:
        payload = run(power_play_series())

        conditions = {question["condition"] for question in payload["data"]["chart_questions"]}
        self.assertEqual(conditions, {"launch_volume_character", "flag_tightness_or_vcp"})
        self.assertIn("ticker.chart", payload["next_capabilities"])

    def test_answering_them_reaches_qualified_and_reports_it_as_a_complete_answer(self) -> None:
        """`partial` describes a contract with a gap in it, and this one no longer has any.

        The state is the investment verdict and the status is whether the evidence contract was
        satisfied; a qualified Power Play reported as `partial` tells a reader to go looking for
        the missing piece.
        """
        frame = power_play_series()
        keys = [f'{q["key"]}=observed' for q in run(frame)["data"]["chart_questions"]]
        payload = run(frame, chart_readings=keys)

        self.assertEqual(payload["data"]["power_play_state"], "qualified")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["missing"], [])
        self.assertIn("convention.power_play_chart_reading", payload["doctrine_ids"])

    def test_a_stale_answer_is_refused_by_name(self) -> None:
        """Stale here means the key, not the picture: the caller named this run's own bars."""
        with self.assertRaises(RequestError) as caught:
            run(power_play_series(), chart_readings=["0000000000000000=observed"])

        self.assertIn("0000000000000000", str(caught.exception))

    def test_a_word_the_seam_does_not_act_on_is_refused(self) -> None:
        """Including the one the tactic seam takes. Two words here, and a third that silently did
        nothing would leave a caller reading a gap they believe they filled."""
        for word in ("unclear", "probably", ""):
            with self.subTest(word=word), self.assertRaises(RequestError):
                run(power_play_series(), chart_readings=[f"aaaaaaaaaaaaaaaa={word}"])

    def test_a_line_missing_either_half_is_refused(self) -> None:
        for line in ("aaaaaaaaaaaaaaaa", "=observed"):
            with self.subTest(line=line), self.assertRaises(RequestError):
                run(power_play_series(), chart_readings=[line])

    def test_the_same_key_answered_twice_is_a_contradiction(self) -> None:
        with self.assertRaises(RequestError):
            run(
                power_play_series(),
                chart_readings=["aaaaaaaaaaaaaaaa=observed", "aaaaaaaaaaaaaaaa=absent"],
            )

    def test_the_answer_travels_back_out_beside_the_question(self) -> None:
        """So a reader of the envelope alone can see which answers this verdict rests on."""
        frame = two_tops_that_both_await_the_chart_series()
        questions = run(frame)["data"]["chart_questions"]
        first = questions[0]["key"]
        payload = run(frame, chart_readings=[f"{first}=observed"])

        answered = {q["key"]: q["answered"] for q in payload["data"]["chart_questions"]}
        self.assertEqual(answered[first], "observed")
        self.assertIsNone(answered[questions[1]["key"]])


class ARejectedStructureAsksNothing(unittest.TestCase):
    def test_the_gap_it_reports_does_not_send_the_reader_to_a_chart(self) -> None:
        """The reason a reader acts on has to be the reason it actually stopped.

        A criterion reported as waiting on a chart, with no key anywhere in the envelope that
        would answer it, sends the reader to draw a picture and come back with nothing to do.
        """
        payload = run(power_play_series(flag_depth_pct=40.0))
        reasons = {item["id"]: item["reason"] for item in payload["missing"]}

        self.assertEqual(payload["data"]["power_play_state"], "not_qualified")
        self.assertEqual(payload["data"]["chart_questions"], [])
        self.assertEqual(
            reasons["fundamentals.power_play_exception.flag_tightness_or_vcp"],
            "structure_is_already_rejected",
        )
        self.assertEqual(payload["next_capabilities"], [])


class AGapOnARejectedStructureIsNotAnInstruction(unittest.TestCase):
    """`required` and the reason both say what is left to do, so on a finished answer both stop.

    A rejected structure still carries criteria nobody satisfied -- that is what rejection looks
    like from the inside. Reporting them as required evidence waiting on a chart tells a reader to
    go and close something that no longer decides anything, and contradicts the `ok` status one
    line up.
    """

    def test_a_reader_s_own_absent_reading_closes_the_rest_of_the_questions(self) -> None:
        frame = power_play_series()
        volume = next(
            q for q in run(frame)["data"]["chart_questions"]
            if q["condition"] == "launch_volume_character"
        )
        payload = run(frame, chart_readings=[f'{volume["key"]}=absent'])

        self.assertEqual(payload["data"]["power_play_state"], "not_qualified")
        gaps = {item["id"].split(".")[-1]: item for item in payload["missing"]}
        tightness = gaps["flag_tightness_or_vcp"]
        self.assertEqual(tightness["reason"], "structure_is_already_rejected")
        self.assertFalse(tightness["required"])
        self.assertEqual(payload["next_capabilities"], [])

    def test_a_question_already_answered_is_not_reported_as_still_waiting(self) -> None:
        """Otherwise the envelope asks forever: the key it names comes back already answered."""
        frame = power_play_series()
        keys = [f'{q["key"]}=observed' for q in run(frame)["data"]["chart_questions"]]
        payload = run(frame, chart_readings=keys)

        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["next_capabilities"], [])


class AFinishedAnswerCarriesItsEvidenceAndAsksNothing(unittest.TestCase):
    """Both halves, because dropping either one is a different lie.

    Kept whole, a terminal envelope prints a key nobody can act on under a status that says
    nothing is outstanding. Emptied, the reader cannot see which answers the verdict rests on --
    and one of the two criteria here was settled by a person, which is the thing an auditor of a
    Power Play most needs to find.
    """

    def _rejected(self):
        frame = power_play_series()
        volume = next(
            q for q in run(frame)["data"]["chart_questions"]
            if q["condition"] == "launch_volume_character"
        )
        return run(frame, chart_readings=[f'{volume["key"]}=absent'])

    def test_the_answer_it_rests_on_is_still_there(self) -> None:
        payload = self._rejected()

        answered = [q for q in payload["data"]["chart_questions"] if q["answered"] is not None]
        self.assertEqual([q["condition"] for q in answered], ["launch_volume_character"])
        self.assertEqual(answered[0]["answered"], "absent")

    def test_and_nothing_it_no_longer_wants(self) -> None:
        payload = self._rejected()

        self.assertEqual(payload["data"]["power_play_state"], "not_qualified")
        self.assertEqual([q for q in payload["data"]["chart_questions"] if q["answered"] is None], [])

    def test_a_question_answered_under_one_top_does_not_answer_for_another(self) -> None:
        """`awaited` counts unanswered questions, and both tops ask this criterion separately.

        Counted by condition alone it goes quiet as soon as any top is answered; counted by
        answer alone it never goes quiet at all. The envelope has to keep asking until the top
        that may contest it has been read, and stop the moment it has.
        """
        frame = two_tops_that_both_await_the_chart_series()
        questions = run(frame)["data"]["chart_questions"]
        self.assertEqual(len(questions), 2)

        half = run(frame, chart_readings=[f'{questions[0]["key"]}=observed'])
        self.assertEqual(
            {item["reason"] for item in half["missing"]}, {"chart_unread_under_another_top"}
        )
        self.assertIn("ticker.chart", half["next_capabilities"])

        whole = run(frame, chart_readings=[f'{q["key"]}=observed' for q in questions])
        self.assertEqual(whole["missing"], [])
        self.assertEqual(whole["next_capabilities"], [])


class AChartAlreadyReadIsNotAChartStillWaited0n(unittest.TestCase):
    """The gap where an answered question and no question at all look identical.

    The highest top is out on the depth gate, so it was issued no key. The top beneath it survives
    and asks both questions, and once those are answered nothing anywhere is still waiting on a
    reader -- but the highest top's own criteria are still unsatisfied, because its reading is the
    one the verdict is reported from.

    Counting a question that has been answered as one still outstanding tells the reader to go and
    read a chart they have already read, and the envelope says it again on the next run.
    """

    def _payload(self, answers=()):
        frame = two_tops_that_both_await_the_chart_series(flag_low=79.0)
        questions = run(frame)["data"]["chart_questions"]
        self.assertEqual({q["reading"] for q in questions}, {1})
        chosen = [f'{q["key"]}=observed' for q in questions if q["condition"] in answers]
        return run(frame, chart_readings=chosen) if chosen else run(frame)

    def test_while_the_lower_top_is_unread_the_chart_is_what_it_waits_on(self) -> None:
        payload = self._payload()

        reasons = {item["id"].split(".")[-1]: item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons["launch_volume_character"], "chart_reading_required")
        self.assertIn("ticker.chart", payload["next_capabilities"])

    def test_once_it_is_read_the_gap_stops_naming_a_chart(self) -> None:
        payload = self._payload(("launch_volume_character", "flag_tightness_or_vcp"))

        reasons = {item["id"].split(".")[-1]: item["reason"] for item in payload["missing"]}
        self.assertEqual(
            reasons["launch_volume_character"], "reading_rejected_before_a_chart_was_needed"
        )
        self.assertEqual(payload["next_capabilities"], [])


if __name__ == "__main__":
    unittest.main()
