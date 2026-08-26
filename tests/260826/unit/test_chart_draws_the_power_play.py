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
import os
import tempfile
import unittest
import unittest.mock
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.minervini import chart as chart_module
from scripts.minervini.chart import (
    ArtifactNameTaken,
    _draw_power_play,
    _power_play_spans,
    render_chart_artifacts,
)
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


def _png_software(path) -> str | None:
    """What the PNG itself says drew it, read out of its own tEXt chunks."""

    raw = Path(path).read_bytes()
    offset = 8
    while offset + 8 <= len(raw):
        length = int.from_bytes(raw[offset:offset + 4], "big")
        kind = raw[offset + 4:offset + 8]
        body = raw[offset + 8:offset + 8 + length]
        if kind == b"tEXt":
            keyword, _, value = body.partition(b"\x00")
            if keyword == b"Software":
                return value.decode("latin-1")
        offset += 12 + length
    return None


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

    def test_the_files_are_named_by_the_overlay_too(self) -> None:
        """Same prices, different events, same directory: the second render wrote its picture
        over the first one's, and the first one's digests went on naming a file that had been
        replaced -- a reader holding that manifest looking at somebody else's overlay."""
        with tempfile.TemporaryDirectory() as directory:
            plain = _rendered(self.frame, directory)
            split = _rendered(self.split, directory)

            self.assertNotEqual(plain["manifest_path"], split["manifest_path"])
            self.assertNotEqual(set(plain["paths"].values()), set(split["paths"].values()))
            self.assertTrue(Path(plain["paths"]["daily"]).exists())
            self.assertTrue(Path(split["paths"]["daily"]).exists())

        for manifest in (plain, split):
            for path in manifest["paths"].values():
                with self.subTest(path=path):
                    self.assertIn(manifest["input_sha256"][:12], Path(path).name)
                    self.assertIn(manifest["power_play"]["measured_bars"][:8], Path(path).name)

    def test_the_recorded_side_effect_names_the_overlay_input_too(self) -> None:
        """What was written, and everything the file at that path depends on."""
        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        snapshot = ProviderSnapshot(
            self.frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=self.frame.index[-1].date(),
                coverage={"completed_only": True},
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            payload = execute(
                "ticker.chart",
                {
                    "ticker": "TEST",
                    "as_of": self.frame.index[-1].date().isoformat(),
                    "output_dir": directory,
                    "no_cache": True,
                },
                runtime=Runtime(price_history=lambda ticker, requested: snapshot),
            )

        artifacts = [item for item in payload["side_effects"] if item["type"] == "chart_artifact"]
        self.assertTrue(artifacts)
        for item in artifacts:
            with self.subTest(path=item["path"]):
                self.assertEqual(
                    item["power_play_measured_bars"],
                    payload["data"]["power_play"]["measured_bars"],
                )

    def test_a_name_two_inputs_reached_is_refused_rather_than_overwritten(self) -> None:
        """Both halves of the stamp are truncated, so a name is something two inputs can share.

        Thirty-two bits of the overlay half were reached in under four seconds by varying split
        multiples until two histories agreed -- one with a span, one without -- and the second
        render replaced the first's pictures while the first's manifest went on naming them.
        Widening the name moves the number; asking the directory settles it.
        """
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)
            written = Path(manifest["manifest_path"])
            collided = json.loads(written.read_text(encoding="utf-8"))
            collided["power_play"]["measured_bars"] = "f" * 64
            written.write_text(json.dumps(collided), encoding="utf-8")

            with self.assertRaises(ArtifactNameTaken) as caught:
                _rendered(self.frame, directory)

        self.assertIn(manifest["power_play"]["measured_bars"], str(caught.exception))

    def test_the_name_is_claimed_before_anything_is_drawn(self) -> None:
        """Asking first and writing after leaves a window three files wide.

        Two colliding renders both passed a check, then interleaved: the surviving manifest
        named a span while the surviving pictures had none, and the mismatch was answered as
        qualified. The claim is the manifest, so a second render meets it wherever in the
        first one's work it arrives -- here, before the first has written a single picture.
        """
        # A real collision, built rather than searched for: the same first eight characters the
        # name is cut to, and a different digest behind them.
        collided = power_play_fingerprint(self.frame)[:8] + "0" * 56
        self.assertNotEqual(collided, power_play_fingerprint(self.frame))
        drawn: list[str] = []
        real = chart_module._render_png

        def draw_the_second_render_first(bars, path, *args, **kwargs):
            if not drawn:
                drawn.append(str(path))
                with unittest.mock.patch.object(
                    chart_module, "power_play_fingerprint", return_value=collided
                ):
                    with self.assertRaises(ArtifactNameTaken):
                        _rendered(self.split, path.parent)
            return real(bars, path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.object(
                chart_module, "_render_png", draw_the_second_render_first
            ):
                manifest = _rendered(self.frame, directory)

            self.assertTrue(drawn)
            written = json.loads(Path(manifest["manifest_path"]).read_text(encoding="utf-8"))

        # The bundle the first render drew, whole: the interleaving left a manifest naming a
        # span with pictures that had none.
        self.assertEqual(written["power_play"]["measured_bars"], manifest["power_play"]["measured_bars"])
        self.assertTrue(written["artifacts"])

    def test_a_render_in_flight_puts_nothing_under_the_manifest_name(self) -> None:
        """Anything watching the directory reads that name, and read mid-render it was a
        manifest with no artifacts and no paths -- eight fields short, for the whole length of
        every render. The claim that covers the render is a file of its own."""
        seen: list[Any] = []
        real = chart_module._render_png

        def look_at_the_directory(bars, path, *args, **kwargs):
            seen.extend(sorted(item.name for item in path.parent.iterdir()))
            return real(bars, path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.object(
                chart_module, "_render_png", look_at_the_directory
            ):
                manifest = _rendered(self.frame, directory)

        self.assertTrue(seen)
        self.assertNotIn(Path(manifest["manifest_path"]).name, seen)

    def test_a_second_render_of_the_same_name_is_refused_while_the_first_draws(self) -> None:
        """One render inside a name at a time, decided by the filesystem rather than reasoned
        about. Overlapping renders were permitted for a long time -- the digests and the
        renderer agree, so nothing they wrote could disagree -- and every rule that tried to
        make cleanup safe under that permission fell to some interleaving of the two. Refusing
        costs the second caller a retry and buys the only thing those rules could not."""
        refused: list[BaseException] = []
        real = chart_module._render_png
        overtaking = False

        def render_the_same_input_again(bars, path, *args, **kwargs):
            nonlocal overtaking
            if not overtaking:
                overtaking = True
                try:
                    _rendered(self.frame, path.parent)
                except ArtifactNameTaken as caught:
                    refused.append(caught)
            return real(bars, path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.object(
                chart_module, "_render_png", render_the_same_input_again
            ):
                manifest = _rendered(self.frame, directory)

            standing = sorted(path.name for path in Path(directory).glob("*.reserving*"))

        self.assertEqual(len(refused), 1)
        self.assertIn("right now", str(refused[0]))
        self.assertEqual(sorted(manifest["paths"]), ["daily", "power_play", "weekly"])
        self.assertEqual(standing, [])

    def test_a_failing_render_never_takes_a_finished_manifest_with_it(self) -> None:
        """Nothing here deletes a manifest, and a bundle finished under this name is left whole
        even by the render that finds it while cleaning up after itself."""
        with tempfile.TemporaryDirectory() as directory:
            finished = _rendered(self.frame, directory)
            Path(finished["paths"]["weekly"]).unlink()

            real = chart_module._render_png
            calls = 0

            def fall_over_after_the_first(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("the plotting stack fell over")
                return real(*args, **kwargs)

            with unittest.mock.patch.object(
                chart_module, "_render_png", fall_over_after_the_first
            ):
                with self.assertRaises(RuntimeError):
                    _rendered(self.frame, directory)

            standing = Path(finished["manifest_path"]).exists()
            restored = Path(finished["paths"]["weekly"]).exists()
            claims = list(Path(directory).glob("*.reserving*"))

        self.assertTrue(standing)
        self.assertTrue(restored)
        self.assertEqual(claims, [])

    def test_a_colliding_vintage_is_refused_while_the_name_is_held(self) -> None:
        """The truncated halves of the stamp are shareable, so a different input can arrive at
        this name. It meets the claim rather than the pictures."""
        collided = power_play_fingerprint(self.frame)[:8] + "0" * 56
        real = chart_module._render_png
        overtaking = False
        refused: list[bool] = []

        def let_a_colliding_vintage_in(bars, path, *args, **kwargs):
            nonlocal overtaking
            if not overtaking:
                overtaking = True
                with unittest.mock.patch.object(
                    chart_module, "power_play_fingerprint", return_value=collided
                ):
                    try:
                        _rendered(self.split, path.parent)
                        refused.append(False)
                    except ArtifactNameTaken:
                        refused.append(True)
            return real(bars, path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.object(
                chart_module, "_render_png", let_a_colliding_vintage_in
            ):
                _rendered(self.frame, directory)

        self.assertEqual(refused, [True])

    def test_a_symlink_pointing_at_nothing_is_still_a_name_this_render_does_not_hold(self) -> None:
        """`exists` calls it absent, so the claim read as free and the write followed the link."""
        collided = power_play_fingerprint(self.frame)[:8] + "0" * 56
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(_rendered(self.frame, directory)["manifest_path"])
            manifest.unlink()
            manifest.symlink_to(Path(directory) / "a-file-that-was-never-written.json")

            with unittest.mock.patch.object(
                chart_module, "power_play_fingerprint", return_value=collided
            ):
                with self.assertRaises(ArtifactNameTaken):
                    _rendered(self.split, directory)

    def test_a_failed_render_does_not_leave_a_name_nobody_can_use(self) -> None:
        """The claim is this render's to take back."""
        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.object(
                chart_module, "_render_png", side_effect=RuntimeError("the plotting stack fell over")
            ):
                with self.assertRaises(RuntimeError):
                    _rendered(self.frame, directory)

            self.assertEqual(list(Path(directory).iterdir()), [])
            manifest = _rendered(self.frame, directory)

        self.assertTrue(manifest["artifacts"])

    def test_a_manifest_whose_overlay_block_is_not_a_block_is_refused(self) -> None:
        """Read one level deep, `power_play` was assumed to be an object and a string there
        raised an AttributeError the caller could do nothing with."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)
            written = Path(manifest["manifest_path"])
            written.write_text(
                json.dumps({"input_sha256": manifest["input_sha256"], "power_play": "gone"}),
                encoding="utf-8",
            )

            with self.assertRaises(ArtifactNameTaken):
                _rendered(self.frame, directory)

    def test_a_directory_it_cannot_write_is_the_callers_to_change(self) -> None:
        """`mkdir(exist_ok=True)` is happy with a directory that is already there, and the first
        write is several steps later -- so the caller got an internal_error for a destination
        they could have chosen differently."""
        from scripts.minervini.chart import UnusableOutputDirectory

        with tempfile.TemporaryDirectory() as directory:
            sealed = Path(directory) / "sealed"
            sealed.mkdir()
            sealed.chmod(0o500)
            try:
                with self.assertRaises(UnusableOutputDirectory):
                    _rendered(self.frame, sealed)
            finally:
                sealed.chmod(0o700)

    def test_valid_json_that_is_not_a_manifest_is_still_not_this_render(self) -> None:
        """Reaching into a list for a digest raised an AttributeError nobody could act on."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)
            Path(manifest["manifest_path"]).write_text("[]", encoding="utf-8")

            with self.assertRaises(ArtifactNameTaken):
                _rendered(self.frame, directory)

    def test_rendering_the_same_input_twice_still_writes_over_itself(self) -> None:
        """The check is about two inputs, not two runs."""
        with tempfile.TemporaryDirectory() as directory:
            first = _rendered(self.frame, directory)
            second = _rendered(self.frame, directory)

        self.assertEqual(first["manifest_path"], second["manifest_path"])

    def test_a_manifest_written_before_the_overlay_had_a_digest_is_not_a_collision(self) -> None:
        """It can only share a name with a render whose overlay has no digest either, and then
        the two agree about the bars, so the newer picture is the same picture redrawn."""
        bare = self.frame.drop(columns=["Stock Splits", "Dividends"])
        with tempfile.TemporaryDirectory() as directory:
            first = _rendered(bare, directory)
            written = Path(first["manifest_path"])
            older = json.loads(written.read_text(encoding="utf-8"))
            del older["power_play"]
            written.write_text(json.dumps(older), encoding="utf-8")

            second = _rendered(bare, directory)

        self.assertEqual(first["manifest_path"], second["manifest_path"])

    def _execute_a_render(self, frame, directory):
        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        snapshot = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True},
            ),
        )
        return execute(
            "ticker.chart",
            {
                "ticker": "TEST",
                "as_of": frame.index[-1].date().isoformat(),
                "output_dir": directory,
                "no_cache": True,
            },
            runtime=Runtime(price_history=lambda ticker, requested: snapshot),
        )

    def test_a_taken_name_reaches_the_caller_as_a_directory_they_can_move(self) -> None:
        """Unhandled, it became an internal_error with the request and the explicit as_of
        stripped off -- a name the caller could have changed, reported as a defect."""
        from scripts.minervini.contracts import RequestError

        collided = power_play_fingerprint(self.frame)[:8] + "0" * 56
        with tempfile.TemporaryDirectory() as directory:
            self._execute_a_render(self.frame, directory)

            with unittest.mock.patch.object(
                chart_module, "power_play_fingerprint", return_value=collided
            ):
                with self.assertRaises(RequestError) as caught:
                    self._execute_a_render(self.split, directory)

        self.assertEqual(caught.exception.args[1], "output_dir")

    def test_every_picture_it_wrote_is_reported_as_a_side_effect(self) -> None:
        """What was written, all of it. Reporting the first two of three is a file on disk that
        the envelope never admits to creating."""
        with tempfile.TemporaryDirectory() as directory:
            payload = self._execute_a_render(self.frame, directory)

        written = {item["path"] for item in payload["side_effects"] if item["type"] == "chart_artifact"}
        self.assertEqual(written, {artifact["path"] for artifact in payload["data"]["artifacts"]})
        self.assertEqual(len(written), 3)

    def test_every_side_effect_names_the_file_it_actually_identifies(self) -> None:
        """A side-effect record is what a reader carries away instead of the file. Both digests
        on every record, and both of them the manifest's own -- a record naming a digest the
        file does not hold identifies some other render, and nothing in the envelope would say
        so. The manifest record carried only the price digest while the pictures it lists
        carried both, though the manifest depends on the overlay's and is stamped with it."""
        with tempfile.TemporaryDirectory() as directory:
            payload = self._execute_a_render(self.frame, directory)
            manifest = json.loads(
                Path(payload["data"]["manifest_path"]).read_text(encoding="utf-8")
            )

        recorded = [
            item for item in payload["side_effects"]
            if item["type"] in ("chart_artifact", "artifact_manifest")
        ]
        self.assertEqual(len(recorded), 4)
        for item in recorded:
            with self.subTest(path=item["path"]):
                self.assertEqual(item["input_sha256"], manifest["input_sha256"])
                self.assertEqual(
                    item["power_play_measured_bars"], manifest["power_play"]["measured_bars"]
                )
                self.assertEqual(item["as_of"], manifest["as_of"])
        # And each record points at the kind of file its own type names.
        named = {item["type"]: item["path"] for item in recorded if item["type"] == "artifact_manifest"}
        self.assertEqual(named["artifact_manifest"], payload["data"]["manifest_path"])
        self.assertTrue(named["artifact_manifest"].endswith("_manifest.json"))

    def test_a_chart_that_drew_a_span_points_back_at_what_asked_for_it(self) -> None:
        """ticker.power-play sends a reader here; without the return leg an orchestrator that
        follows these lists draws the picture and has nowhere to carry the answer."""
        with tempfile.TemporaryDirectory() as directory:
            payload = self._execute_a_render(self.frame, directory)

        self.assertTrue(payload["data"]["power_play"]["spans"])
        self.assertIn("ticker.power-play", payload["next_capabilities"])

    def test_and_one_that_drew_none_does_not(self) -> None:
        """Nothing was asked, so there is nothing to go back and answer."""
        plain, _ = base_series()
        with tempfile.TemporaryDirectory() as directory:
            payload = self._execute_a_render(plain, directory)

        self.assertEqual(payload["data"]["power_play"]["spans"], [])
        self.assertNotIn("ticker.power-play", payload["next_capabilities"])

    def test_a_history_that_never_said_whether_a_split_occurred_names_nothing(self) -> None:
        """The same abstention the capability makes: absence is not a report of none."""
        bare = self.frame.drop(columns=["Stock Splits", "Dividends"])

        manifest = self._manifest(bare)

        self.assertIsNone(manifest["power_play"]["measured_bars"])
        self.assertEqual(manifest["power_play"]["spans"], [])


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


class ADestinationThatCannotHoldArtifacts(unittest.TestCase):
    def test_a_path_that_is_a_file_is_the_callers_to_change(self) -> None:
        """Unhandled, `[Errno 17] File exists` reached the caller as a defect in the renderer."""
        from scripts.minervini.contracts import RequestError
        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = power_play_series()
        snapshot = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True},
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            occupied = Path(directory) / "not-a-directory"
            occupied.write_text("", encoding="utf-8")

            with self.assertRaises(RequestError) as caught:
                execute(
                    "ticker.chart",
                    {
                        "ticker": "TEST",
                        "as_of": frame.index[-1].date().isoformat(),
                        "output_dir": str(occupied),
                        "no_cache": True,
                    },
                    runtime=Runtime(price_history=lambda ticker, requested: snapshot),
                )

        self.assertEqual(caught.exception.args[1], "output_dir")

    def test_something_sitting_where_a_picture_goes_is_the_callers_to_change_too(self) -> None:
        """The parent is writable and the manifest name is free, so every check before the
        drawing passes -- and the write then fails on `Is a directory`, which reached the caller
        as `internal_error`. That tells a reader the harness is broken when the path is."""
        from scripts.minervini.contracts import RequestError
        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = power_play_series()
        snapshot = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True},
            ),
        )
        request = {
            "ticker": "TEST",
            "as_of": frame.index[-1].date().isoformat(),
            "no_cache": True,
        }
        runtime = Runtime(price_history=lambda ticker, requested: snapshot)
        with tempfile.TemporaryDirectory() as directory:
            written = execute("ticker.chart", request | {"output_dir": directory}, runtime=runtime)
            taken = Path(written["data"]["artifacts"][0]["path"]).name

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / taken).mkdir()

            with self.assertRaises(RequestError) as caught:
                execute("ticker.chart", request | {"output_dir": directory}, runtime=runtime)

        self.assertEqual(caught.exception.args[1], "output_dir")

    def test_a_bundle_that_could_not_finish_leaves_nothing_behind(self) -> None:
        """The pictures are committed one at a time, so a bundle failing on its second left the
        first standing under a digest-stamped name -- a finished-looking artifact beside an
        envelope reporting no side effects, which is the reader's cue that nothing was written.
        Every name is this render's by the claim, so taking them back takes nothing else."""
        from scripts.minervini.contracts import RequestError
        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = power_play_series()
        snapshot = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True},
            ),
        )
        request = {
            "ticker": "TEST",
            "as_of": frame.index[-1].date().isoformat(),
            "no_cache": True,
        }
        runtime = Runtime(price_history=lambda ticker, requested: snapshot)
        with tempfile.TemporaryDirectory() as directory:
            written = execute("ticker.chart", request | {"output_dir": directory}, runtime=runtime)
            blocked = Path(written["data"]["paths"]["daily"]).name

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / blocked).mkdir()

            with self.assertRaises(RequestError):
                execute("ticker.chart", request | {"output_dir": directory}, runtime=runtime)

            left_behind = sorted(path.name for path in Path(directory).iterdir())

        self.assertEqual(left_behind, [blocked])

    def test_giving_up_the_claim_is_never_what_fails_a_finished_render(self) -> None:
        """Every disclosed artifact is on disk and the caller gets an exception instead of the
        paths naming them -- because the last thing the render does is give up its own claim,
        and that can fail on a destination that has finished taking changes. The claim left
        behind costs the next render of this name a refusal it can clear by hand; the
        alternative costs this caller a bundle it cannot find."""
        frame = power_play_series()
        real = Path.unlink

        def refuse_the_claim(self, *args, **kwargs):
            if ".reserving" in self.name:
                raise PermissionError("the claim cannot be removed")
            return real(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.object(Path, "unlink", refuse_the_claim):
                manifest = _rendered(frame, directory)

            written = sorted(path.name for path in Path(directory).glob("*.png"))
            claims = sorted(path.name for path in Path(directory).glob("*.reserving"))

        self.assertEqual(len(written), 3)
        self.assertEqual(len(claims), 1)
        self.assertEqual(sorted(manifest["paths"]), ["daily", "power_play", "weekly"])

    def test_a_render_that_gave_up_leaves_the_name_clear(self) -> None:
        """It holds the only claim while it draws, so with no finished manifest under this name
        nothing here is anybody's -- pictures this render committed, and any an earlier one that
        was killed left behind."""
        frame = power_play_series()
        with tempfile.TemporaryDirectory() as directory:
            real = chart_module._render_png
            calls = 0

            def fail_after_the_first(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("the picture failed")
                return real(*args, **kwargs)

            chart_module._render_png = fail_after_the_first
            try:
                with self.assertRaises(chart_module.UnusableOutputDirectory):
                    _rendered(frame, directory)
            finally:
                chart_module._render_png = real

            left_behind = sorted(path.name for path in Path(directory).iterdir())

        self.assertEqual(left_behind, [])

    def test_a_destination_that_will_not_take_the_claim_is_the_callers_too(self) -> None:
        """Taking the claim is already writing there. A filesystem that holds ordinary files but
        refuses hard links is answered by choosing a different directory, not by reporting that
        this harness is broken."""
        from scripts.minervini.contracts import RequestError
        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = power_play_series()
        snapshot = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                as_of=frame.index[-1].date(),
                coverage={"completed_only": True},
            ),
        )
        real_open = chart_module.os.open

        def refuse_the_claim(path, *args, **kwargs):
            if ".reserving" in str(path):
                raise PermissionError("the claim cannot be created")
            return real_open(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.object(chart_module.os, "open", refuse_the_claim):
                with self.assertRaises(RequestError) as caught:
                    execute(
                        "ticker.chart",
                        {
                            "ticker": "TEST",
                            "as_of": frame.index[-1].date().isoformat(),
                            "output_dir": directory,
                            "no_cache": True,
                        },
                        runtime=Runtime(price_history=lambda ticker, requested: snapshot),
                    )

            left_behind = sorted(path.name for path in Path(directory).iterdir())

        self.assertEqual(caught.exception.args[1], "output_dir")
        self.assertEqual(left_behind, [])


class RecordingAxis:
    """Keeps what was drawn on it and what each thing was called.

    The labels are the part under test here and a rendered PNG cannot be asked about them, so
    this is where the wording gets pinned."""

    def __init__(self) -> None:
        self.labels: list[str] = []
        self.spans: list[tuple] = []
        self.rules: list[Any] = []
        self.points: list[tuple] = []
        self.levels: list[tuple] = []
        # How each thing was drawn, not only that it was. A reviewer set every marker to size
        # zero and every rule to width zero and the whole suite passed: the drawing calls all
        # happened, and nothing on the picture could be seen.
        self.drawn: list[dict[str, Any]] = []

    def plot(self, x, y, **kwargs) -> None:
        self.points.append((x[0], float(y[0])))
        self.drawn.append(kwargs)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def axvline(self, position, **kwargs) -> None:
        self.rules.append(position)
        self.drawn.append(kwargs)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def axvspan(self, start, end, **kwargs) -> None:
        self.spans.append((start, end))
        self.drawn.append(kwargs)
        if kwargs.get("label"):
            self.labels.append(str(kwargs["label"]))

    def hlines(self, level, start, end, **kwargs) -> None:
        self.levels.append((float(level), start, end))
        self.drawn.append(kwargs)
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


def _panel_index(artifact, daily):
    """The bars the named panel actually drew, as an index."""
    if artifact["timeframe"] == "weekly":
        return (
            daily.resample("W-FRI")
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna()
            .index
        )
    if artifact["timeframe"] == "power_play":
        window = chart_module._span_window(daily, _power_play_spans(daily, "digest")["spans"])
        return window.index
    return daily.index


def artifact_end(artifact, daily):
    return _panel_index(artifact, daily)[-1]


class AClaimIsAFileNotAPathname(unittest.TestCase):
    """Reached by hand, because the sequence needs a directory swapped mid-render and there is
    no seam above these two functions that can do that between them.

    Giving the claim up by pathname is what makes the exclusive rule breakable from outside: the
    path a render took its claim under can be made to lead somewhere else, and the release then
    deletes whatever claim is standing at the new place -- a second render's live one. A third
    render walks in behind it, and two are inside one name, which is the state the whole rule
    exists to prevent.
    """

    def test_giving_up_the_claim_never_takes_somebody_else_s(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            started_in, replacement = root / "out", root / "other"
            started_in.mkdir()
            replacement.mkdir()

            name = "TEST_2026-08-26_abc_manifest.json.reserving"
            reserved = chart_module._reserve_the_name(started_in / name, "a" * 64, None)

            # Somebody else's live claim, in a directory that is about to answer to this path.
            (replacement / name).write_bytes(b'{"input_sha256":"b"}')
            started_in.rename(root / "moved")
            replacement.rename(started_in)

            chart_module._release(reserved)

            self.assertTrue((started_in / name).exists())
            self.assertEqual((started_in / name).read_bytes(), b'{"input_sha256":"b"}')


class AManifestNeverNamesAPictureThatIsNotThere(unittest.TestCase):
    """Published last and read first, so what it names has to be there when it is written.

    Two ways it was not. A picture can outlive the render that drew it -- killed before its
    manifest, its claim then deleted by hand as the refusal says to -- and the name it leaves
    behind is shareable, so the render that next takes it can draw a different set of panels and
    publish two paths with a stranded third beside them. And every write here resolves the
    destination by name, so a directory renamed mid-render splits the bundle across two
    directories while the manifest, written last, names all of it.
    """

    def test_a_picture_left_by_an_earlier_render_is_cleared_before_publishing(self) -> None:
        frame, _ = base_series()
        with tempfile.TemporaryDirectory() as directory:
            first = _rendered(frame, directory)
            self.assertEqual(sorted(first["paths"]), ["daily", "weekly"])
            standing = Path(first["manifest_path"])
            stem = standing.name.removesuffix("_manifest.json")
            # What a killed render of a colliding vintage leaves: a panel this input does not
            # draw, under this input's name, with nothing left to report it.
            stranded = standing.parent / f"{stem}_power_play.png"
            stranded.write_bytes(b"not really a picture")
            standing.unlink()

            second = _rendered(frame, directory)

            self.assertFalse(stranded.exists())
            self.assertEqual(sorted(second["paths"]), ["daily", "weekly"])
            self.assertTrue(all(Path(path).exists() for path in second["paths"].values()))

    def _render_losing(self, frame, directory, lose):
        """Render, and let `lose` happen to the destination once the last panel is drawn."""

        real = chart_module._render_png

        def draw_then_lose_it(bars, path, symbol, timeframe, *args, **kwargs):
            drawn = real(bars, path, symbol, timeframe, *args, **kwargs)
            if timeframe == "power_play":
                lose(path.parent)
            return drawn

        with unittest.mock.patch.object(chart_module, "_render_png", draw_then_lose_it):
            with self.assertRaises(chart_module.UnusableOutputDirectory) as refusal:
                _rendered(frame, directory)
        return refusal.exception

    def test_a_picture_that_stopped_being_there_refuses_instead_of_publishing(self) -> None:
        """Every panel, not the first one: checking only weekly leaves the two the reader is
        sent to the Power Play question for unchecked."""
        frame = power_play_series()
        for timeframe in ("weekly", "daily", "power_play"):
            with self.subTest(timeframe=timeframe), tempfile.TemporaryDirectory() as directory:
                # The destination moved: the earlier panels went to the directory that used to
                # answer to this path, and the later ones to whatever answers to it now.
                refusal = self._render_losing(
                    frame, directory,
                    lambda parent, timeframe=timeframe: next(
                        parent.glob(f"*_{timeframe}.png")
                    ).unlink(),
                )
                self.assertIn(f"_{timeframe}.png", str(refusal))
                self.assertIn(directory, str(refusal))
                self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), [])

    def test_a_directory_standing_where_a_picture_belongs_is_not_a_picture(self) -> None:
        """`exists` says yes to it, and a reader who opens it gets nothing. The manifest would
        have named it as the picture the Power Play question is answered from."""
        frame = power_play_series()

        def replace_the_weekly_with_a_directory(parent: Path) -> None:
            weekly = next(parent.glob("*_weekly.png"))
            weekly.unlink()
            weekly.mkdir()

        with tempfile.TemporaryDirectory() as directory:
            refusal = self._render_losing(frame, directory, replace_the_weekly_with_a_directory)
            left = sorted(path.name for path in Path(directory).iterdir())

        self.assertIn("_weekly.png", str(refusal))
        self.assertEqual(len(left), 1)
        self.assertTrue(left[0].endswith("_weekly.png"))

    def test_a_render_that_lost_its_own_claim_refuses_instead_of_publishing(self) -> None:
        """The claim is what says this is still the directory the render started in. Gone, the
        sweep below it would be clearing a name in somebody else's directory and the check
        would be reading somebody else's pictures -- both passing, since the names are the ones
        this render expects to find."""
        frame = power_play_series()

        with tempfile.TemporaryDirectory() as directory:
            refusal = self._render_losing(
                frame, directory,
                lambda parent: next(parent.glob("*.reserving")).unlink(),
            )
            published = list(Path(directory).glob("*_manifest.json"))

        self.assertIn("no longer the file at its own path", str(refusal))
        self.assertEqual(published, [])

    def test_rollback_in_a_directory_this_render_no_longer_holds_takes_nothing(self) -> None:
        """Refusing to publish was only half of it. Rollback runs next, and it sweeps this
        render's panel names -- which in the directory that now answers to this path are another
        render's live ones, drawn under its own claim. The refusal saved the manifest and the
        cleanup deleted the pictures."""
        frame = power_play_series()

        with tempfile.TemporaryDirectory() as outer:
            root = Path(outer)
            destination = root / "out"
            destination.mkdir()
            standing: list[Path] = []

            def swap_in_another_render(parent: Path) -> None:
                names = sorted(path.name for path in parent.iterdir())
                parent.rename(root / "moved")
                parent.mkdir()
                for name in names:
                    # The other render's own claim and its own three panels, under the names
                    # this render is about to go looking for.
                    (parent / name).write_bytes(b"the other render's work")
                    standing.append(parent / name)

            refusal = self._render_losing(frame, str(destination), swap_in_another_render)

            self.assertIn("no longer the file at its own path", str(refusal))
            self.assertEqual(len(standing), 4)
            for path in standing:
                with self.subTest(name=path.name):
                    self.assertTrue(path.exists())
                    self.assertEqual(path.read_bytes(), b"the other render's work")

    def test_what_the_caller_put_beside_the_bundle_is_not_this_render_s_to_take(self) -> None:
        """The sweep is for a panel this renderer wrote and abandoned. Reaching every
        `{stem}_*.png` it also took an annotated copy the caller had been working from."""
        frame, _ = base_series()
        with tempfile.TemporaryDirectory() as directory:
            first = _rendered(frame, directory)
            standing = Path(first["manifest_path"])
            stem = standing.name.removesuffix("_manifest.json")
            annotated = standing.parent / f"{stem}_annotated.png"
            annotated.write_bytes(b"the caller's own crop")
            standing.unlink()

            second = _rendered(frame, directory)

            self.assertTrue(annotated.exists())
            self.assertEqual(sorted(second["paths"]), ["daily", "weekly"])


