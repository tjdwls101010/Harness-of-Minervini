"""The chart the analyst approves from has to show what they are approving.

The detector's chain answers a required condition, and the flow asks a person to look at it and
declare it back. A chart without the anchors on it makes that approval a formality: you would be
agreeing to a list of dates while looking at a picture that never mentions them.
"""

from __future__ import annotations

import json
import tempfile
import unittest

import pandas as pd
from pathlib import Path

from scripts.minervini.chart import RENDERER_VERSION, _draw_anchors, render_chart_artifacts
from scripts.minervini.setup_structure import bars_fingerprint, read_bars
from scripts.minervini.swings import canonical_chain
from tests.series import anchor_dates, base_series, unstable_series


class AnchorOverlayTests(unittest.TestCase):
    def test_the_manifest_records_the_anchors_that_were_drawn(self) -> None:
        frame, anchors = base_series()

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        self.assertEqual([item["date"] for item in manifest["segmentation"]["anchors"]], anchor_dates(frame, anchors))
        self.assertEqual(manifest["segmentation"]["state"], "resolved")

    def test_the_manifest_on_disk_carries_them_too(self) -> None:
        frame, _ = base_series()

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )
            written = json.loads(Path(manifest["manifest_path"]).read_text(encoding="utf-8"))

        self.assertEqual(written["segmentation"], manifest["segmentation"])

    def test_the_manifest_names_one_set_of_bars_not_two(self) -> None:
        """The provenance digest and the segmentation's are the same value, or an approval
        taken from one of them would not match what the other was cut from."""

        frame, _ = base_series()

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        self.assertEqual(manifest["segmentation"]["bars_fingerprint"], manifest["input_sha256"])

    def test_the_weekly_chart_marks_the_week_a_swing_happened_in(self) -> None:
        """A Tuesday low has no Tuesday bar on a weekly chart, and it still happened.

        Requiring the anchor's own date to be a weekly session left almost every anchor off:
        the label is the week's Friday, so only a swing that landed exactly on one was drawn.
        """

        frame, anchors = base_series()
        declared = anchor_dates(frame, anchors)

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        drawn = {artifact["timeframe"]: artifact["anchors_drawn"] for artifact in manifest["artifacts"]}
        self.assertEqual(drawn["daily"], declared)
        self.assertEqual(drawn["weekly"], declared)

    def test_the_week_in_progress_is_on_the_chart_rather_than_dropped(self) -> None:
        """A week is kept for the sessions it aggregates, not for the label it was given.

        Buckets were filtered by their Friday label against as_of, so a mid-week reading -- and
        every week whose Friday is a holiday -- lost its most recent weekly bar and the anchors
        on it. Every bucket here only ever holds completed sessions, because the daily frame was
        cut at as_of before the resample.
        """

        frame, _ = base_series(start="2026-01-05", breakout=False)

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        pivot = manifest["segmentation"]["anchors"][-1]["date"]
        weekly = next(item for item in manifest["artifacts"] if item["timeframe"] == "weekly")
        self.assertIn(pivot, weekly["anchors_drawn"])
        self.assertTrue(weekly["pivot_drawn"])

    def test_an_unvouched_segmentation_puts_nothing_on_either_timeframe(self) -> None:
        frame, _ = unstable_series()

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        self.assertEqual([artifact["anchors_drawn"] for artifact in manifest["artifacts"]], [[], []])
        self.assertEqual([artifact["pivot_drawn"] for artifact in manifest["artifacts"]], [False, False])

    def test_a_segmentation_the_detector_will_not_vouch_for_draws_nothing(self) -> None:
        """Drawing an unstable chain would show a person a structure the engine refuses to use."""

        frame, _ = unstable_series()

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        self.assertEqual(manifest["segmentation"]["state"], "unstable")
        self.assertEqual(manifest["segmentation"]["anchors"], [])


class RecordingAxis:
    """Enough of an axis to say what was asked of it, and nothing else.

    The manifest's `pivot_drawn` is what a reader sees, and a test that only checks it is
    checking one half of a coupling against itself: make the axhline unconditional again and
    leave the flag alone, and every other test here still passes. The drawing is not observable
    through a rendered PNG, so this is where the coupling gets pinned.
    """

    def __init__(self) -> None:
        self.markers: list[float] = []
        self.levels: list[float] = []

    def plot(self, _x, y, **_kwargs) -> None:
        self.markers.append(float(y[0]))

    def axhline(self, level, **_kwargs) -> None:
        self.levels.append(float(level))


