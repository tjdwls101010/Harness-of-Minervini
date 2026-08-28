"""The schema directory is generated except for the one file that indexes it.

`synchronize()` writes one schema per capability and never touched `catalog.json`, so the
index beside twenty generated files was hand-maintained. Adding a capability left it stale,
and the only thing that noticed was a test three directories away comparing two sets -- which
tells you the catalog is wrong without telling you that regenerating cannot fix it.

A generator that writes all but one of its own artifacts is worse than one that writes none:
running it looks like it brought the directory up to date.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import tempfile
import unittest

from scripts.minervini.capabilities import CAPABILITIES
from scripts.minervini.schema_sync import synchronize


PUBLISHED = pathlib.Path(__file__).resolve().parents[3] / "schemas" / "v2"


@contextlib.contextmanager
def generated():
    """A fresh generation, in a directory nothing else has ever written to."""

    with tempfile.TemporaryDirectory() as temporary:
        directory = pathlib.Path(temporary) / "v2"
        directory.mkdir(parents=True)
        synchronize(directory)
        yield directory


class TheGeneratorOwnsTheWholeDirectory(unittest.TestCase):
    def test_the_catalog_is_generated_rather_than_maintained_by_hand(self) -> None:
        """Bytes, not parsed objects.

        The published file is what other tools read, so key order, indentation, the trailing
        newline and the escaping are part of what has to be reproducible. Comparing parsed
        objects would let a generator that formats differently pass while every regeneration
        rewrote the file.
        """

        with generated() as directory:
            self.assertTrue((directory / "catalog.json").exists(), "synchronize() left its own index behind")
            self.assertEqual(
                (directory / "catalog.json").read_bytes(),
                (PUBLISHED / "catalog.json").read_bytes(),
            )

    def test_every_file_the_catalog_names_is_one_the_generator_wrote(self) -> None:
        """Checked in the generated directory, which is the only place that proves anything.

        Looking for the named files under the checked-in directory instead was the same defect
        this test exists to catch, one level up: a generator that wrote the index and nothing
        else would have passed, because the files it skipped were already sitting there.
        """

        with generated() as directory:
            catalog = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(set(catalog["capabilities"]), set(CAPABILITIES))
            for name, entry in catalog["capabilities"].items():
                with self.subTest(capability=name):
                    self.assertTrue((directory / entry["schema_file"]).exists())
                    self.assertTrue(entry["schema_id"].endswith(entry["schema_file"]))


if __name__ == "__main__":
    unittest.main()
