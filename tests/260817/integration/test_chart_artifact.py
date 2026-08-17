from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest

import pandas as pd

from scripts.minervini.chart import render_chart_artifacts


FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "chart"


def completed_daily_ohlcv() -> pd.DataFrame:
    frame = pd.DataFrame(json.loads((FIXTURES / "completed_daily.json").read_text())).set_index("date")
    frame.index = pd.to_datetime(frame.index)
    return frame


class ChartArtifactPublicSeamTests(unittest.TestCase):
    def test_completed_daily_provider_data_renders_weekly_first_and_auditable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = render_chart_artifacts(
                completed_daily_ohlcv(),
                ticker="test",
                as_of="2026-08-14",
                output_dir=pathlib.Path(temporary),
            )

            self.assertEqual(result["ticker"], "TEST")
            self.assertEqual(result["as_of"], "2026-08-14")
            self.assertEqual([artifact["timeframe"] for artifact in result["artifacts"]], ["weekly", "daily"])
            self.assertEqual(len(result["input_sha256"]), 64)

            for artifact in result["artifacts"]:
                path = pathlib.Path(artifact["path"])
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)
                self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

            manifest_path = pathlib.Path(result["manifest_path"])
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["as_of"], "2026-08-14")
            self.assertEqual(manifest["renderer_version"], result["renderer_version"])
            self.assertEqual(manifest["input_sha256"], result["input_sha256"])
            self.assertEqual([artifact["path"] for artifact in manifest["artifacts"]], [artifact["path"] for artifact in result["artifacts"]])
            self.assertEqual(manifest["paths"], {artifact["timeframe"]: artifact["path"] for artifact in result["artifacts"]})

    def test_identical_completed_input_rewrites_the_same_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kwargs = {"ticker": "TEST", "as_of": "2026-08-14", "output_dir": pathlib.Path(temporary)}
            first = render_chart_artifacts(completed_daily_ohlcv(), **kwargs)
            first_hashes = {artifact["timeframe"]: hashlib.sha256(pathlib.Path(artifact["path"]).read_bytes()).hexdigest() for artifact in first["artifacts"]}

            second = render_chart_artifacts(completed_daily_ohlcv(), **kwargs)
            second_hashes = {artifact["timeframe"]: hashlib.sha256(pathlib.Path(artifact["path"]).read_bytes()).hexdigest() for artifact in second["artifacts"]}

            self.assertEqual(second, first)
            self.assertEqual(second_hashes, first_hashes)


if __name__ == "__main__":
    unittest.main()
