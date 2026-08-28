"""The schema directory is generated except for the one file that indexes it.

`synchronize()` writes one schema per capability and never touched `catalog.json`, so the
index beside twenty generated files was hand-maintained. Adding a capability left it stale,
and the only thing that noticed was a test three directories away comparing two sets -- which
tells you the catalog is wrong without telling you that regenerating cannot fix it.

A generator that writes all but one of its own artifacts is worse than one that writes none:
running it looks like it brought the directory up to date.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.minervini.capabilities import CAPABILITIES
from scripts.minervini.schema_sync import synchronize


PUBLISHED = pathlib.Path(__file__).resolve().parents[3] / "schemas" / "v2"


def generated() -> pathlib.Path:
    directory = pathlib.Path(tempfile.mkdtemp()) / "v2"
    directory.mkdir(parents=True)
    synchronize(directory)
    return directory


class TheGeneratorOwnsTheWholeDirectory(unittest.TestCase):
    def test_the_catalog_is_generated_rather_than_maintained_by_hand(self) -> None:
        catalog = generated() / "catalog.json"

        self.assertTrue(catalog.exists(), "synchronize() left the index it publishes beside")
        self.assertEqual(
            json.loads(catalog.read_text(encoding="utf-8")),
            json.loads((PUBLISHED / "catalog.json").read_text(encoding="utf-8")),
        )

    def test_the_generated_catalog_names_every_capability_and_its_file(self) -> None:
        catalog = json.loads((generated() / "catalog.json").read_text(encoding="utf-8"))

        self.assertEqual(set(catalog["capabilities"]), set(CAPABILITIES))
        for name, entry in catalog["capabilities"].items():
            with self.subTest(capability=name):
                self.assertTrue((PUBLISHED / entry["schema_file"]).exists())
                self.assertTrue(entry["schema_id"].endswith(entry["schema_file"]))


if __name__ == "__main__":
    unittest.main()
