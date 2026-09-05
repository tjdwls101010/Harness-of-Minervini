"""Behavior checks for chart draws the power play."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
import pandas as pd
from scripts.minervini.chart import _draw_power_play, _power_play_spans
from scripts.minervini.power_play import measure_power_play
from scripts.minervini.power_play_evidence import build_power_play_evidence, compile_power_play_spec
from tests.series import base_series, power_play_series
from tests.unit.chart._chart_fixtures import _rendered
from tests.charts import RecordingAxis


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
                    self.assertIn(question["peak_date"], artifact["power_play_drawn"]["peak_date"])
                    self.assertIn(
                        question["advance_anchor_date"],
                        artifact["power_play_drawn"]["advance_anchor_date"],
                    )

    def test_the_session_the_volume_question_is_about_is_marked_on_the_volume_axis(self) -> None:
        """The clause is about one bar's volume, and the price panel is not where a reader
        judges that. Marking it anywhere else leaves the question exactly as unanswerable."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        for artifact in manifest["artifacts"]:
            with self.subTest(timeframe=artifact["timeframe"]):
                self.assertTrue(artifact["power_play_drawn"]["advance_peak_volume_date"])

    def test_the_manifest_on_disk_carries_it_too(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)
            written = json.loads(Path(manifest["manifest_path"]).read_text(encoding="utf-8"))

        self.assertEqual(written["power_play"], manifest["power_play"])


class AQuestionThatCannotNameEveryLandmark(unittest.TestCase):
    """A history ending on the peak has no flag low, and the picture cannot invent one.

    Reported as a flat list of the sessions that were marked, an absent flag low reads exactly
    like a session this timeframe does not reach -- the reader is looking for a cross that was
    never drawn, with nothing on the page or in the manifest telling them which it is. One list
    per landmark says it: the peak's list has the date, the flag low's is empty.
    """

    def setUp(self) -> None:
        self.frame = power_play_series().loc[:"2026-04-30"]
        self.question = next(
            question for question in build_power_play_evidence(self.frame)["chart_questions"]
            if question.get("answered") is None
        )

    def test_the_fixture_really_asks_about_a_span_with_a_hole_in_it(self) -> None:
        self.assertIsNone(self.question["flag_low_date"])
        self.assertIsNotNone(self.question["peak_date"])

    def test_the_manifest_says_which_landmark_is_not_on_the_picture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        for artifact in manifest["artifacts"]:
            with self.subTest(timeframe=artifact["timeframe"]):
                drawn = artifact["power_play_drawn"]
                self.assertEqual(drawn["flag_low_date"], [])
                self.assertEqual(drawn["peak_date"], [self.question["peak_date"]])


class ASpanTheQuestionCannotFullyName(unittest.TestCase):
    """A landmark the question stopped carrying is a mark the picture silently loses.

    Read with `.get`, it arrives as None, `_containing_bar` is never reached for it, and the
    artifact's `power_play_drawn` simply does not list it -- which reads exactly like a session
    this chart does not reach. The reader is looking for a cross that was never drawn and has
    nothing telling them the difference, so the chart refuses the span instead.
    """

    def test_the_chart_refuses_a_question_missing_a_landmark(self) -> None:
        frame = power_play_series()
        real = build_power_play_evidence(frame)
        thinned = {
            **real,
            "chart_questions": [
                {name: value for name, value in question.items() if name != "flag_low_date"}
                for question in real["chart_questions"]
            ],
        }

        with unittest.mock.patch(
            "scripts.minervini.chart.build_power_play_evidence", return_value=thinned
        ):
            with self.assertRaises(KeyError):
                _power_play_spans(frame, "digest")


