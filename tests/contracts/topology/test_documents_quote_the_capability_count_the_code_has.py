from tests.paths import ROOT

import re
import unittest

from scripts.minervini.capabilities import CAPABILITIES


class DocumentsDescribeThePublishedInterface(unittest.TestCase):
    def test_documents_quote_the_capability_count_the_code_has(self) -> None:
        schema_count = len(list((ROOT / "schemas/v2").glob("*.schema.json"))) - 1
        for filename, pattern, expected in (
            ("README.md", r"(\d+) versioned schemas", schema_count),
            ("CHANGELOG.md", r"(\d+) capabilities expose", len(CAPABILITIES)),
        ):
            with self.subTest(document=filename):
                match = re.search(pattern, (ROOT / filename).read_text(encoding="utf-8"))
                self.assertIsNotNone(match, f"{filename} must state the current interface count")
                self.assertEqual(int(match.group(1)), expected)
