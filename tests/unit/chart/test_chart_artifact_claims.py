"""Behavior checks for chart artifact claims."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from scripts.minervini import chart as chart_module
from tests.series import base_series, power_play_series
from tests.unit.chart._chart_fixtures import _png_software, _rendered


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
