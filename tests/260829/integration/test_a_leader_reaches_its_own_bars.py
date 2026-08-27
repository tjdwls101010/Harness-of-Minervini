"""The market snapshot fetches each ranked leader's own history and measures from it.

Slice 5-A ended the caller-supplied behavior word inside the evidence adapter.  This is the
other half: without a live path that actually reads a leader's bars, the adapter's measurement
is reachable only from a test, and the snapshot goes on publishing `unavailable` for every
leader forever.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta


AS_OF = "2025-12-31"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures"


def _frame(values: np.ndarray, *, as_of: str = AS_OF) -> pd.DataFrame:
    close = pd.Series(values, index=pd.bdate_range(end=as_of, periods=len(values)))
    return pd.DataFrame(
        {
            "Open": close * 0.995,
            "High": close * 1.002,
            "Low": close * 0.998,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000),
        },
        index=close.index,
    )


def _snapshot(frame: pd.DataFrame, *, as_of: str = AS_OF) -> ProviderSnapshot[pd.DataFrame]:
    return ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date.fromisoformat(as_of),
            coverage={"completed_only": True},
        ),
    )


def _rows(provider: str, rows: list[dict[str, object]]) -> ProviderSnapshot[list[dict[str, object]]]:
    return ProviderSnapshot(
        rows,
        SnapshotMeta(
            provider=provider,
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date.fromisoformat(AS_OF),
        ),
    )


class LeaderHistoryReachesTheSnapshotTests(unittest.TestCase):
    def _runtime(self, price_history) -> Runtime:
        return Runtime(
            price_history=price_history,
            finviz_breadth=lambda as_of: (_ for _ in ()).throw(
                ProviderUnavailable("finviz", "fixture_withholds_breadth", operation="raw_snapshot")
            ),
            sector_ranking=lambda as_of: _rows("ibd-rs-rating", [{"sector": "Zeta Technology", "avg_rs": 92.0, "count": 20}]),
            industry_ranking=lambda as_of: _rows(
                "ibd-rs-rating", [{"industry": "Semiconductors", "sector": "Zeta Technology", "avg_rs": 95.0, "count": 8}]
            ),
            market_leaders=lambda as_of, limit: _rows(
                "ibd-rs-rating",
                [{"ticker": "NEARHIGH", "rs_rating": 99, "rs_raw": 4.2}, {"ticker": "BROKEN", "rs_rating": 97, "rs_raw": 3.9}],
            ),
        )

    def test_each_leader_is_measured_from_the_history_the_runtime_returns_for_it(self) -> None:
        rising = _frame(np.linspace(50, 150, 300))
        # A peak at 200 followed by a slide to 100 is a 50% correction: past the source ceiling.
        broken = _frame(np.concatenate([np.linspace(80, 200, 150), np.linspace(200, 100, 150)]))

        def prices(ticker: str, as_of: str) -> ProviderSnapshot[pd.DataFrame]:
            return _snapshot({"QQQ": rising, "NEARHIGH": rising, "BROKEN": broken}[ticker])

        payload = execute(
            "market.snapshot",
            {"as_of": AS_OF, "trade_traction": "supports", "leader_limit": 10},
            runtime=self._runtime(prices),
        )

        leaders = {leader["ticker"]: leader for leader in payload["data"]["leaders"]}
        self.assertEqual(leaders["NEARHIGH"]["behavior"]["state"], "supports")
        self.assertEqual(leaders["BROKEN"]["behavior"]["state"], "contradicts")
        self.assertEqual(leaders["BROKEN"]["behavior"]["reason"], "correction_deeper_than_the_source_ceiling")
        # The fixture's peak high is 200 x 1.002 and its trough low is 100 x 0.998.
        self.assertAlmostEqual(leaders["BROKEN"]["correction_depth"]["measured"], 50.1996, places=3)

    def test_a_leader_whose_history_is_unavailable_is_named_in_missing_and_measured_by_nobody(self) -> None:
        rising = _frame(np.linspace(50, 150, 300))

        def prices(ticker: str, as_of: str) -> ProviderSnapshot[pd.DataFrame]:
            if ticker == "BROKEN":
                raise ProviderUnavailable("fixture-prices", "history_withheld", operation="daily_bars")
            return _snapshot(rising)

        payload = execute(
            "market.snapshot",
            {"as_of": AS_OF, "trade_traction": "supports", "leader_limit": 10},
            runtime=self._runtime(prices),
        )

        leaders = {leader["ticker"]: leader for leader in payload["data"]["leaders"]}
        self.assertEqual(leaders["NEARHIGH"]["behavior"]["state"], "supports")
        self.assertEqual(leaders["BROKEN"]["behavior"], {"state": "unavailable", "reason": "leader_price_history_not_read"})
        withheld = [item for item in payload["missing"] if item.get("ticker") == "BROKEN"]
        self.assertEqual([item["reason"] for item in withheld], ["history_withheld"])
        self.assertFalse(withheld[0]["required"])

    def test_a_leader_history_that_stopped_short_of_the_session_is_not_measured_from(self) -> None:
        rising = _frame(np.linspace(50, 150, 300))
        behind = _frame(np.linspace(50, 150, 300), as_of="2025-12-30")

        def prices(ticker: str, as_of: str) -> ProviderSnapshot[pd.DataFrame]:
            if ticker == "BROKEN":
                return ProviderSnapshot(
                    behind,
                    SnapshotMeta(
                        provider="fixture-prices",
                        retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                        as_of=date(2025, 12, 30),
                        coverage={"completed_only": True, "requested_session": AS_OF, "last_completed_bar": "2025-12-30"},
                        stale=True,
                    ),
                )
            return _snapshot(rising)

        payload = execute(
            "market.snapshot",
            {"as_of": AS_OF, "trade_traction": "supports", "leader_limit": 10},
            runtime=self._runtime(prices),
        )

        leaders = {leader["ticker"]: leader for leader in payload["data"]["leaders"]}
        self.assertEqual(leaders["BROKEN"]["behavior"], {"state": "unavailable", "reason": "leader_price_history_not_read"})
        self.assertIn("completed_price_evidence", {item["id"] for item in payload["missing"] if item.get("ticker") == "BROKEN"})


if __name__ == "__main__":
    unittest.main()
