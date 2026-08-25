"""The chart the analyst approves from has to show what they are approving.

The detector's chain answers a required condition, and the flow asks a person to look at it and
declare it back. A chart without the anchors on it makes that approval a formality: you would be
agreeing to a list of dates while looking at a picture that never mentions them.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.minervini.chart import render_chart_artifacts
from tests.series import anchor_dates, base_series


class AnchorOverlayTests(unittest.TestCase):
    def test_the_manifest_records_the_anchors_that_were_drawn(self) -> None:
        frame, anchors = base_series()

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        self.assertEqual([item["date"] for item in manifest["segmentation"]["anchors"]], anchor_dates(frame, anchors))
        self.assertEqual(manifest["segmentation"]["state"], "resolved")

    def test_the_manifest_on_disk_carries_them_too(self) -> None:
        frame, _ = base_series()

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )
            written = json.loads(Path(manifest["manifest_path"]).read_text(encoding="utf-8"))

        self.assertEqual(written["segmentation"], manifest["segmentation"])

    def test_a_segmentation_the_detector_will_not_vouch_for_draws_nothing(self) -> None:
        """Drawing an unstable chain would show a person a structure the engine refuses to use."""

        frame, _ = base_series(depths=(25.0, 10.0, 1.2))

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        self.assertEqual(manifest["segmentation"]["state"], "unstable")
        self.assertEqual(manifest["segmentation"]["anchors"], [])


if __name__ == "__main__":
    unittest.main()
