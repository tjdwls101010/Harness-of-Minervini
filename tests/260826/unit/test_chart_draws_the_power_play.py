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
from scripts.minervini.power_play_evidence import (
    build_power_play_evidence,
    compile_power_play_spec,
    power_play_fingerprint,
)
from scripts.minervini.setup_structure import bars_fingerprint
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

        self.assertEqual(manifest["power_play"]["drawn_bars"], manifest["input_sha256"])
        self.assertEqual(manifest["power_play"]["drawn_bars"], self.questions[0]["drawn_bars"])

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


class TheOverlayNamesTheBarsItWasComputedFrom(unittest.TestCase):
    """The price-only digest cannot see the input this overlay turns on.

    `input_sha256` covers the five price columns, which is the right identity for candles and
    swing anchors. The Power Play span is not read from prices alone: a split inside it leaves
    the structure deciding nothing and a payout withholds the criteria it decided, so two
    histories with identical prices and different events produce different questions -- and
    produced, on one reproduction, two questions from the capability and no span at all on a
    chart whose digest matched. The reader answered about a blank picture and the answer was
    accepted.

    So the overlay names its own input, in the same word and the same form the question does.
    """

    def setUp(self) -> None:
        self.frame = power_play_series()
        self.split = self.frame.copy()
        self.split.loc[self.split.index[-30], "Stock Splits"] = 2.0

    def _manifest(self, frame):
        with tempfile.TemporaryDirectory() as directory:
            return _rendered(frame, directory)

    def test_the_two_frames_are_the_same_bars_and_not_the_same_input(self) -> None:
        self.assertEqual(bars_fingerprint(self.frame), bars_fingerprint(self.split))
        self.assertNotEqual(
            power_play_fingerprint(self.frame), power_play_fingerprint(self.split)
        )

    def test_the_block_names_both_digests_under_the_words_the_question_uses(self) -> None:
        manifest = self._manifest(self.frame)
        question = next(
            q for q in build_power_play_evidence(self.frame)["chart_questions"]
            if q.get("answered") is None
        )

        self.assertEqual(manifest["power_play"]["drawn_bars"], question["drawn_bars"])
        self.assertEqual(manifest["power_play"]["measured_bars"], question["measured_bars"])

    def test_the_split_moves_the_overlay_digest_where_it_cannot_move_the_other(self) -> None:
        """The whole failure in one assertion: same picture identity, different overlay."""
        plain, split = self._manifest(self.frame), self._manifest(self.split)

        self.assertEqual(plain["input_sha256"], split["input_sha256"])
        self.assertEqual(plain["power_play"]["drawn_bars"], split["power_play"]["drawn_bars"])
        self.assertNotEqual(
            plain["power_play"]["measured_bars"], split["power_play"]["measured_bars"]
        )

    def test_a_history_that_never_said_whether_a_split_occurred_names_nothing(self) -> None:
        """The same abstention the capability makes: absence is not a report of none."""
        bare = self.frame.drop(columns=["Stock Splits", "Dividends"])

        manifest = self._manifest(bare)

        self.assertIsNone(manifest["power_play"]["measured_bars"])
        self.assertEqual(manifest["power_play"]["spans"], [])


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


class TopsThatShareOneBar(unittest.TestCase):
    """Five tops in three weeks, and a weekly picture that can only show three.

    Landmarks were deduped by their raw date and only then mapped onto a bar, so five stars were
    drawn at three positions with five legend entries standing behind them. The legend is the
    only thing binding a mark to the question key it answers, and at that point it cannot: a
    reader counting stars against it is back to guessing which top they are looking at, which is
    the wrong-top approval the span was drawn to prevent -- on the surface that gets read first.

    One visible mark, one entry, and the entry names every reading that landed on it. The daily
    is unaffected, because a session there is its own bar.
    """

    def setUp(self) -> None:
        self.frame = power_play_series()
        self.weekly = (
            self.frame.resample("W-FRI")
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna()
        )
        base = _power_play_spans(self.frame, "digest")["spans"][0]
        # Three weeks: 04-17 alone, then 04-21 with 04-23, then 04-27 with 04-29.
        self.tops = ("2026-04-17", "2026-04-21", "2026-04-23", "2026-04-27", "2026-04-29")
        self.highs = (20.1, 20.2, 20.9, 20.4, 20.3)
        self.span = {"spans": [
            {**base, "reading": index, "peak_date": day, "peak_high": high}
            for index, (day, high) in enumerate(zip(self.tops, self.highs))
        ]}

    def test_the_weekly_picture_marks_each_bar_once(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        peaks = [label for label in price.labels if label.startswith("advance peak")]
        self.assertEqual(len(peaks), 3)
        self.assertEqual(len([point for point in price.points if point[1] > 19]), 3)

    def test_and_names_every_reading_that_landed_on_it(self) -> None:
        """A star a reader cannot name is a star they cannot answer from."""
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        named = " ".join(price.labels)
        for day in self.tops:
            with self.subTest(top=day):
                self.assertIn(day, named)

    def test_the_merged_mark_sits_at_the_highest_top_it_stands_for(self) -> None:
        """It is one bar's mark, so it goes where that bar's readings reached."""
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        self.assertIn(20.9, [point[1] for point in price.points])
        self.assertNotIn(20.2, [point[1] for point in price.points])

    def test_the_manifest_still_reports_all_five_because_all_five_are_named(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        drawn, _ = _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        self.assertTrue(set(self.tops).issubset(set(drawn)))

    def test_the_daily_picture_keeps_one_mark_per_session(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        peaks = [label for label in price.labels if label.startswith("advance peak")]
        self.assertEqual(len(peaks), 5)


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
