"""Behavior checks for operations watchlist."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from scripts.minervini.ledger import Ledger
from scripts.minervini.operations import Runtime, execute
from ._operation_fixtures import AS_OF


class OperationCompositionTests(unittest.TestCase):

    def test_ledger_reads_are_side_effect_free_and_record_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.sqlite3"
            runtime = Runtime(ledger_factory=lambda: Ledger(path))

            empty = execute("watchlist.show", {"as_of": AS_OF}, runtime=runtime)

            self.assertEqual(empty["data"]["records"], [])
            self.assertEqual(empty["as_of"]["date"], AS_OF)
            self.assertFalse(path.exists())

            output_hash = hashlib.sha256(b"fixture-output").hexdigest()
            recorded = execute(
                "watchlist.record",
                {
                    "ticker": "TEST",
                    "instrument_id": "nasdaq:NASDAQ:TEST",
                    "as_of": AS_OF,
                    "output_hash": output_hash,
                    "verdict": "WAIT",
                    "condition": "completed close above 100",
                    "invalidation": "close below 94",
                    "doctrine_ids": ["setup.vcp_supply"],
                    "evidence_quality": "partial",
                    "note": "fixture",
                },
                runtime=runtime,
            )

            self.assertEqual(recorded["status"], "ok")
            self.assertTrue(path.exists())
            self.assertEqual(recorded["side_effects"][0]["type"], "sqlite_write")
            self.assertEqual(execute("watchlist.history", {"ticker": "TEST"}, runtime=runtime)["data"]["events"][0]["operation"], "record")
