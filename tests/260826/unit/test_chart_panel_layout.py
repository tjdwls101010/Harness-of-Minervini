"""Behavior checks for chart panel layout."""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
import warnings
from typing import Any
import pandas as pd
from scripts.minervini import chart as chart_module
from scripts.minervini.chart import _power_play_spans
from tests.series import power_play_series
from ._chart_fixtures import _rendered
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

    def test_the_mark_on_top_of_the_tallest_bar_is_inside_the_frame(self) -> None:
        """Matplotlib stops the volume axis five percent above its tallest bar, and at that
        height the triangle on top of that bar is cut flat by the border -- looked at on a real
        ABCL render, where the cut lands on exactly the session the panel is asking about, since
        the heaviest advance session is the tallest bar whenever the baseline was quiet.

        So the floor is a ceiling higher than the one autoscale picks. Where between the two a
        mark stops being clipped is a judgment made by looking, and was: five percent clips and
        twelve does not.
        """
        real = chart_module._atomic_figure
        ceilings: list[tuple[float, float]] = []

        def measure(figure, path):
            for axis in figure.axes:
                heights = [patch.get_height() for patch in axis.patches if patch.get_height()]
                if heights:
                    ceilings.append((float(axis.get_ylim()[1]), float(max(heights))))
            return real(figure, path)

        chart_module._atomic_figure = measure
        try:
            with tempfile.TemporaryDirectory() as directory:
                _rendered(self.frame, directory)
        finally:
            chart_module._atomic_figure = real

        self.assertTrue(ceilings)
        for ceiling, tallest in ceilings:
            with self.subTest(tallest=tallest):
                self.assertGreaterEqual(ceiling, tallest * 1.10)

    def test_the_shade_covers_the_window_it_names(self) -> None:
        """A rectangle of zero width is a window the manifest reports and the picture does not
        show, and the ratio beside it is divided by sessions the reader cannot see."""
        volume = RecordingAxis()

        chart_module._shade_baselines(volume, self.frame, self.span["spans"], "daily")

        # Whole bars. A bar is drawn centred on its session, so a rectangle running centre to
        # centre leaves half of each boundary session outside a window that counted all of it --
        # and this panel is where a reader answers which sessions the median was taken over.
        edge = pd.Timedelta(days=chart_module._bar_width("daily") / 2)
        self.assertTrue(volume.spans)
        for start, end in volume.spans:
            with self.subTest(start=start):
                self.assertEqual(
                    start,
                    pd.Timestamp(self.span["spans"][0]["baseline_first_session"]) - edge,
                )
                self.assertEqual(
                    end, pd.Timestamp(self.span["spans"][0]["baseline_last_session"]) + edge
                )
                self.assertGreater(end - start, pd.Timedelta(days=1))

    def test_the_divisor_is_the_median_of_exactly_the_sessions_the_bounds_name(self) -> None:
        """The window is published as two dates and the divisor as one number, and a reader
        checking the multiple has only those. Every dormant session in this fixture carries the
        same volume, so a reading that lost the window's first session, or its last, or reached
        one session forward into the anchor, returned the same median and agreed with bounds it
        no longer matched. The advance-anchor version of that slip is not cosmetic: it moved the
        ratio under the criterion's threshold, failed the volume clause, and withdrew the chart
        question a person was supposed to answer.

        So the sessions are made a ramp, and the anchor unlike any of them. Then the four
        windows a one-session slip can land on are four different numbers, and this assertion
        can disagree with the code.
        """
        published = self.span["spans"][0]
        first = pd.Timestamp(published["baseline_first_session"])
        last = pd.Timestamp(published["baseline_last_session"])
        anchor = pd.Timestamp(published["advance_anchor_date"])

        frame = self.frame.copy()
        window = frame.loc[first:last].index
        frame.loc[window, "Volume"] = [
            100_000.0 + step * 10_000 for step in range(len(window))
        ]
        frame.loc[anchor, "Volume"] = 2_000_000.0

        spans = _power_play_spans(frame, "digest")["spans"]
        self.assertTrue(spans)
        span = spans[0]
        self.assertEqual(span["baseline_first_session"], published["baseline_first_session"])
        self.assertEqual(span["baseline_last_session"], published["baseline_last_session"])

        named = frame.loc[first:last, "Volume"]
        taken = float(named.median())
        self.assertEqual(float(span["baseline_volume"]), taken)
        for slipped, what in (
            (named.iloc[1:], "without its first session"),
            (named.iloc[:-1], "without its last"),
            (pd.concat([named, frame.loc[[anchor], "Volume"]]), "reaching into the anchor"),
        ):
            with self.subTest(window=what):
                self.assertNotEqual(float(slipped.median()), taken)

    def test_the_divisor_is_drawn_across_the_window_it_was_taken_over(self) -> None:
        """The median is the one number on this panel a reader cannot point at, and without it
        the eye checks the multiple against the tallest bar in the shade instead."""
        volume = RecordingAxis()

        chart_module._shade_baselines(volume, self.frame, self.span["spans"], "daily")

        divisor = self.span["spans"][0]["baseline_volume"]
        self.assertIsNotNone(divisor)
        # Against the sessions, not just against the field it was published in. Doubling the
        # published divisor draws a line that is not the median and labels a ratio computed
        # from one that is -- and comparing the line with the field it came from calls that
        # agreement.
        self.assertEqual(
            float(divisor),
            float(
                self.frame.loc[
                    self.span["spans"][0]["baseline_first_session"]:
                    self.span["spans"][0]["baseline_last_session"],
                    "Volume",
                ].median()
            ),
        )
        # Across the shade rather than across the window's centres: a line stopping short of
        # the rectangle it belongs to reads as a level that ran out partway through it.
        edge = pd.Timedelta(days=chart_module._bar_width("daily") / 2)
        self.assertEqual(
            volume.levels,
            [(
                float(divisor),
                pd.Timestamp(self.span["spans"][0]["baseline_first_session"]) - edge,
                pd.Timestamp(self.span["spans"][0]["baseline_last_session"]) + edge,
            )],
        )
        self.assertIn("baseline median", volume.labels)

    def test_a_multiple_just_over_one_is_not_printed_as_one(self) -> None:
        """One decimal is the right precision for judging expansion, and harmless everywhere but
        at 1.0. A published 1.04 printed there says the heaviest session of the advance merely
        matched its baseline -- and exceeding the baseline is the condition that makes the
        question exist, so the picture argues against the number that put it on the page."""
        frame = power_play_series(advance_volume_multiple=1.04)
        span = _power_play_spans(frame, "digest")
        self.assertTrue(span["spans"], "the fixture has to still be asking for this to mean anything")
        ratio = span["spans"][0]["advance_peak_volume_ratio"]
        self.assertGreater(ratio, 1.0)
        self.assertEqual(round(ratio, 1), 1.0)
        price, volume = RecordingAxis(), RecordingAxis()

        chart_module._draw_power_play(price, volume, frame, span, "daily")

        printed = [label for label in volume.labels if label.startswith("heaviest advance")]
        self.assertTrue(printed)
        self.assertNotIn("(1.0x", printed[0])
        self.assertIn(f"({ratio:.2f}x", printed[0])

    def test_the_legend_does_not_sit_on_the_bar_it_asks_about(self) -> None:
        """Pinned to the upper left, the volume legend covered the tallest bar of the baseline
        window on a real name -- which is exactly the bar the reader is being asked to compare
        the marked session against, and the legend is what carries that mark back to its
        question. Covering the picture it explains costs both.

        What it may not cover is what it names: the landmarks, and the tallest bar of the
        window the multiple is divided against. On a panel of seven hundred candles a legend
        sits over some of them wherever it goes, and that is not the complaint."""
        import matplotlib.pyplot as plt

        # The heavy day at the window's own left edge, which is where the span panel puts it --
        # five sessions in, under whatever a corner-pinned legend would occupy. Below the
        # panel's tallest bar on purpose: the advance almost always runs heavier than anything
        # in the quiet window, so protecting the panel's maximum protects a bar in the advance
        # and leaves this one -- the one the multiple is measured against -- under the legend.
        loud = self.frame.copy()
        opening = pd.Timestamp(self.span["spans"][0]["baseline_first_session"])
        loud.loc[opening, "Volume"] = float(loud["Volume"].max()) * 0.8

        real_subplots = plt.subplots
        real_figure = chart_module._atomic_figure
        collisions: list[str] = []
        panels: list[Any] = []

        def keep(*args, **kwargs):
            figure, (price_axis, volume_axis) = real_subplots(*args, **kwargs)
            panels.append((price_axis, volume_axis))
            return figure, (price_axis, volume_axis)

        def measure(figure, path):
            figure.canvas.draw()
            for axis in figure.axes:
                legend = axis.get_legend()
                if legend is None:
                    continue
                box = legend.get_window_extent()
                for line in axis.lines:
                    if line.get_marker() in (None, "None", "none", ""):
                        continue
                    if box.overlaps(line.get_window_extent()):
                        collisions.append(line.get_label())
                # The window's own tallest bar, not the panel's: the multiple is measured
                # against that window, so that is the bar the eye reaches for.
                for patch in axis.patches:
                    if not patch.get_height():
                        continue
                    if abs(patch.get_height() - float(loud.loc[opening, "Volume"])) > 1e-9:
                        continue
                    if box.overlaps(patch.get_window_extent()):
                        collisions.append(f"baseline bar {patch.get_height()}")
            return real_figure(figure, path)

        chart_module.plt.subplots = keep
        chart_module._atomic_figure = measure
        try:
            with tempfile.TemporaryDirectory() as directory:
                _rendered(loud, directory)
        finally:
            chart_module.plt.subplots = real_subplots
            chart_module._atomic_figure = real_figure

        self.assertTrue(panels, "the render has to have drawn something")
        self.assertLess(
            float(loud.loc[opening, "Volume"]), float(loud["Volume"].max()),
            "the fixture only means something while the baseline's bar is not the panel's",
        )
        self.assertEqual(collisions, [])

    def test_no_candle_body_reaches_past_the_session_it_belongs_to(self) -> None:
        """The floor that keeps a doji visible is a fraction of the bar's own range, and drawn
        upward from a doji sitting at its high it put the body above the high -- a price the
        stock never traded, on the picture a base's tightness is approved from."""
        import matplotlib.pyplot as plt

        pinned = self.frame.copy()
        # A session that opened and closed at its high, and one that never moved at all.
        pinned.iloc[10, pinned.columns.get_indexer(["Open", "Close", "High"])] = 10.0
        pinned.iloc[10, pinned.columns.get_loc("Low")] = 9.0
        pinned.iloc[11, pinned.columns.get_indexer(["Open", "High", "Low", "Close"])] = 7.5

        real = chart_module._atomic_figure
        outside: list[tuple[float, float]] = []

        def measure(figure, path):
            price_axis = figure.axes[0]
            for patch, (_, row) in zip(price_axis.patches, self._bars_of(figure, pinned)):
                top = patch.get_y() + patch.get_height()
                if top > row["High"] + 1e-9 or patch.get_y() < row["Low"] - 1e-9:
                    outside.append((patch.get_y(), top))
            return real(figure, path)

        chart_module._atomic_figure = measure
        try:
            with tempfile.TemporaryDirectory() as directory:
                _rendered(pinned, directory)
        finally:
            chart_module._atomic_figure = real

        self.assertEqual(outside, [])

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

    def test_no_legend_runs_off_the_page(self) -> None:
        """The placement above the panel is clear of the marks by construction and can still be
        wider than the panel, and there it takes its own last entry and the axis labels off the
        side of the page with it. Forced by giving every landmark a long name."""
        import matplotlib.pyplot as plt

        real_names = chart_module._names
        real_corners = chart_module._LEGEND_CORNERS
        # Long enough that two columns of it are wider than the panel, and with no corner to
        # fall into, so the placement above the panel is the one under test.
        chart_module._names = lambda marks, days: " (" + ", ".join(days) * 10 + ")"
        chart_module._LEGEND_CORNERS = ()
        real_figure = chart_module._atomic_figure
        off_the_page: list[str] = []

        def measure(figure, path):
            figure.canvas.draw()
            for axis in figure.axes:
                legend = axis.get_legend()
                if legend is None:
                    continue
                if not chart_module._inside(legend.get_window_extent(), figure.bbox):
                    off_the_page.append(figure.axes[0].get_title())
            return real_figure(figure, path)

        chart_module._atomic_figure = measure
        try:
            with tempfile.TemporaryDirectory() as directory:
                # The oversized legend is the point, and matplotlib says so on every draw.
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message=".*constrained_layout.*")
                    _rendered(self.frame, directory)
        finally:
            chart_module._names = real_names
            chart_module._LEGEND_CORNERS = real_corners
            chart_module._atomic_figure = real_figure

        self.assertEqual(off_the_page, [])

    def test_the_boundary_is_never_printed_from_either_side(self) -> None:
        """Falling short of the baseline reads the same way from the other side: 0.999 printed
        as `1.00x` claims a session matched a baseline it did not. Below one is the reading that
        rejects the criterion, so the picture must not round it up to the line."""
        printed = {ratio: chart_module._multiple(ratio) for ratio in (0.96, 0.999, 0.9999, 1.001, 1.04, 6.0, 10.493)}

        for ratio, text in printed.items():
            with self.subTest(ratio=ratio):
                self.assertNotEqual(float(text), 1.0)
                self.assertEqual(float(text) > 1.0, ratio > 1.0)
        self.assertEqual(printed[6.0], "6.0")
        self.assertEqual(printed[10.493], "10.5")
        self.assertEqual(chart_module._multiple(1.0), "1.0")
