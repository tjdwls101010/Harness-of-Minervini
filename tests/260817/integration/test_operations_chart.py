"""Behavior checks for operations chart."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from scripts.minervini.operations import Runtime, execute
from ._operation_fixtures import AS_OF, price_snapshot, stale_price_snapshot


class OperationCompositionTests(unittest.TestCase):

    def test_chart_writes_no_artifact_from_a_session_behind_price_history(self) -> None:
        runtime = Runtime(price_history=lambda ticker, as_of: stale_price_snapshot())

        payload = execute("ticker.chart", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["side_effects"], [])
        self.assertIn("completed_price_evidence", {item["id"] for item in payload["missing"]})

    def test_chart_operation_records_each_explicit_artifact_side_effect(self) -> None:
        runtime = Runtime(price_history=lambda ticker, as_of: price_snapshot())
        with tempfile.TemporaryDirectory() as temporary:
            payload = execute(
                "ticker.chart",
                {"ticker": "TEST", "as_of": AS_OF, "output_dir": temporary},
                runtime=runtime,
            )

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data"]["ticker"], "TEST")
            self.assertEqual([item["timeframe"] for item in payload["data"]["artifacts"]], ["weekly", "daily"])
            self.assertEqual({item["type"] for item in payload["side_effects"]}, {"chart_artifact", "artifact_manifest"})
            self.assertTrue(all(Path(item["path"]).exists() for item in payload["side_effects"]))