class WhatIsDrawnHasToBeVisible(unittest.TestCase):
    """Every test here asked whether a drawing call happened, and none asked how.

    Set every marker to size zero and every rule to width zero and the suite went on passing --
    a picture with nothing on it, reported as a picture with everything on it. And the figure
    itself: shrunk to two inches square, Matplotlib warned that the axes had collapsed and the
    tests still agreed the chart was fine.
    """

    def setUp(self) -> None:
        self.frame = power_play_series()
        self.span = _power_play_spans(self.frame, "digest")

    def test_nothing_is_drawn_the_colour_of_the_panel_under_it(self) -> None:
        """Size was the only visibility this class asked about. Painted white on a white panel
        the baseline window vanishes at every size and its legend entry stays -- so the picture
        names a window a reader cannot find, which is the multiple's own divisor. The same edit
        to the marker colour erased every peak star and flag-low cross while `power_play_drawn`
        went on reporting all of them."""
        from matplotlib import colors as mcolors
        import matplotlib.pyplot as plt

        price, volume = RecordingAxis(), RecordingAxis()
        _draw_power_play(price, volume, self.frame, self.span, "daily")

        under = mcolors.to_rgb(plt.rcParams["axes.facecolor"])
        shaded = [drawn for drawn in price.drawn + volume.drawn if "color" in drawn]
        self.assertTrue(shaded)
        for drawn in shaded:
            with self.subTest(label=drawn.get("label")):
                over = mcolors.to_rgb(drawn["color"])
                alpha = float(drawn.get("alpha", 1.0))
                # What the eye is given, which is the colour composited onto the panel rather
                # than the colour asked for: a strong hue at a low alpha is a faint wash. The
                # floor is under what this module draws today -- the baseline shade lands at
                # 0.078 -- and above nothing, which is what a same-colour mutant leaves.
                reached = max(
                    abs(alpha * over[channel] + (1 - alpha) * under[channel] - under[channel])
                    for channel in range(3)
                )
                self.assertGreater(reached, 0.05)

    def test_a_hollow_landmark_is_the_stroke_it_is_drawn_with(self) -> None:
        """Colour was checked and geometry was not, and a hollow marker is all geometry. Set the
        edge width to zero and the peak star and the flag cross vanish -- there is no face to
        fall back on -- while `power_play_drawn` goes on reporting both. And the face has to stay
        empty for the reason it was made empty: a Power Play peak is often a detected swing high
        on the same bar at the same price, and a filled marker drawn afterwards covered the blue
        one completely with the manifest still reporting the anchor as drawn.
        """
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        hollow = [drawn for drawn in price.drawn if "markerfacecolor" in drawn]
        self.assertTrue(hollow)
        for drawn in hollow:
            with self.subTest(label=drawn.get("label")):
                self.assertEqual(drawn["markerfacecolor"], "none")
                self.assertGreater(drawn.get("markeredgewidth", 0), 0.5)

    def test_nothing_is_drawn_at_a_size_nobody_can_see(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        self.assertTrue(price.drawn and volume.drawn)
        for drawn in price.drawn + volume.drawn:
            with self.subTest(label=drawn.get("label")):
                # Above nothing is not the bar. A rule a millionth of a point wide and a shade
                # at a millionth of an alpha are both "greater than zero" and neither is on the
                # picture, so the floors are sizes a person can actually see.
                #
                # The marker floor sits just under the smallest size this module deliberately
                # draws, which is as much as a floor can honestly assert: nothing shrinks below
                # what we chose on purpose. A size between the floor and the chosen one is not
                # something this test can object to -- that judgment is made by looking.
                if "markersize" in drawn:
                    self.assertGreaterEqual(drawn["markersize"], 6)
                if "linewidth" in drawn:
                    self.assertGreater(drawn["linewidth"], 0.5)
                if "alpha" in drawn:
                    self.assertGreater(drawn["alpha"], 0.05)
                if "marker" in drawn:
                    self.assertNotIn(drawn["marker"], (None, "none", ""))

    def test_the_pictures_are_a_size_a_person_can_read(self) -> None:
        """Read off the file, because the figure is the deliverable and its dimensions are the
        one thing about a rendered picture a test can check without eyes."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)
            for timeframe, path in manifest["paths"].items():
                header = Path(path).read_bytes()[16:24]
                width = int.from_bytes(header[:4], "big")
                height = int.from_bytes(header[4:], "big")
                with self.subTest(timeframe=timeframe):
                    self.assertGreaterEqual(width, 1000)
                    self.assertGreaterEqual(height, 600)


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
                self.assertEqual(
                    artifact["power_play_drawn"],
                    {name: [] for name in artifact["power_play_drawn"]},
                )


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

    def test_the_volume_marker_is_the_heaviest_session_of_the_advance(self) -> None:
        """Read off the bars here rather than off the span, because the chart and the question
        come from one builder: if that builder named the wrong session, every test comparing
        the two agrees with it. The clause is about the heaviest session between where the
        advance began and the top it ended on, and that is a fact about the frame.

        Where it began is the session *after* the anchor -- the anchor is the last dormant one,
        which is what the picture's own rule label says. Read from the anchor instead, this
        window agreed with a reading that reached one bar back into dormancy, because on a
        fixture whose dormancy is flat the extra bar can never win. So the anchor is made the
        heaviest bar in the whole frame and the reading still has to skip it.
        """
        frame = self.frame.copy()
        anchor = pd.Timestamp(self.span["advance_anchor_date"])
        frame.loc[anchor, "Volume"] = float(frame["Volume"].max()) * 20
        spans = _power_play_spans(frame, "digest")["spans"]
        self.assertTrue(spans)
        span = spans[0]
        self.assertEqual(span["advance_anchor_date"], self.span["advance_anchor_date"])

        after_the_anchor = frame.loc[anchor : span["peak_date"], "Volume"].iloc[1:]
        heaviest = after_the_anchor.idxmax()

        self.assertNotEqual(heaviest, anchor)
        self.assertEqual(pd.Timestamp(span["advance_peak_volume_date"]), heaviest)

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

    def test_those_prices_are_the_bars_own_and_not_just_the_questions(self) -> None:
        """Comparing the picture with the field it was drawn from says they agree and nothing
        more. Publish zero for the peak and the star lands on zero, with the two still in
        perfect agreement about a price the bars never traded at. So the levels are checked
        against the sessions they name."""
        self.assertEqual(
            float(self.span["peak_high"]),
            float(self.frame.loc[self.span["peak_date"], "High"]),
        )
        self.assertEqual(
            float(self.span["flag_low"]),
            float(self.frame.loc[self.span["flag_low_date"], "Low"]),
        )
        after_the_peak = self.frame.loc[self.span["peak_date"]:, "Low"]
        self.assertEqual(float(self.span["flag_low"]), float(after_the_peak.min()))

    def test_the_anchor_is_the_session_after_the_quiet_window_ends(self) -> None:
        """The two are adjacent by construction and nothing was checking it, so the anchor could
        be published as the last baseline session -- one bar early, on the landmark that decides
        where the move commenced. The rule's own label says the advance starts after this
        session, and that sentence is only true of this bar."""
        first = self.frame.index.get_loc(pd.Timestamp(self.span["baseline_last_session"]))
        anchor = self.frame.index.get_loc(pd.Timestamp(self.span["advance_anchor_date"]))

        self.assertEqual(anchor, first + 1)

    def test_the_span_says_which_reading_it_came_from(self) -> None:
        """The reading index is what carries a mark back to the question it belongs to, and a
        chain of tops issues several spans that differ in little else."""
        spans = _power_play_spans(self.frame, "digest")["spans"]
        asked = [
            question for question in build_power_play_evidence(self.frame)["chart_questions"]
            if question.get("answered") is None
        ]

        # One span per reading, not per question: a reading with three undecided criteria is
        # three questions about one picture.
        self.assertEqual(
            [span["reading"] for span in spans],
            sorted({question["reading"] for question in asked}),
        )

    def test_the_advance_rule_stands_on_the_anchor_session(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, {"spans": [self.span]}, "daily")

        self.assertEqual(price.rules, [pd.Timestamp(self.span["advance_anchor_date"])])
