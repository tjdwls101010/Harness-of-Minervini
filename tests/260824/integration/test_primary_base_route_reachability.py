"""Every branch the Primary Base doctrine declares must be reachable from the interface."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


AS_OF = "2025-12-31"


def recent_ipo_history(*, trough: float, last: float) -> ProviderSnapshot[pd.DataFrame]:
    """A 120-session listing: a peak at 100, a correction to ``trough``, then a recovery."""

    peak, peak_position = 100.0, 20
    closes = [60.0 + index for index in range(peak_position)]
    closes.append(peak)
    closes.append(trough)
    # The recovery stops just under the peak so the only bar that can clear the
    # all-time high is the last one, which is what `last` decides.
    recovery = 120 - peak_position - 3
    step = (peak * 0.99 - trough) / (recovery + 1)
    closes.extend(trough + step * (index + 1) for index in range(recovery))
    closes.append(last)
    index = pd.bdate_range(end=AS_OF, periods=len(closes))
    close = pd.Series(closes, index=index)
    frame = pd.DataFrame(
        {
            "Open": close * 0.995,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000),
        },
        index=index,
    )
    return ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date.fromisoformat(AS_OF),
            coverage={"completed_only": True},
        ),
    )


def qualify(*, trough: float, last: float, **judgments: str) -> dict:
    runtime = Runtime(
        price_history=lambda ticker, as_of: recent_ipo_history(trough=trough, last=last),
        rs_rating=lambda ticker, as_of: ProviderSnapshot(
            {"rating": 88, "rating_date": AS_OF},
            SnapshotMeta(
                provider="ibd-rs-rating",
                retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                as_of=date.fromisoformat(AS_OF),
                coverage={"completed_only": True},
            ),
        ),
    )
    return execute("ticker.qualify", {"ticker": "IPOX", "as_of": AS_OF, **judgments}, runtime=runtime)


class PrimaryBaseReachabilityTests(unittest.TestCase):
    def test_a_base_below_its_all_time_high_is_incomplete_without_a_chart_judgment(self) -> None:
        payload = qualify(trough=75.0, last=99.0, primary_base_quality="supports")

        self.assertEqual(payload["data"]["route"], "recent_ipo_primary_base")
        self.assertEqual(payload["data"]["eligibility_state"], "incomplete")

    def test_a_confirmed_consolidation_near_the_all_time_high_reaches_eligible(self) -> None:
        payload = qualify(
            trough=75.0,
            last=99.0,
            primary_base_quality="supports",
            primary_base_emergence="near_high_consolidation",
        )

        self.assertEqual(payload["data"]["eligibility_state"], "eligible")

    def test_a_confirmed_year_long_correction_reaches_eligible_at_forty_five_percent_deep(self) -> None:
        payload = qualify(
            trough=55.0,
            last=101.0,
            primary_base_quality="supports",
            primary_base_long_correction="confirmed",
        )

        self.assertEqual(payload["data"]["eligibility_state"], "eligible")

    def test_an_unconfirmed_deep_base_stays_incomplete(self) -> None:
        payload = qualify(trough=55.0, last=101.0, primary_base_quality="supports")

        self.assertEqual(payload["data"]["eligibility_state"], "incomplete")


if __name__ == "__main__":
    unittest.main()
