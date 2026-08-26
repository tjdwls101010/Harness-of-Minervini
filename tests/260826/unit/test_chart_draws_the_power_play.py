"""The Power Play approval asks a person about a structure the picture never drew.

`ticker power-play` cannot qualify a stock on the volume clause by itself -- the source says
"an explosive price move commences on huge volume" and gives no number, so the capability
measures three readings, hands back a chart question and waits. The chart it sends the reader
to drew candles, moving averages and the VCP detector's swing anchors, and nothing at all
about the Power Play: not the advance it is asking about, not the peak that advance ended on,
not the baseline the volume ratio was divided by, and not the session that ratio belongs to.

So the reader was being asked whether a session's volume was huge while looking at a picture
that never said which session. That is the same formality the swing anchors were drawn to
avoid, on the one path where the harness genuinely cannot decide without a person.

What the chart owes this question is the span the numbers were read from. The measurement
already carries every landmark with its date, so nothing here is recomputed or guessed at.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.minervini.chart import _draw_power_play, _power_play_spans, render_chart_artifacts
from scripts.minervini.power_play import measure_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence, compile_power_play_spec
from tests.series import base_series, power_play_series, two_tops_that_both_await_the_chart_series


def _rendered(frame, directory):
    return render_chart_artifacts(
        frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
    )


class TheChartCarriesTheStructureItAsksAbout(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = power_play_series()
        self.questions = [
            question for question in build_power_play_evidence(self.frame)["chart_questions"]
            if question.get("answered") is None
        ]

    def test_the_fixture_really_has_the_capability_asking(self) -> None:
        self.assertTrue(self.questions)

    def test_the_manifest_carries_the_span_each_question_is_about(self) -> None:
        """Not a span the chart measured for itself -- the values are the question's own, so the
        two cannot drift into describing different tops with the same digest on both."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        drawn = {span["peak_date"]: span for span in manifest["power_play"]["spans"]}
        self.assertEqual(set(drawn), {question["peak_date"] for question in self.questions})
        for question in self.questions:
            span = drawn[question["peak_date"]]
            for landmark in ("advance_anchor_date", "flag_low_date", "advance_peak_volume_date",
                             "baseline_first_session", "baseline_last_session"):
                with self.subTest(peak=question["peak_date"], landmark=landmark):
                    self.assertEqual(span[landmark], question[landmark])

    def test_it_names_one_set_of_bars_with_everything_else_on_the_page(self) -> None:
        """An approval cites the digest, so a span measured from other bars than the picture
        was cut from is the same failure the segmentation digest exists to prevent."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        self.assertEqual(manifest["power_play"]["bars_fingerprint"], manifest["input_sha256"])
        self.assertEqual(manifest["power_play"]["bars_fingerprint"], self.questions[0]["drawn_bars"])

    def test_each_picture_reports_which_landmarks_it_actually_shows(self) -> None:
        """The same contract the anchors already keep: what the picture contains, not what was
        available to put in it. A weekly chart that does not reach a session cannot mark it."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        for artifact in manifest["artifacts"]:
            with self.subTest(timeframe=artifact["timeframe"]):
                self.assertIn("power_play_drawn", artifact)
                for question in self.questions:
                    self.assertIn(question["peak_date"], artifact["power_play_drawn"])
                    self.assertIn(question["advance_anchor_date"], artifact["power_play_drawn"])

    def test_the_session_the_volume_question_is_about_is_marked_on_the_volume_axis(self) -> None:
        """The clause is about one bar's volume, and the price panel is not where a reader
        judges that. Marking it anywhere else leaves the question exactly as unanswerable."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        for artifact in manifest["artifacts"]:
            with self.subTest(timeframe=artifact["timeframe"]):
                self.assertTrue(artifact["heaviest_advance_session_drawn"])

    def test_the_manifest_on_disk_carries_it_too(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)
            written = json.loads(Path(manifest["manifest_path"]).read_text(encoding="utf-8"))

        self.assertEqual(written["power_play"], manifest["power_play"])


class RecordingAxis:
    """Keeps what was drawn on it and what each thing was called.

    The labels are the part under test here and a rendered PNG cannot be asked about them, so
    this is where the wording gets pinned."""

    def __init__(self) -> None:
        self.labels: list[str] = []
        self.spans: list[tuple] = []
        self.rules: list[Any] = []
        self.points: list[tuple] = []

    def plot(self, x, y, **kwargs) -> None:
        self.points.append((x[0], float(y[0])))
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def axvline(self, position, **kwargs) -> None:
        self.rules.append(position)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def axvspan(self, start, end, **kwargs) -> None:
        self.spans.append((start, end))
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def legend(self, *_args, **_kwargs) -> None:
        return None


class TheRatioBelongsToTheTimeframeItWasMeasuredOn(unittest.TestCase):
    """A weekly volume bar is five sessions added together.

    The clause divides one session's volume by a session baseline, so printing "6.0x" beside a
    weekly bar asks the reader to check that arithmetic against bars it was never computed
    from -- and on this fixture the weeks after it are three times taller, so the picture
    argues against its own number. The week still gets marked: the weekly is read first, and
    which week holds the event is what sends a reader to the right place on the daily.
    """

    def setUp(self) -> None:
        self.frame = power_play_series()
        self.span = _power_play_spans(self.frame, "irrelevant-digest")
        self.weekly = (
            self.frame.resample("W-FRI")
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna()
        )

    def test_the_daily_panel_prints_the_ratio(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        self.assertIn("heaviest advance session (6.0x baseline)", volume.labels)

    def test_the_weekly_panel_marks_the_week_without_one(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        drawn, marked = _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        self.assertTrue(marked)
        self.assertIn("week of the heaviest advance session", volume.labels)
        self.assertFalse([label for label in volume.labels if "x baseline" in label])

    def test_both_panels_name_each_landmark_rather_than_the_structure(self) -> None:
        """One shared "power play" entry leaves a reader looking at a star and a cross with
        nothing saying which is the top of the advance and which is the bottom of the flag."""
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        self.assertEqual(price.labels, ["advance begins", "advance peak", "flag low"])
        self.assertIn("baseline volume", volume.labels)

    def test_the_advance_start_is_a_rule_down_the_panel_not_a_dot_at_a_price(self) -> None:
        """It was a marker at the bar's low, and on AAOI's three years of history at $0-230 it
        could not be seen at all -- the one landmark the volume clause is a claim about."""
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        self.assertEqual(len(price.rules), 1)


class AStockNobodyIsAskingAbout(unittest.TestCase):
    """Drawing is not the same as claiming.

    The arithmetic succeeds on any history: an ordinary base has a highest bar, a first bar of
    its rise and a quiet window before it. An earlier version drew whenever it liked the look
    of those, and put a Power Play span on charts the capability had asked nothing about --
    AAOI, OCC, HPE and MRNA all drew while every one of them was `not_qualified` with no
    question outstanding. Now the questions are the only reason to draw, so there is nothing
    left to disagree with.
    """

    def setUp(self) -> None:
        self.frame, _ = base_series()
        self.measured = measure_power_play(self.frame, compile_power_play_spec())

    def test_the_measurement_succeeds_which_is_exactly_the_trap(self) -> None:
        """`rejection` says the arithmetic ran, not that a Power Play exists. This base rises
        fifteen percent over seven weeks and comes back with a peak, an anchor and a baseline
        like any other history."""
        self.assertIsNone(self.measured["rejection"])
        self.assertLess(self.measured["advance_pct"], 100)
        self.assertIsNotNone(self.measured["peak_date"])

    def test_but_the_capability_asks_nothing_about_it(self) -> None:
        open_questions = [
            question for question in build_power_play_evidence(self.frame)["chart_questions"]
            if question.get("answered") is None
        ]

        self.assertEqual(open_questions, [])

    def test_so_nothing_is_drawn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        self.assertEqual(manifest["power_play"]["spans"], [])
        for artifact in manifest["artifacts"]:
            with self.subTest(timeframe=artifact["timeframe"]):
                self.assertEqual(artifact["power_play_drawn"], [])
                self.assertFalse(artifact["heaviest_advance_session_drawn"])


class EveryTopTheCapabilityIsAskingAbout(unittest.TestCase):
    """A chain of candidate tops is asked about one at a time, and the chart drew only the
    highest.

    So a reader sent to answer about the second top saw the first one, with the same digest on
    the picture -- which meant the seam accepted an answer read off a structure the question
    was not about. That is a worse failure than drawing nothing: the reader has no way to know
    they are looking at the wrong top, and the harness has no way to notice either.
    """

    def setUp(self) -> None:
        self.frame = two_tops_that_both_await_the_chart_series()
        self.questions = [
            question for question in build_power_play_evidence(self.frame)["chart_questions"]
            if question.get("answered") is None
        ]

    def test_the_fixture_really_asks_about_more_than_one_top(self) -> None:
        self.assertGreater(len({question["peak_date"] for question in self.questions}), 1)

    def test_every_one_of_those_tops_is_on_the_picture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        asked = {question["peak_date"] for question in self.questions}
        self.assertEqual(set(manifest["power_play"]["asked_about"]), asked)
        for artifact in manifest["artifacts"]:
            with self.subTest(timeframe=artifact["timeframe"]):
                self.assertTrue(asked.issubset(set(artifact["power_play_drawn"])))

    def test_a_top_asked_two_things_is_still_drawn_once(self) -> None:
        """The volume clause and the flag's tightness are two questions about one picture, and
        drawing it twice stacks the markers and doubles the legend without adding a landmark."""
        spans = _power_play_spans(self.frame, "digest")["spans"]

        self.assertEqual(len(spans), len({span["peak_date"] for span in spans}))


class TheMarkerLandsOnTheBarItNames(unittest.TestCase):
    """A reviewer moved the heaviest-volume marker onto the advance anchor and every test here
    still passed, because they all asked whether something was drawn and never where."""

    def setUp(self) -> None:
        self.frame = power_play_series()
        self.span = _power_play_spans(self.frame, "digest")["spans"][0]

    def test_the_volume_marker_sits_on_the_session_the_ratio_belongs_to(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, {"spans": [self.span]}, "daily")

        expected = pd.Timestamp(self.span["advance_peak_volume_date"])
        self.assertEqual([point[0] for point in volume.points], [expected])
        self.assertEqual(volume.points[0][1], float(self.frame.loc[expected, "Volume"]))

    def test_the_peak_and_the_flag_low_sit_on_their_own_bars_at_their_own_prices(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, {"spans": [self.span]}, "daily")

        self.assertEqual(
            price.points,
            [
                (pd.Timestamp(self.span["peak_date"]), float(self.span["peak_high"])),
                (pd.Timestamp(self.span["flag_low_date"]), float(self.span["flag_low"])),
            ],
        )

    def test_the_advance_rule_stands_on_the_anchor_session(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, {"spans": [self.span]}, "daily")

        self.assertEqual(price.rules, [pd.Timestamp(self.span["advance_anchor_date"])])


if __name__ == "__main__":
    unittest.main()
