"""Two Minervini sentences bound a base's length, and the setup published only the wider one.

`setup.consolidation_footprint_3_to_60_weeks` is Chapter 10's general consolidation footprint;
`basecount.typical_base_duration_5_to_26_weeks` is Chapter 5's stage-2 base patterns. The
registry's own note on the second says the ranges "appear to describe overlapping but not
identical things" and leaves it to a reducer author to decide which applies where. Nobody
decided: `setup_evidence` measured `base_duration_weeks` once and read it against 3-60 only,
so the 5-26 band had `ticker.setup` in `consumers` and was never emitted.

Both apply, because the reading is one measurement against two standards rather than a choice
between them. A 32-week base sits inside 3-60 and past the upper edge of 5-26, and reporting
only "within range" is what the response standard forbids: a band names which edge is the
good one, and this base is on the wrong side of one of them.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.setup_structure import bars_fingerprint
from tests.series import anchor_dates, base_series


FOOTPRINT = "setup.consolidation_footprint_3_to_60_weeks"
STAGE_TWO_BASE = "basecount.typical_base_duration_5_to_26_weeks"
# Long enough that the two bands disagree: past 26 weeks, well inside 60.
# The extra sessions have to fit behind a completed session, so the series starts earlier.
LONG_BASE = {"declines": (30, 28, 25), "rallies": (28, 25, 22), "start": "2025-06-02"}


def run(**kwargs) -> dict:
    frame, anchors = base_series(**kwargs)
    meta = SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True})
    prices = ProviderSnapshot(frame, meta)
    request = {
        "ticker": "TEST",
        "as_of": prices.meta.as_of.isoformat(),
        "swing": anchor_dates(frame, anchors),
        "right_side_development": "constructive",
        "chain_completeness": "complete",
        "approved_bars": bars_fingerprint(prices.data),
        "entry_proximity": "at_pivot",
        "entry_price": float(prices.data["Close"].iloc[-1]),
        "no_cache": True,
    }
    return execute("ticker.setup", request, runtime=Runtime(price_history=lambda ticker, requested: prices))


def band(payload: dict, claim_id: str) -> dict:
    readings = [signal for signal in payload["signals"] if signal.get("doctrine_id") == claim_id and signal.get("role") == "band"]
    assert len(readings) == 1, f"{claim_id}: {len(readings)} band readings"
    return readings[0]


class OneMeasurementReachesBothStandards(unittest.TestCase):
    def test_a_short_base_is_reported_against_both_bands(self) -> None:
        payload = run()

        for claim_id in (FOOTPRINT, STAGE_TWO_BASE):
            with self.subTest(claim=claim_id):
                self.assertIn(claim_id, payload["doctrine_ids"])

    def test_both_bands_read_the_same_measured_duration(self) -> None:
        """One base has one length. Two readings that disagreed would be two measurements."""

        payload = run()

        self.assertEqual(band(payload, FOOTPRINT)["measured"], band(payload, STAGE_TWO_BASE)["measured"])

    def test_a_base_past_the_stage_two_edge_is_not_reported_as_within_range(self) -> None:
        payload = run(**LONG_BASE)
        footprint = band(payload, FOOTPRINT)
        stage_two = band(payload, STAGE_TWO_BASE)

        self.assertGreater(stage_two["measured"], 26)
        self.assertEqual(footprint["state"], "within_source_range")
        self.assertNotEqual(stage_two["state"], "within_source_range")
        self.assertEqual(stage_two["source_range"], [5, 26])

    def test_the_stage_two_band_carries_the_sentence_it_came_from(self) -> None:
        reading = band(run(), STAGE_TWO_BASE)

        self.assertIn("5 to 26 weeks", reading["quotation"])


if __name__ == "__main__":
    unittest.main()
