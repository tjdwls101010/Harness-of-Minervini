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

from scripts.minervini.chart import _draw_power_play, _power_play_span, render_chart_artifacts
from scripts.minervini.power_play import measure_power_play
from scripts.minervini.power_play_evidence import compile_power_play_spec
from tests.series import base_series, power_play_series


def _rendered(frame, directory):
    return render_chart_artifacts(
        frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
    )


class TheChartCarriesTheStructureItAsksAbout(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = power_play_series()
        self.measured = measure_power_play(self.frame, compile_power_play_spec())

    def test_the_fixture_really_is_a_measurable_power_play(self) -> None:
        self.assertIsNone(self.measured["rejection"])
        self.assertEqual(self.measured["advance_anchor_date"], "2026-03-26")
        self.assertEqual(self.measured["peak_date"], "2026-04-30")

    def test_the_manifest_carries_the_span_the_numbers_were_read_from(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        power_play = manifest["power_play"]
        self.assertEqual(power_play["drawn_because"], "advance_gates_met")
        self.assertEqual(power_play["advance_anchor_date"], self.measured["advance_anchor_date"])
        self.assertEqual(power_play["peak_date"], self.measured["peak_date"])
        self.assertEqual(power_play["flag_low_date"], self.measured["flag_low_date"])
        self.assertEqual(power_play["advance_peak_volume_date"], self.measured["advance_peak_volume_date"])
        self.assertEqual(power_play["baseline_first_session"], self.measured["baseline_first_session"])
        self.assertEqual(power_play["baseline_last_session"], self.measured["baseline_last_session"])

    def test_it_names_one_set_of_bars_with_everything_else_on_the_page(self) -> None:
        """An approval cites the digest, so a span measured from other bars than the picture
        was cut from is the same failure the segmentation digest exists to prevent."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        self.assertEqual(manifest["power_play"]["bars_fingerprint"], manifest["input_sha256"])

    def test_each_picture_reports_which_landmarks_it_actually_shows(self) -> None:
        """The same contract the anchors already keep: what the picture contains, not what was
        available to put in it. A weekly chart that does not reach a session cannot mark it."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        for artifact in manifest["artifacts"]:
            with self.subTest(timeframe=artifact["timeframe"]):
                self.assertIn("power_play_drawn", artifact)
                self.assertIn(self.measured["peak_date"], artifact["power_play_drawn"])
                self.assertIn(self.measured["advance_anchor_date"], artifact["power_play_drawn"])

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

    def plot(self, _x, _y, **kwargs) -> None:
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
        self.span = _power_play_span(self.frame, "irrelevant-digest")
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


class AStockWithNoSuchStructure(unittest.TestCase):
    """Drawing is not the same as claiming.

    The arithmetic succeeds on any history: an ordinary base has a highest bar, a first bar of
    its rise and a quiet window before it. Reporting those as a Power Play span would put a
    claim on the picture that no measurement made, and a reader who came to that chart for
    some other reason would be looking at a structure nobody said was there."""

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

    def test_so_nothing_is_drawn_and_the_manifest_says_it_was_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        self.assertIsNone(manifest["power_play"]["drawn_because"])
        for artifact in manifest["artifacts"]:
            with self.subTest(timeframe=artifact["timeframe"]):
                self.assertEqual(artifact["power_play_drawn"], [])
                self.assertFalse(artifact["heaviest_advance_session_drawn"])

    def test_an_advance_that_took_too_long_is_not_one_either(self) -> None:
        """Both gates, not just the size. The source bounds how long the move may take, and a
        stock that doubled at a stroll did not do it explosively.

        Forty-five sessions of rise fills the measurement's advance window, so the move is read
        from as far back as it looks and still runs the full eight weeks -- clearing the size
        gate and failing the duration one, which is the pair this test needs."""
        slow = power_play_series(advance_sessions=45, advance_pct=160.0, dormancy_sessions=60)
        measured = measure_power_play(slow, compile_power_play_spec())
        self.assertGreaterEqual(measured["advance_pct"], 100)
        self.assertGreaterEqual(measured["advance_weeks"], 8)

        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(slow, directory)

        self.assertIsNone(manifest["power_play"]["drawn_because"])


if __name__ == "__main__":
    unittest.main()