class WhatARefusalTellsTheCallerToDo(unittest.TestCase):
    """A refusal is read by somebody who has to do something next, so the recovery it names is
    as much a published thing as the digests are -- and it survives review only because prose is
    the one part of this module a mutant can rewrite without a test noticing.

    Both messages had said something the round-14 rule made false. The claim refusal told a
    caller to wait and read the manifest, which is the right advice for exactly one of the three
    ways the render being waited on can end. The collision refusal offered to let the caller
    remove the file standing in the way as "a claim left behind" -- but claims are the .reserving
    file now, so the file it was pointing at is a finished bundle's manifest, and following it
    strips the pictures beside it of the only record of what drew them.
    """

    def setUp(self) -> None:
        self.frame = power_play_series()

    @staticmethod
    def _advice_to_remove_something(message: str) -> list[str]:
        return [
            sentence for sentence in message.replace("\n", " ").split(". ")
            if "delet" in sentence.lower() or "remove" in sentence.lower()
        ]

    def test_the_held_name_sends_the_caller_back_rather_than_promising_a_manifest(self) -> None:
        real = chart_module._render_png
        refused: list[ArtifactNameTaken] = []
        overtaking = False

        def render_the_same_input_again(bars, path, *args, **kwargs):
            nonlocal overtaking
            if not overtaking:
                overtaking = True
                try:
                    _rendered(self.frame, path.parent)
                except ArtifactNameTaken as caught:
                    refused.append(caught)
            return real(bars, path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.object(
                chart_module, "_render_png", render_the_same_input_again
            ):
                _rendered(self.frame, directory)

        self.assertEqual(len(refused), 1)
        message = str(refused[0])
        sentences = message.replace("\n", " ").split(". ")
        # Retrying is the one instruction true however the held render ends -- but only once it
        # has ended. Told to retry now, an automated caller spins against a live claim.
        retries = [sentence for sentence in sentences if "retry" in sentence.lower()]
        self.assertTrue(retries, message)
        for sentence in retries:
            with self.subTest(sentence=sentence):
                self.assertIn("once it ends", sentence)
        # A live render's claim is the thing standing between two writers in one name, and the
        # manifest beside it is a finished bundle nobody here may offer up.
        for sentence in sentences:
            if "delete" not in sentence.lower():
                continue
            with self.subTest(sentence=sentence):
                self.assertIn(".reserving", sentence)
                self.assertIn("no render is running", sentence)
        self.assertTrue(
            any(
                "manifest" in sentence and "never" in sentence and "remove" in sentence
                for sentence in sentences
            ),
            message,
        )

    def test_a_holder_it_could_not_read_is_not_reported_as_a_collision(self) -> None:
        """The message named three digests and asserted two inputs had met. It had read none of
        them: every identity it printed was `None`, because what stood at the name was not a
        manifest at all. A reader who trusts that goes looking for the other input."""
        with tempfile.TemporaryDirectory() as directory:
            finished = _rendered(self.frame, directory)
            Path(finished["manifest_path"]).write_text("[]", encoding="utf-8")

            with self.assertRaises(ArtifactNameTaken) as refusal:
                _rendered(self.frame, directory)

        message = str(refusal.exception)
        self.assertNotIn("None", message)
        self.assertIn("cannot read", message)
        self.assertIn(Path(finished["manifest_path"]).name, message)
        self.assertIn("another directory", message)

    def test_a_finished_bundle_in_the_way_is_never_offered_up_for_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            finished = _rendered(self.frame, directory)
            standing = Path(finished["manifest_path"])
            payload = json.loads(standing.read_text(encoding="utf-8"))
            payload["input_sha256"] = "b" * 64
            standing.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ArtifactNameTaken) as refusal:
                _rendered(self.frame, directory)

            # What is actually standing there, so the message is measured against a real bundle
            # rather than against the word "manifest".
            self.assertTrue(all(Path(path).exists() for path in finished["paths"].values()))

        message = str(refusal.exception)
        self.assertIn("another directory", message)
        self.assertEqual(self._advice_to_remove_something(message), [])


