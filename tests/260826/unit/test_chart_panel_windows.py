"""Behavior checks for chart panel windows."""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path
import pandas as pd
from scripts.minervini import chart as chart_module
from scripts.minervini.chart import _draw_power_play, _power_play_spans
from scripts.minervini.power_play_evidence import build_power_play_evidence
from tests.series import base_series, power_play_series, two_tops_that_both_await_the_chart_series
from ._chart_fixtures import _rendered
from tests.charts import RecordingAxis


class ThePanelTheFlagCanBeMeasuredOn(unittest.TestCase):
    """Seven hundred sessions in twelve inches cannot show a four-session flag.

    On a real name with three years of history the flag was a handful of pixels under a marker
    wider than the flag itself, so the reader was asked whether it corrected no more than
    twenty-five percent while looking at something they could not measure. The two
    whole-history pictures are what a base is read from and stay exactly as they were; this is
    a third one, and it is the span.
    """

    def test_the_lead_in_is_what_the_history_has_to_give(self) -> None:
        """Up to five sessions, and a history beginning inside its own baseline has none to
        give. The panel starts where the history does; the promise that the window's left edge
        is visible as an edge rather than as the side of the page is the one thing this case
        cannot keep, and the capability says so rather than claiming a week it never drew."""
        frame = power_play_series(dormancy_sessions=41)
        spans = _power_play_spans(frame, "digest")["spans"]
        self.assertTrue(spans)

        window = chart_module._span_window(frame, spans)

        self.assertIsNotNone(window)
        self.assertEqual(window.index[0], frame.index[0])
        self.assertEqual(
            pd.Timestamp(spans[0]["baseline_first_session"]), frame.index[0]
        )

    def setUp(self) -> None:
        self.frame = power_play_series(dormancy_sessions=400)
        self.questions = [
            question for question in build_power_play_evidence(self.frame)["chart_questions"]
            if question.get("answered") is None
        ]

    def test_the_fixture_is_long_enough_that_the_span_would_disappear(self) -> None:
        self.assertTrue(self.questions)
        self.assertGreater(len(self.frame), 400)

    def test_the_span_panel_is_a_third_artifact_and_the_others_are_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        timeframes = [artifact["timeframe"] for artifact in manifest["artifacts"]]
        self.assertEqual(timeframes, ["weekly", "daily", "power_play"])
        held = {artifact["timeframe"]: artifact["bars"] for artifact in manifest["artifacts"]}
        self.assertEqual(held["daily"], len(self.frame))

    def test_it_holds_the_span_and_little_else(self) -> None:
        """Back to the quiet window, because the ratio is a comparison with it, and no further."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        panel = next(a for a in manifest["artifacts"] if a["timeframe"] == "power_play")
        earliest = min(
            question["baseline_first_session"] for question in self.questions
        )
        sessions = len(self.frame.loc[earliest:])
        self.assertLess(panel["bars"], len(self.frame) // 4)
        self.assertGreaterEqual(panel["bars"], sessions)

    def test_every_landmark_is_on_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        panel = next(a for a in manifest["artifacts"] if a["timeframe"] == "power_play")
        for question in self.questions:
            with self.subTest(top=question["peak_date"]):
                self.assertIn(question["peak_date"], panel["power_play_drawn"]["peak_date"])
                self.assertIn(
                    question["baseline_first_session"],
                    panel["power_play_drawn"]["baseline_first_session"],
                )

    def test_it_prints_the_ratio_because_its_bars_are_sessions(self) -> None:
        """A weekly bar is five sessions added together and the multiple is about one of them.
        This panel's bars are the sessions, so the number belongs on it."""
        span = _power_play_spans(self.frame, "digest")
        window = self.frame.loc[span["spans"][0]["baseline_first_session"]:]
        price, volume = RecordingAxis(), RecordingAxis()

        chart_module._draw_power_play(price, volume, window, span, "power_play")

        self.assertTrue([label for label in volume.labels if "x baseline" in label])

    def test_a_span_starting_past_the_last_bar_gets_no_panel(self) -> None:
        """Slicing from a start this frame does not reach hands back the final few sessions.

        They would be labelled the span, carry the landmarks' legend, and be measured for a
        flag depth -- a picture of the last week answering a question about a structure that is
        not on it. A panel that cannot hold the span is not a panel.
        """
        past_the_end = (self.frame.index[-1] + pd.Timedelta(days=30)).date().isoformat()
        real = chart_module._power_play_spans

        def beyond(daily, digest):
            answer = real(daily, digest)
            answer["spans"] = [
                dict(span, baseline_first_session=past_the_end, advance_anchor_date=past_the_end)
                for span in answer["spans"]
            ]
            return answer

        chart_module._power_play_spans = beyond
        try:
            with tempfile.TemporaryDirectory() as directory:
                manifest = _rendered(self.frame, directory)
                written = sorted(Path(directory).glob("*.png"))
        finally:
            chart_module._power_play_spans = real

        timeframes = [artifact["timeframe"] for artifact in manifest["artifacts"]]
        self.assertEqual(timeframes, ["weekly", "daily"])
        self.assertEqual(len(written), 2)

    def test_it_draws_no_moving_average(self) -> None:
        """An average over one span is not the one the daily panel draws at the same dates, and
        two pictures printing different lines under one name is the quiet disagreement this
        overlay exists to stop. Worse still: the weekly branch is the fallback, so a lapse here
        labels values computed from sessions as `SMA 10W`."""
        close = self.frame["Close"]

        self.assertEqual(chart_module._price_overlays(close, "power_play"), {})
        self.assertEqual(
            list(chart_module._price_overlays(close, "daily")), ["EMA 10", "EMA 21", "SMA 50"]
        )
        self.assertEqual(
            list(chart_module._price_overlays(close, "weekly")),
            ["SMA 10W", "SMA 30W", "SMA 40W"],
        )

    def test_the_lead_in_before_the_quiet_window_is_there(self) -> None:
        """A window that begins exactly at the baseline's first session puts that session on the
        left edge of the page, where a reader cannot tell a boundary from a crop."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        panel = next(a for a in manifest["artifacts"] if a["timeframe"] == "power_play")
        earliest = min(question["baseline_first_session"] for question in self.questions)
        self.assertEqual(panel["bars"], len(self.frame.loc[earliest:]) + 5)

    def test_a_stock_nobody_is_asking_about_gets_no_third_picture(self) -> None:
        plain, _ = base_series()
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(plain, directory)

        self.assertEqual(
            [artifact["timeframe"] for artifact in manifest["artifacts"]], ["weekly", "daily"]
        )
        self.assertNotIn("power_play", manifest["paths"])


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

        self.assertIn("heaviest advance session (6.0x baseline median)", volume.labels)

    def test_the_weekly_panel_marks_the_week_without_one(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        drawn = _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        self.assertTrue(drawn["advance_peak_volume_date"])
        self.assertIn("week of the heaviest advance session", volume.labels)
        self.assertFalse([label for label in volume.labels if "x baseline" in label])

    def test_no_weekly_label_calls_its_bar_a_session(self) -> None:
        """The multiple was the only place this rule had reached. On a real EDRY render the
        anchor was 2026-07-01 and the weekly rule sat on the bar labelled 2026-07-03 still
        saying "advance begins after this session", which puts the commencement two sessions
        after it happened -- on exactly the judgment the reader opened the picture to make. The
        baseline shade is worse: a boundary session's week is one bar, so the rectangle covers
        sessions the window ended before, and only the label can say so.
        """
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        labels = price.labels + volume.labels
        self.assertTrue(labels)
        for label in labels:
            with self.subTest(label=label):
                self.assertNotIn("this session", label)
        # Naming the week is not enough on its own -- the reader needs the session it holds,
        # since that is what the question and the daily panel are keyed on.
        anchored = [label for label in price.labels if label.startswith("advance begins")]
        self.assertEqual(len(anchored), 1)
        self.assertIn(str(self.span["spans"][0]["advance_anchor_date"]), anchored[0])
        shaded = [label for label in volume.labels if label.startswith("baseline volume")]
        self.assertEqual(len(shaded), 1)
        for edge in ("baseline_first_session", "baseline_last_session"):
            self.assertIn(str(self.span["spans"][0][edge]), shaded[0])

    def test_the_session_panels_still_say_this_session(self) -> None:
        """The qualification belongs to the weekly alone: on a session panel the bar under the
        rule is the session, and spelling the date out there is noise the daily does not need."""
        price, _volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, RecordingAxis(), self.frame, self.span, "daily")

        self.assertIn(
            "advance begins after this session",
            [label for label in price.labels if label.startswith("advance begins")],
        )

    def test_both_panels_name_each_landmark_rather_than_the_structure(self) -> None:
        """One shared "power play" entry leaves a reader looking at a star and a cross with
        nothing saying which is the top of the advance and which is the bottom of the flag."""
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        self.assertEqual(
            price.labels,
            ["advance begins after this session", "advance peak", "flag low"],
        )
        self.assertIn("baseline volume", volume.labels)

    def test_the_advance_start_is_a_rule_down_the_panel_not_a_dot_at_a_price(self) -> None:
        """It was a marker at the bar's low, and on AAOI's three years of history at $0-230 it
        could not be seen at all -- the one landmark the volume clause is a claim about."""
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        self.assertEqual(len(price.rules), 1)


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
                self.assertTrue(asked.issubset(set(artifact["power_play_drawn"]["peak_date"])))

    def test_two_tops_each_carry_their_own_date_on_the_picture(self) -> None:
        """The threshold case, and the ordinary one: a chain usually reads two tops.

        A rule that only names dates from three marks up leaves exactly this shape with two
        identical stars and two identical legend entries -- the commonest chain there is, and
        the one where a reader most needs to know which of the two they are answering about.
        """
        span = _power_play_spans(self.frame, "digest")
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, span, "daily")

        peaks = [label for label in price.labels if label.startswith("advance peak")]
        self.assertEqual(len(peaks), 2)
        for question in self.questions:
            with self.subTest(top=question["peak_date"]):
                self.assertIn(f"advance peak ({question['peak_date']})", peaks)

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

        drawn = _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        self.assertTrue(set(self.tops).issubset(set(drawn["peak_date"])))

    def test_a_landmark_the_readings_agree_on_is_reported_once(self) -> None:
        """These five share one advance, so the anchor is one bar and one date.

        Reported per reading, `power_play_drawn` says the anchor was drawn five times and the
        label names one session five times over -- a manifest counting what was available to put
        on the picture rather than what the picture holds, which is the contract it exists for.
        """
        price, volume = RecordingAxis(), RecordingAxis()

        drawn = _draw_power_play(price, volume, self.weekly, self.span, "weekly")

        for landmark, days in drawn.items():
            with self.subTest(landmark=landmark):
                self.assertEqual(len(days), len(set(days)))

    def test_a_shared_bar_prints_no_volume_multiple_the_readings_disagree_on(self) -> None:
        """One number beside a mark that stands for two readings names neither of them."""
        spans = [
            {**span, "advance_peak_volume_ratio": 6.0 + index}
            for index, span in enumerate(self.span["spans"][:2])
        ]
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, {"spans": spans}, "daily")

        self.assertEqual([label for label in volume.labels if "x baseline" in label], [])
        self.assertIn("heaviest advance session", volume.labels)

    def test_nor_one_two_baselines_happen_to_agree_on(self) -> None:
        """The multiple is a claim about a division, so both halves have to be one thing.

        Two readings that divided by different quiet windows can land on the same number, and
        checking only the number printed "6.0x" beside a mark standing for both -- with two
        shades under it, either of which the reader might check the arithmetic against.
        """
        windows = (("2026-01-29", "2026-03-25"), ("2026-01-30", "2026-03-24"))
        spans = [
            {**span, "advance_peak_volume_ratio": 6.0,
             "baseline_first_session": first, "baseline_last_session": last}
            for span, (first, last) in zip(self.span["spans"][:2], windows)
        ]
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, {"spans": spans}, "daily")

        self.assertEqual([label for label in volume.labels if "x baseline" in label], [])

    def test_flag_lows_that_share_a_week_mark_the_lowest_of_them(self) -> None:
        """The opposite edge from the peaks, and for the opposite reason: the cross stands for
        how far that week's readings fell, so the shallowest of them is the wrong end."""
        lows = ("2026-04-21", "2026-04-23")
        spans = [
            {**self.span["spans"][index], "flag_low_date": day, "flag_low": low}
            for index, (day, low) in enumerate(zip(lows, (18.9, 18.1)))
        ]
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.weekly, {"spans": spans}, "weekly")

        self.assertIn(18.1, [point[1] for point in price.points])
        self.assertNotIn(18.9, [point[1] for point in price.points])

    def test_baselines_that_land_on_the_same_weeks_are_one_shade(self) -> None:
        """Two entries behind one rectangle say the panel is showing something it is not."""
        windows = (("2026-01-29", "2026-03-25"), ("2026-01-30", "2026-03-24"))
        spans = [
            {**self.span["spans"][index], "baseline_first_session": first,
             "baseline_last_session": last}
            for index, (first, last) in enumerate(windows)
        ]
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.weekly, {"spans": spans}, "weekly")

        self.assertEqual(len(volume.spans), 1)
        # One rectangle, one entry, and the entry names what the rectangle covers -- the
        # earliest first session and the latest last, not the four boundary dates behind it.
        # Joining all four read "the weeks holding 2026-01-29 to 2026-03-25 to 2026-01-30 to
        # 2026-03-24", which describes no window at all.
        self.assertEqual(
            [label for label in volume.labels if label.startswith("baseline")],
            ["baseline volume -- the weeks holding 2026-01-29 to 2026-03-25"],
        )

    def test_the_daily_picture_keeps_one_mark_per_session(self) -> None:
        price, volume = RecordingAxis(), RecordingAxis()

        _draw_power_play(price, volume, self.frame, self.span, "daily")

        peaks = [label for label in price.labels if label.startswith("advance peak")]
        self.assertEqual(len(peaks), 5)