class ThePivotLineFollowsThePivotTests(unittest.TestCase):
    def test_no_level_is_drawn_when_the_pivot_has_no_bar_on_this_timeframe(self) -> None:
        frame, _ = base_series(start="2026-01-05", breakout=False)
        segmentation = canonical_chain(frame)
        weekly = frame.resample("W-FRI").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()
        weekly = weekly.loc[weekly.index.date <= frame.index[-1].date()]
        axis = RecordingAxis()

        drawn, pivot_drawn = _draw_anchors(axis, weekly, segmentation, "weekly")

        self.assertNotIn(segmentation["anchors"][-1]["date"], drawn)
        self.assertFalse(pivot_drawn)
        self.assertEqual(axis.levels, [])
        self.assertTrue(axis.markers)

    def test_the_level_is_drawn_once_when_the_pivot_is_on_the_chart(self) -> None:
        frame, _ = base_series(start="2026-01-05", breakout=False)
        segmentation = canonical_chain(frame)
        axis = RecordingAxis()

        _, pivot_drawn = _draw_anchors(axis, frame, segmentation, "daily")

        self.assertTrue(pivot_drawn)
        self.assertEqual(axis.levels, [float(segmentation["anchors"][-1]["price"])])


class OneIdeaOfAUsableBarTests(unittest.TestCase):
    """A picture nothing can be approved from is not a success.

    The chart validated bars its own way and the setup validated them another, so a render could
    succeed off bars the measuring side refuses -- and the artifact then carried a null digest,
    which is the one thing a setup approval has to name. The envelope still said ok and pointed
    at ticker.setup, which is the absence of provenance read as success.
    """

    def _refused(self, frame) -> str:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as raised:
                render_chart_artifacts(frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory)
        return str(raised.exception)

    def test_a_session_with_no_price_at_all_is_refused_by_both(self) -> None:
        frame, _ = base_series()
        frame.iloc[5, :4] = 0.0

        self.assertIsNone(bars_fingerprint(frame))
        self.assertIn("history_contains_non_positive_values", self._refused(frame))

    def test_two_stamps_on_one_date_are_refused_by_both(self) -> None:
        frame, _ = base_series()
        frame = frame.iloc[:5].copy()
        frame.index = [
            pd.Timestamp("2026-01-02 09:30"), pd.Timestamp("2026-01-02 16:00"),
            pd.Timestamp("2026-01-05 16:00"), pd.Timestamp("2026-01-06 16:00"), pd.Timestamp("2026-01-07 16:00"),
        ]

        self.assertIsNone(bars_fingerprint(frame))
        self.assertIn("history_repeats_a_session", self._refused(frame))

    def test_the_two_surfaces_never_disagree_about_a_frame(self) -> None:
        """The invariant, rather than one rule at a time.

        What went wrong was not any single check but that there were two lists of them. Pinning
        the rules one by one would let the lists drift apart again between the pinned ones.
        """

        base, _ = base_series()

        def zero_prices(frame): frame.iloc[5, 0:4] = 0.0
        def negative_close(frame): frame.iloc[9, frame.columns.get_loc("Close")] = -1.0
        def negative_volume(frame): frame.iloc[9, frame.columns.get_loc("Volume")] = -5.0
        def high_below_low(frame): frame.iloc[11, frame.columns.get_loc("High")] = float(frame["Low"].iloc[11]) - 1
        def open_above_high(frame): frame.iloc[13, frame.columns.get_loc("Open")] = float(frame["High"].iloc[13]) + 1
        def nan_close(frame): frame.iloc[15, frame.columns.get_loc("Close")] = float("nan")
        def infinite_high(frame): frame.iloc[17, frame.columns.get_loc("High")] = float("inf")
        def repeated_session(frame): frame.index = [frame.index[0], *frame.index[1:-1], frame.index[0]]
        def missing_column(frame): frame.drop(columns=["Volume"], inplace=True)
        def non_date_index(frame): frame.index = ["not-a-date", *frame.index[1:]]

        def missing_stamp(frame): frame.index = [pd.NaT, *frame.index[1:]]
        def positional_index(frame): frame.index = pd.RangeIndex(len(frame))

        def boolean_prices(frame):
            for column in ("Open", "High", "Low", "Close"):
                frame[column] = True

        def repeated_column(frame):
            frame["spare"] = frame["Close"]
            frame.columns = ["Open", "High", "Low", "Close", "Volume", "Close"]

        def late_evening_zone(frame):
            # Two exchange dates, one of which becomes the next UTC day if the zone is converted
            # rather than dropped. Everything above is naive, which is how a whole timezone seam
            # sat between the two surfaces with the matrix reporting agreement.
            frame.index = pd.DatetimeIndex(
                [pd.Timestamp("2026-01-01 23:30"), pd.Timestamp("2026-01-02 16:00"), *frame.index[2:]]
            ).tz_localize("America/New_York")

        def two_sessions_one_zone_day(frame):
            frame.index = pd.DatetimeIndex(
                [pd.Timestamp("2026-01-02 00:30"), pd.Timestamp("2026-01-02 23:30"), *frame.index[2:]]
            ).tz_localize("America/New_York")

        mutations = [
            ("untouched", lambda frame: None), ("zero prices", zero_prices), ("negative close", negative_close),
            ("negative volume", negative_volume), ("high below low", high_below_low),
            ("open above high", open_above_high), ("nan close", nan_close), ("infinite high", infinite_high),
            ("repeated session", repeated_session), ("missing column", missing_column),
            ("non-date index", non_date_index), ("repeated column", repeated_column),
            ("missing stamp", missing_stamp), ("positional index", positional_index),
            ("boolean prices", boolean_prices),
            ("late evening zone", late_evening_zone),
            ("two sessions one zone day", two_sessions_one_zone_day),
        ]
        for label, mutate in mutations:
            with self.subTest(frame=label):
                frame = base.copy()
                mutate(frame)
                # Both sides have to answer, rather than one of them raising something the
                # envelope has no word for.
                accepted = read_bars(frame)[1] is None
                try:
                    with tempfile.TemporaryDirectory() as directory:
                        render_chart_artifacts(frame, ticker="TEST", as_of=base.index[-1].date(), output_dir=directory)
                    rendered = True
                except ValueError:
                    rendered = False
                self.assertEqual(accepted, rendered)

    def test_a_week_still_collecting_sessions_says_so(self) -> None:
        """Its volume bar is short because the week is short, not because the stock went quiet.

        Volume drying up is one of the things a reader is looking for on this picture, so the
        one bar that is guaranteed to look dry for an unrelated reason has to be labelled.
        """

        for start, partial in (("2026-01-06", False), ("2026-01-05", True)):
            with self.subTest(start=start):
                frame, _ = base_series(start=start, breakout=False)
                with tempfile.TemporaryDirectory() as directory:
                    manifest = render_chart_artifacts(
                        frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
                    )
                weekly = next(item for item in manifest["artifacts"] if item["timeframe"] == "weekly")
                self.assertEqual(weekly["last_bar_partial"], partial)
                self.assertFalse(
                    next(item for item in manifest["artifacts"] if item["timeframe"] == "daily")["last_bar_partial"]
                )

    def test_a_doji_stays_a_doji_at_any_price(self) -> None:
        """A body floor in dollars is a different floor on every stock.

        A five-cent name with a one-tenth-of-a-cent range had a body drawn five times its whole
        session, and the axis stretched to fit a candle that never traded -- on the picture a
        person approves a base's tightness from.
        """

        index = pd.bdate_range("2026-01-02", periods=60)
        penny = pd.DataFrame(
            {"Open": 0.050, "High": 0.051, "Low": 0.049, "Close": 0.050, "Volume": 1e6}, index=index
        )

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                penny, ticker="TEST", as_of=index[-1].date(), output_dir=directory
            )

        # It renders at all, and nothing about it depends on a dollar-denominated floor.
        self.assertEqual(len(manifest["artifacts"]), 2)
        self.assertEqual(manifest["renderer_version"], RENDERER_VERSION)

    def test_a_session_late_in_the_exchange_day_keeps_its_own_date(self) -> None:
        """The date a session traded on, not the UTC day it spills into.

        One surface dropped the zone and the other converted to UTC, so the same tz-aware bars
        were a repeated session to one and two ordinary ones to the other -- and where both did
        accept, they fingerprinted different dates.
        """

        frame, _ = base_series()
        frame.index = pd.DatetimeIndex(
            [pd.Timestamp("2026-01-01 23:30"), pd.Timestamp("2026-01-02 16:00"), *frame.index[2:]]
        ).tz_localize("America/New_York")

        bars, rejection = read_bars(frame)

        self.assertIsNone(rejection)
        self.assertEqual([str(bars.index[0].date()), str(bars.index[1].date())], ["2026-01-01", "2026-01-02"])

    def test_an_infinite_price_leaves_as_unavailable_rather_than_an_exception(self) -> None:
        """`read_bars` passed it and the digest raised on it, which is an internal failure where
        the envelope should have carried typed unavailability."""

        frame, _ = base_series()
        frame.iloc[7, frame.columns.get_loc("High")] = float("inf")

        self.assertIsNone(bars_fingerprint(frame))


if __name__ == "__main__":
    unittest.main()
