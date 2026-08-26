"""The reader has to have looked at the bars the answer is applied to.

The key binds an answer to the bars this capability measured. What it cannot do is attest that the
picture the reader looked at came from those bars -- the harness never sees their screen, and the
two capabilities involved reach the provider separately, so the chart can be drawn from a vintage
the verdict was not measured on. Answered anyway, the eyes corroborated one series and the machine
qualified another.

So the answer names the bars it was read from, the same way a setup approval names the bars its
chain was approved from, and the two capabilities report that digest in the same form.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pathlib
import tempfile
import unittest

from scripts.minervini.cache import ProviderCache
from scripts.minervini.contracts import RequestError
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.power_play_evidence import power_play_fingerprint
from scripts.minervini.setup_structure import bars_fingerprint
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


class TheAnswerNamesThePictureItCameFrom(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = power_play_series()
        self.runtime = Runtime(price_history=lambda ticker, requested: snapshot(self.frame))
        self.request = {
            "ticker": "TEST",
            "as_of": self.frame.index[-1].date().isoformat(),
            "no_cache": True,
        }

    def _questions(self):
        return execute("ticker.power-play", self.request, runtime=self.runtime)["data"]["chart_questions"]

    def test_the_question_names_the_digest_the_chart_reports(self) -> None:
        """One string to compare, in the form ticker.chart prints it."""
        question = self._questions()[0]

        self.assertEqual(question["drawn_bars"], bars_fingerprint(self.frame))

    def test_an_answer_with_no_picture_named_is_refused(self) -> None:
        keys = [f'{q["key"]}=observed' for q in self._questions()]

        with self.assertRaises(RequestError) as caught:
            execute("ticker.power-play", {**self.request, "chart_readings": keys}, runtime=self.runtime)

        self.assertIn("drawn_bars", str(caught.exception))

    def test_naming_the_right_picture_lets_the_answer_through(self) -> None:
        keys = [f'{q["key"]}=observed' for q in self._questions()]
        payload = execute(
            "ticker.power-play",
            {**self.request, "chart_readings": keys, "drawn_bars": bars_fingerprint(self.frame),
             "measured_bars": power_play_fingerprint(self.frame)},
            runtime=self.runtime,
        )

        self.assertEqual(payload["data"]["power_play_state"], "qualified")

    def test_a_chart_drawn_from_another_vintage_closes_nothing(self) -> None:
        """The one the two capabilities can actually disagree about.

        Not refused: the caller answered honestly about a picture that existed. What they read it
        from is not what this verdict is measured on, so the criteria stay open and the envelope
        says so under the same name a setup approval of the wrong vintage gets.
        """
        keys = [f'{q["key"]}=observed' for q in self._questions()]
        payload = execute(
            "ticker.power-play",
            {**self.request, "chart_readings": keys, "drawn_bars": bars_fingerprint(power_play_series(flag_sessions=18)),
             "measured_bars": power_play_fingerprint(self.frame)},
            runtime=self.runtime,
        )

        self.assertEqual(payload["data"]["power_play_state"], "incomplete")
        reasons = {item["reason"] for item in payload["missing"]}
        self.assertEqual(reasons, {"approval_covers_different_bars"})
        self.assertEqual(payload["data"]["measured_from"], bars_fingerprint(self.frame))
        # The questions stay, unanswered. Removed, the reader is told their picture was the wrong
        # series and left with nothing naming what to read from the right one.
        self.assertEqual(
            [q["answered"] for q in payload["data"]["chart_questions"]], [None, None]
        )


class TheOverlayHasItsOwnInput(unittest.TestCase):
    """Naming the picture is not the same as naming the overlay drawn on it.

    `drawn_bars` covers the five price columns, which identifies the candles. This capability
    does not read the span from prices alone -- a split inside it leaves the structure deciding
    nothing, a payout withholds the criteria it decided -- so two histories with identical prices
    and different events issue different questions. Reproduced: the capability asked two, the
    chart drew no span at all, and `input_sha256` matched on both. The reader answered off a
    blank picture and the answer was accepted straight through to `qualified`.

    So the overlay names its own input too, under the word the question already prints it under.
    """

    def setUp(self) -> None:
        self.frame = power_play_series()
        # Same five price columns, a different corporate-action history.
        self.split = self.frame.copy()
        self.split.loc[self.split.index[-30], "Stock Splits"] = 2.0
        self.runtime = Runtime(price_history=lambda ticker, requested: snapshot(self.frame))
        self.request = {
            "ticker": "TEST",
            "as_of": self.frame.index[-1].date().isoformat(),
            "no_cache": True,
        }

    def _readings(self):
        payload = execute("ticker.power-play", self.request, runtime=self.runtime)
        return [f'{q["key"]}=observed' for q in payload["data"]["chart_questions"]]

    def test_the_fixture_really_separates_the_two_digests(self) -> None:
        self.assertEqual(bars_fingerprint(self.frame), bars_fingerprint(self.split))
        self.assertNotEqual(power_play_fingerprint(self.frame), power_play_fingerprint(self.split))

    def test_an_answer_that_names_no_overlay_is_refused(self) -> None:
        with self.assertRaises(RequestError) as caught:
            execute(
                "ticker.power-play",
                {
                    **self.request,
                    "chart_readings": self._readings(),
                    "drawn_bars": bars_fingerprint(self.frame),
                },
                runtime=self.runtime,
            )

        self.assertIn("measured_bars", str(caught.exception))

    def test_an_overlay_from_another_events_vintage_closes_nothing(self) -> None:
        """The digest that used to match on both sides of the failure."""
        payload = execute(
            "ticker.power-play",
            {
                **self.request,
                "chart_readings": self._readings(),
                "drawn_bars": bars_fingerprint(self.frame),
                "measured_bars": power_play_fingerprint(self.split),
            },
            runtime=self.runtime,
        )

        self.assertEqual(payload["data"]["power_play_state"], "incomplete")
        self.assertEqual({item["reason"] for item in payload["missing"]}, {"approval_covers_different_bars"})
        self.assertEqual(payload["data"]["measured_bars"], power_play_fingerprint(self.frame))
        self.assertEqual([q["answered"] for q in payload["data"]["chart_questions"]], [None, None])

    def test_naming_both_lets_the_answer_through(self) -> None:
        payload = execute(
            "ticker.power-play",
            {
                **self.request,
                "chart_readings": self._readings(),
                "drawn_bars": bars_fingerprint(self.frame),
                "measured_bars": power_play_fingerprint(self.frame),
            },
            runtime=self.runtime,
        )

        self.assertEqual(payload["data"]["power_play_state"], "qualified")

    def test_a_value_that_is_not_a_fingerprint_is_refused(self) -> None:
        for value in ("not-a-sha256", "abc", power_play_fingerprint(self.frame).upper()):
            with self.subTest(value=value), self.assertRaises(RequestError):
                execute(
                    "ticker.power-play",
                    {
                        **self.request,
                        "chart_readings": ["a=observed"],
                        "drawn_bars": bars_fingerprint(self.frame),
                        "measured_bars": value,
                    },
                    runtime=self.runtime,
                )


class TheTwoCapabilitiesCanReachDifferentBars(unittest.TestCase):
    def test_the_skew_is_real_and_the_digest_is_what_catches_it(self) -> None:
        """A regression guard on the reason the digest is asked for at all.

        The provider cache is namespaced per capability, so ticker.power-play and ticker.chart
        hold their own entry for the same ticker and session and can be populated from different
        fetches. Without the digest, the reader draws one series and answers about another.
        """
        old, new = power_play_series(), power_play_series(advance_volume_multiple=1.05)
        self.assertNotEqual(bars_fingerprint(old), bars_fingerprint(new))
        served: list[int] = []

        def history(ticker, requested):
            frame = old if not served else new
            served.append(1)
            return snapshot(frame)

        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(price_history=history, cache=ProviderCache(pathlib.Path(directory)))
            request = {"ticker": "TEST", "as_of": old.index[-1].date().isoformat()}
            questions = execute("ticker.power-play", request, runtime=runtime)["data"]["chart_questions"]
            chart = execute("ticker.chart", {**request, "output_dir": directory}, runtime=runtime)

            self.assertNotEqual(chart["data"]["input_sha256"], questions[0]["drawn_bars"])
            payload = execute(
                "ticker.power-play",
                {
                    **request,
                    "chart_readings": [f'{q["key"]}=observed' for q in questions],
                    "drawn_bars": chart["data"]["input_sha256"],
                    "measured_bars": chart["data"]["power_play"]["measured_bars"],
                },
                runtime=runtime,
            )

        self.assertEqual(payload["data"]["power_play_state"], "incomplete")
        self.assertEqual(
            {item["reason"] for item in payload["missing"]}, {"approval_covers_different_bars"}
        )



class ADigestIsWhatIsAskedFor(unittest.TestCase):
    """Any non-empty string used to count, so a typo arrived as a reading of another vintage.

    Which is the wrong kind of answer entirely: a malformed value is a bad request, and reporting
    it as a finding about the stock sends the reader to redraw a chart that was never the problem.
    """

    def setUp(self) -> None:
        self.frame = power_play_series()
        self.runtime = Runtime(price_history=lambda ticker, requested: snapshot(self.frame))
        self.request = {
            "ticker": "TEST",
            "as_of": self.frame.index[-1].date().isoformat(),
            "no_cache": True,
        }

    def test_a_value_that_is_not_a_fingerprint_is_refused(self) -> None:
        for value in ("not-a-sha256", "abc", bars_fingerprint(self.frame)[:32], bars_fingerprint(self.frame).upper()):
            with self.subTest(value=value), self.assertRaises(RequestError):
                execute(
                    "ticker.power-play",
                    {**self.request, "chart_readings": ["a=observed"], "drawn_bars": value,
                     "measured_bars": power_play_fingerprint(self.frame)},
                    runtime=self.runtime,
                )

    def test_it_is_checked_even_with_nothing_to_apply_it_to(self) -> None:
        """A caller who names a picture is making a claim about it whether or not they answered."""
        with self.assertRaises(RequestError):
            execute("ticker.power-play", {**self.request, "drawn_bars": "nope"}, runtime=self.runtime)

    def test_a_padded_digest_is_not_quietly_read_as_another_vintage(self) -> None:
        """The check strips; the comparison downstream did not.

        A trailing newline is what a shell pipeline hands you, and it passed validation and then
        missed the digest it was checked against -- so a correct answer about the right picture
        came back as an honest reading of a series that never existed.
        """
        payload = execute(
            "ticker.power-play",
            {
                **self.request,
                "chart_readings": [
                    f'{q["key"]}=observed'
                    for q in execute("ticker.power-play", self.request, runtime=self.runtime)["data"][
                        "chart_questions"
                    ]
                ],
                "drawn_bars": f" {bars_fingerprint(self.frame)}\n",
                "measured_bars": f" {power_play_fingerprint(self.frame)}\n",
            },
            runtime=self.runtime,
        )

        self.assertEqual(payload["data"]["power_play_state"], "qualified")


class ARejectionIsNotWaitingOnAPicture(unittest.TestCase):
    def test_a_finished_rejection_keeps_its_own_reason_whatever_vintage_arrives(self) -> None:
        """The vintage is only ever a reason for a criterion a chart could still close.

        Read the other way round, a structure the bars already rejected reported every criterion
        as `approval_covers_different_bars`, which sends a reader to redraw a chart for a verdict
        that is finished -- the same mistake as reporting a still-forming flag under the chart's
        name, one layer further out.
        """
        frame = power_play_series(advance_pct=40.0)
        runtime = Runtime(price_history=lambda ticker, requested: snapshot(frame))
        payload = execute(
            "ticker.power-play",
            {
                "ticker": "TEST",
                "as_of": frame.index[-1].date().isoformat(),
                "no_cache": True,
                "chart_readings": ["some-key-this-run-never-issued=observed"],
                "drawn_bars": bars_fingerprint(power_play_series(flag_sessions=18)),
                "measured_bars": power_play_fingerprint(frame),
            },
            runtime=runtime,
        )

        self.assertEqual(payload["data"]["power_play_state"], "not_qualified")
        self.assertEqual(
            {item["reason"] for item in payload["missing"]}, {"structure_is_already_rejected"}
        )

class BeingToldToRedrawSendsYouSomewhere(unittest.TestCase):
    def test_a_wrong_vintage_still_points_at_the_capability_that_draws_one(self) -> None:
        """The gap closes by reading the right picture, so the envelope names where to get it.

        Every other gap a chart closes points at ticker.chart. This one is the same errand and was
        the one case that pointed nowhere -- the reader is told their picture was the wrong series
        and left to work out that a picture is still what they need.
        """
        frame = power_play_series()
        runtime = Runtime(price_history=lambda ticker, requested: snapshot(frame))
        request = {"ticker": "TEST", "as_of": frame.index[-1].date().isoformat(), "no_cache": True}
        questions = execute("ticker.power-play", request, runtime=runtime)["data"]["chart_questions"]
        payload = execute(
            "ticker.power-play",
            {
                **request,
                "chart_readings": [f'{q["key"]}=observed' for q in questions],
                "drawn_bars": bars_fingerprint(power_play_series(flag_sessions=18)),
                "measured_bars": power_play_fingerprint(frame),
            },
            runtime=runtime,
        )

        self.assertIn("ticker.chart", payload["next_capabilities"])


if __name__ == "__main__":
    unittest.main()
