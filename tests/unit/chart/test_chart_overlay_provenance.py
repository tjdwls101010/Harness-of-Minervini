"""Behavior checks for chart overlay provenance."""

from __future__ import annotations

from tests.providers import rows_snapshot
import json
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from scripts.minervini import chart as chart_module
from scripts.minervini.chart import ArtifactNameTaken
from scripts.minervini.power_play_evidence import build_power_play_evidence, power_play_fingerprint
from scripts.minervini.setup_structure import bars_fingerprint
from tests.series import base_series, power_play_series
from tests.unit.chart._chart_fixtures import _rendered


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

        snapshot = rows_snapshot(self.frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=self.frame.index[-1].date(), coverage={"completed_only": True})
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

        snapshot = rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True})
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
