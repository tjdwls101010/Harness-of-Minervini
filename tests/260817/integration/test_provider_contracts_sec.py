"""Behavior checks for provider contracts sec."""

from __future__ import annotations

import unittest
from scripts.minervini.providers.sec import select_filed_as_of


class ProviderContractTests(unittest.TestCase):

    def test_sec_selection_never_uses_a_filing_published_after_as_of(self) -> None:
        records = [
            {"value": 20, "filed_at": "2026-08-10", "form": "10-Q"},
            {"value": 30, "filed_at": "2026-08-15", "form": "10-Q"},
        ]

        selected = select_filed_as_of(records, "2026-08-12")

        self.assertEqual(selected, {"value": 20, "filed_at": "2026-08-10", "form": "10-Q"})
