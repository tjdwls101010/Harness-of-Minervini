"""Behavior checks for chart panel labels."""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path
from scripts.minervini import chart as chart_module
from scripts.minervini.chart import _power_play_spans, render_chart_artifacts
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import power_play_series
from tests.unit.chart._chart_fixtures import _panel_index, _rendered, artifact_end
from tests.charts import RecordingAxis


class WhatThePictureSaysAboutItself(unittest.TestCase):
    """Every published thing that names the bundle has to name the same bundle.

    Three of these went unpinned until a reviewer mutated them: the panel could call itself
    Daily while the manifest called it power_play, `paths` could omit a picture that `artifacts`
    and the directory both hold, and the shaded baseline could collapse to zero width with both
    boundary dates still reported.
    """

    def setUp(self) -> None:
        self.frame = power_play_series(dormancy_sessions=400)
        self.span = _power_play_spans(self.frame, "digest")

    def test_the_panel_calls_itself_what_the_manifest_calls_it(self) -> None:
        """The title is the only thing on the picture that says which panel a reader is holding."""
        self.assertEqual(
            chart_module._PANEL_TITLES,
            {"weekly": "Weekly", "daily": "Daily", "power_play": "Power Play"},
        )

    def test_paths_holds_every_picture_the_artifacts_list_does(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        self.assertEqual(
            sorted(manifest["paths"]),
            sorted(artifact["timeframe"] for artifact in manifest["artifacts"]),
        )
        self.assertEqual(
            sorted(manifest["paths"].values()),
            sorted(artifact["path"] for artifact in manifest["artifacts"]),
        )

    def test_only_the_week_still_collecting_calls_its_last_bar_partial(self) -> None:
        """`last_bar_partial` warns that a bar aggregates fewer sessions than it will end up
        holding, so its volume is short for a reason that is not the stock going quiet. That is
        a weekly bucket's problem. The daily and Power Play panels are drawn on completed
        sessions, and a mid-week render marking their last bar partial tells a reader to
        discount the very session the volume question is asked about.
        """
        frame = self.frame
        if frame.index[-1].weekday() == 4:
            frame = frame.iloc[:-1]
        self.assertNotEqual(frame.index[-1].weekday(), 4, "the frame has to end mid-week")

        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(frame, directory)

        partial = {
            artifact["timeframe"]: artifact["last_bar_partial"]
            for artifact in manifest["artifacts"]
        }
        self.assertEqual(partial, {"weekly": True, "daily": False, "power_play": False})

    def test_the_picture_and_the_manifest_name_the_ticker_that_was_asked_for(self) -> None:
        """Nothing was comparing either of them with the request, so both could name some other
        stock on some other date and agree with each other perfectly while doing it."""
        real = chart_module._atomic_figure
        titles: list[str] = []

        def measure(figure, path):
            titles.append(figure.axes[0].get_title())
            return real(figure, path)

        asked = self.frame.index[-1].date()
        chart_module._atomic_figure = measure
        try:
            with tempfile.TemporaryDirectory() as directory:
                manifest = render_chart_artifacts(
                    self.frame, ticker="ASKED", as_of=asked, output_dir=directory
                )
                names = sorted(Path(path).name for path in Path(directory).glob("*.png"))
        finally:
            chart_module._atomic_figure = real

        self.assertEqual(manifest["ticker"], "ASKED")
        self.assertEqual(manifest["as_of"], asked.isoformat())
        for title in titles:
            with self.subTest(title=title):
                self.assertTrue(title.startswith("ASKED "))
                self.assertIn(asked.isoformat(), title)
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(name.startswith(f"ASKED_{asked.isoformat()}_"))

    def test_what_it_reports_drawing_is_what_the_panel_actually_holds(self) -> None:
        """The report is what a reader consults instead of hunting the picture, so a landmark
        the panel shows and the report denies sends them looking for a mark that is there and
        telling them it is not -- and the other way round. Checked against the sessions each
        panel covers rather than against the report's own contents."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        asked = [
            question for question in build_power_play_evidence(self.frame)["chart_questions"]
            if question.get("answered") is None
        ]
        for artifact in manifest["artifacts"]:
            covered = self.frame.loc[:artifact_end(artifact, self.frame)]
            for landmark in chart_module._SPAN_LANDMARK_DATES:
                named = {
                    question[landmark] for question in asked
                    if question.get(landmark) is not None
                    and chart_module._containing_bar(
                        _panel_index(artifact, self.frame), str(question[landmark]),
                        artifact["timeframe"],
                    ) is not None
                }
                with self.subTest(timeframe=artifact["timeframe"], landmark=landmark):
                    self.assertEqual(
                        sorted(artifact["power_play_drawn"][landmark]), sorted(named)
                    )
            self.assertTrue(len(covered) > 0)

    def test_each_published_path_names_the_panel_it_belongs_to(self) -> None:
        """Completeness says the three pictures are all reported; it does not say which is
        which. Swapping the weekly and daily paths left both in the manifest and both on disk,
        and pointed the reader at the wrong picture for every landmark on it."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        held = {
            "weekly": len(chart_module._weekly_bars(self.frame, self.frame.index[-1].date())),
            "daily": len(self.frame),
            "power_play": len(
                chart_module._span_window(self.frame, self.span["spans"])
            ),
        }
        for artifact in manifest["artifacts"]:
            timeframe = artifact["timeframe"]
            with self.subTest(timeframe=timeframe):
                self.assertTrue(Path(artifact["path"]).name.endswith(f"_{timeframe}.png"))
                self.assertEqual(
                    Path(manifest["paths"][timeframe]).name, Path(artifact["path"]).name
                )
                self.assertEqual(artifact["bars"], held[timeframe])

    def test_the_panel_says_what_each_of_its_axes_holds(self) -> None:
        """The title and the two axis labels are the whole of what a picture says about itself.
        Nothing was reading them, so this panel could have called its volume axis Price while
        the manifest called the artifact power_play."""
        real = chart_module._atomic_figure
        said: list[tuple[str, str, str]] = []

        def measure(figure, path):
            price_axis, volume_axis = figure.axes[0], figure.axes[1]
            said.append((
                price_axis.get_title(), price_axis.get_ylabel(), volume_axis.get_ylabel()
            ))
            return real(figure, path)

        chart_module._atomic_figure = measure
        try:
            with tempfile.TemporaryDirectory() as directory:
                manifest = _rendered(self.frame, directory)
        finally:
            chart_module._atomic_figure = real

        drawn = [artifact["timeframe"] for artifact in manifest["artifacts"]]
        self.assertEqual(len(said), len(drawn))
        for timeframe, (title, price_label, volume_label) in zip(drawn, said):
            with self.subTest(timeframe=timeframe):
                self.assertIn(chart_module._PANEL_TITLES[timeframe], title)
                self.assertEqual(price_label, "Price")
                self.assertEqual(volume_label, "Volume")

    @staticmethod
    def _bars_of(figure, daily):
        """The sessions this panel drew, in the order its candles were added."""
        title = figure.axes[0].get_title()
        if "Weekly" in title:
            weekly = (
                daily.resample("W-FRI")
                .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
                .dropna()
            )
            return list(weekly.iterrows())
        if "Power Play" in title:
            span = chart_module._span_window(daily, _power_play_spans(daily, "digest")["spans"])
            return list(span.iterrows())
        return list(daily.iterrows())

    def test_the_weekly_panel_draws_no_divisor(self) -> None:
        """It is a session median, and a weekly bar is five sessions added together -- a line at
        that level sits on the floor of a panel it was never measured on."""
        weekly = (
            self.frame.resample("W-FRI")
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna()
        )
        volume = RecordingAxis()

        chart_module._shade_baselines(volume, weekly, self.span["spans"], "weekly")

        self.assertEqual(volume.levels, [])
