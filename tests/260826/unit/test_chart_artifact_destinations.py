"""Behavior checks for chart artifact destinations."""

from __future__ import annotations

from tests.providers import rows_snapshot
import json
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path
from scripts.minervini import chart as chart_module
from scripts.minervini.chart import ArtifactNameTaken
from tests.series import power_play_series
from ._chart_fixtures import _rendered


class ADestinationThatCannotHoldArtifacts(unittest.TestCase):
    def test_a_path_that_is_a_file_is_the_callers_to_change(self) -> None:
        """Unhandled, `[Errno 17] File exists` reached the caller as a defect in the renderer."""
        from scripts.minervini.contracts import RequestError
        from scripts.minervini.operations import Runtime, execute
        from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta

        frame = power_play_series()
        snapshot = rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True})
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
        snapshot = rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True})
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
        snapshot = rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True})
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
        snapshot = rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True})
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
