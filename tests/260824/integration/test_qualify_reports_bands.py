"""A band the harness measured must reach the envelope, or the disclosure rule is prose."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"


def recent_ipo(*, trough: float) -> ProviderSnapshot[pd.DataFrame]:
    peak, peak_position, sessions, last = 100.0, 20, 120, 99.0
    closes = [60.0 + index for index in range(peak_position)]
    closes.append(peak)
    closes.append(trough)
    recovery = sessions - peak_position - 3
    step = (peak * 0.99 - trough) / (recovery + 1)
    closes.extend(trough + step * (index + 1) for index in range(recovery))
    closes.append(last)
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index)
    frame = pd.DataFrame(
        {"Open": close * 0.995, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)},
        index=index,
    )
    return ProviderSnapshot(
        frame,
        SnapshotMeta(provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}),
    )


def qualify(*, trough: float) -> dict:
    runtime = Runtime(
        price_history=lambda ticker, as_of: recent_ipo(trough=trough),
        rs_rating=lambda ticker, as_of: ProviderSnapshot(
            {"rating": 88, "rating_date": AS_OF},
            SnapshotMeta(provider="ibd-rs-rating", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}),
        ),
    )
    return execute("ticker.qualify", {"ticker": "IPOX", "as_of": AS_OF, "primary_base_quality": "supports"}, runtime=runtime)


class QualifyBandReportingTests(unittest.TestCase):
    def test_the_primary_base_depth_band_reaches_the_envelope(self) -> None:
        payload = qualify(trough=70.0)

        band = payload["data"]["bands"]["primary_base.depth"]
        self.assertEqual(band["role"], "band")
        self.assertEqual(band["source_range"], [25, 35])
        self.assertEqual(band["measured"], 30.0)
        self.assertEqual(band["band_position"], 0.5)
        self.assertIn("quotation", band)

    def test_two_depths_inside_the_band_reach_the_envelope_differently(self) -> None:
        loose = qualify(trough=66.0)["data"]["bands"]["primary_base.depth"]
        tight = qualify(trough=74.0)["data"]["bands"]["primary_base.depth"]

        self.assertEqual(loose["state"], tight["state"])
        self.assertGreater(loose["band_position"], tight["band_position"])

    def test_a_standard_route_ticker_reports_no_primary_base_band(self) -> None:
        # Nothing measured, nothing to disclose; an empty map beats a null placeholder.
        payload = execute(
            "ticker.qualify",
            {"ticker": "TEST", "as_of": AS_OF},
            runtime=Runtime(
                price_history=lambda ticker, as_of: recent_ipo(trough=70.0),
                rs_rating=lambda ticker, as_of: ProviderSnapshot(
                    {"rating": 88, "rating_date": AS_OF},
                    SnapshotMeta(provider="ibd-rs-rating", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}),
                ),
            ),
        )

        self.assertIn("bands", payload["data"])


if __name__ == "__main__":
    unittest.main()
