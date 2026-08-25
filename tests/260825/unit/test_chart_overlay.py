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

    def test_the_chart_and_the_setup_answer_name_the_same_bars(self) -> None:
        """One fingerprint across both surfaces, so an approval can be traced to its picture."""

        frame, _ = base_series()

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        self.assertEqual(manifest["segmentation"]["bars_fingerprint"], manifest["input_sha256"])

    def test_the_weekly_chart_marks_the_week_a_swing_happened_in(self) -> None:
        """A Tuesday low has no Tuesday bar on a weekly chart, and it still happened.

        Requiring the anchor's own date to be a weekly session left almost every anchor off:
        the label is the week's Friday, so only a swing that landed exactly on one was drawn.
        """

        frame, anchors = base_series()
        declared = anchor_dates(frame, anchors)

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        drawn = {artifact["timeframe"]: artifact["anchors_drawn"] for artifact in manifest["artifacts"]}
        self.assertEqual(drawn["daily"], declared)
        self.assertEqual(drawn["weekly"], declared)

    def test_an_unvouched_segmentation_puts_nothing_on_either_timeframe(self) -> None:
        frame, _ = base_series(depths=(25.0, 10.0, 1.2))

        with tempfile.TemporaryDirectory() as directory:
            manifest = render_chart_artifacts(
                frame, ticker="TEST", as_of=frame.index[-1].date(), output_dir=directory
            )

        self.assertEqual([artifact["anchors_drawn"] for artifact in manifest["artifacts"]], [[], []])

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