class TheRendererIsPartOfWhatTheNameClaims(unittest.TestCase):
    """The digests name what went in; this name is claimed for what comes out.

    The same bars through two versions of this module are two different pictures. With only the
    input in the name the second wrote its PNGs under the first's manifest, leaving a bundle
    whose manifest reported 1.2.0 beside a picture stamped 9.9.9.
    """

    def setUp(self) -> None:
        self.frame = power_play_series()

    def test_the_version_is_in_the_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)

        tag = f"-r{chart_module.RENDERER_VERSION.replace('.', '-')}_"
        named = list(manifest["paths"].values()) + [manifest["manifest_path"]]
        # The manifest too, and by the same stamp. It is the durable claim on the name, so a
        # version-stamped set of pictures beside an unstamped manifest is the one file in the
        # bundle a second renderer could still replace.
        self.assertEqual(len(named), 4)
        for path in named:
            with self.subTest(path=path):
                self.assertIn(tag, Path(path).name)
        stamps = {Path(path).name.split("_")[2] for path in named}
        self.assertEqual(len(stamps), 1)

    def test_a_bundle_from_another_version_is_refused_rather_than_replaced(self) -> None:
        """Reached by hand, because the name carries the version and the two cannot collide on
        their own -- what is under test is the check, which is what covers a manifest that
        arrived by some other route."""
        with tempfile.TemporaryDirectory() as directory:
            _rendered(self.frame, directory)
            standing = next(Path(directory).glob("*_manifest.json"))
            payload = json.loads(standing.read_text(encoding="utf-8"))
            payload["renderer_version"] = "9.9.9"
            standing.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(chart_module.ArtifactNameTaken) as refusal:
                _rendered(self.frame, directory)

        self.assertIn("9.9.9", str(refusal.exception))
        self.assertIn(chart_module.RENDERER_VERSION, str(refusal.exception))

    def test_the_picture_says_the_version_its_name_and_manifest_claim(self) -> None:
        """The name and the manifest are written by this module; the stamp inside the PNG is
        written by the renderer that actually drew it. They are three claims about one thing,
        and a reader holding a loose picture has only the third."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = _rendered(self.frame, directory)
            drawn_by = {
                timeframe: _png_software(path)
                for timeframe, path in manifest["paths"].items()
            }

        self.assertEqual(len(drawn_by), 3)
        for timeframe, software in drawn_by.items():
            with self.subTest(timeframe=timeframe):
                self.assertIsNotNone(software, "the PNG carries no Software stamp at all")
                vendor, _, version = software.partition("/")
                self.assertEqual(vendor, "minervini-chart")
                # Against the manifest and the name rather than the constant, because what is
                # under test is that the three agree -- a stamp read from the same constant the
                # name is built from would agree with it by construction.
                self.assertEqual(version, manifest["renderer_version"])
                self.assertIn(
                    f"-r{version.replace('.', '-')}_",
                    Path(manifest["paths"][timeframe]).name,
                )

    def test_a_manifest_finished_after_the_first_look_is_not_overwritten(self) -> None:
        """The durable check runs before anything is claimed, so a render already drawing can
        finish in the gap. It is asked again once the claim is held."""
        with tempfile.TemporaryDirectory() as directory:
            real = chart_module._reserve_the_name
            overtaking = False

            def finish_first(reserving, *args, **kwargs):
                nonlocal overtaking
                claim = real(reserving, *args, **kwargs)
                if not overtaking:
                    overtaking = True
                    standing = Path(str(reserving).removesuffix(".reserving"))
                    standing.write_text(
                        json.dumps({
                            "input_sha256": "a" * 64,
                            "renderer_version": chart_module.RENDERER_VERSION,
                            "power_play": {"measured_bars": None},
                        }),
                        encoding="utf-8",
                    )
                return claim

            chart_module._reserve_the_name = finish_first
            try:
                with self.assertRaises(chart_module.ArtifactNameTaken):
                    _rendered(self.frame, directory)
            finally:
                chart_module._reserve_the_name = real

            left_behind = sorted(path.name for path in Path(directory).glob("*.reserving"))

        self.assertEqual(left_behind, [])


if __name__ == "__main__":
    unittest.main()
