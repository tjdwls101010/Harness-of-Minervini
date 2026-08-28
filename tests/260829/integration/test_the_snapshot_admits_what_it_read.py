"""The snapshot envelope cites every claim its own payload names.

`doctrine_ids` was the literal `["scope.data_integrity"]` on this capability, unchanged whether
the payload measured a leader's correction against the source's ceiling or measured nothing at
all. A reader following the citation found the one claim that is always true of every envelope
and none of the ones the numbers actually came from.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.minervini.clock import resolve_as_of
from scripts.minervini.doctrine import get_claim
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta


TODAY = resolve_as_of().date


def _frame(values: np.ndarray) -> pd.DataFrame:
    close = pd.Series(values, index=pd.bdate_range(end=TODAY, periods=len(values)))
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)},
        index=close.index,
    )


def _price(frame: pd.DataFrame) -> ProviderSnapshot[pd.DataFrame]:
    return ProviderSnapshot(
        frame,
        SnapshotMeta(provider="yfinance", retrieved_at=datetime.now(timezone.utc), as_of=TODAY, coverage={"completed_only": True}),
    )


def _rs(rows: list[dict[str, object]]) -> ProviderSnapshot[list[dict[str, object]]]:
    return ProviderSnapshot(rows, SnapshotMeta(provider="ibd-rs-rating", retrieved_at=datetime.now(timezone.utc), as_of=TODAY))


def _runtime() -> Runtime:
    rising = np.array([100.0 + index * 0.2 for index in range(300)])
    return Runtime(
        price_history=lambda ticker, as_of: _price(_frame(rising)),
        current_classification=lambda symbol: ProviderSnapshot(
            {"symbol": symbol, "sector": "Technology", "industry": "Semiconductors"},
            SnapshotMeta(
                provider="yfinance",
                retrieved_at=datetime.now(timezone.utc),
                as_of=TODAY,
                coverage={"kind": "current_classification_only", "historical": False},
            ),
        ),
        finviz_breadth=lambda as_of: (_ for _ in ()).throw(
            ProviderUnavailable("finviz", "fixture_withholds_breadth", operation="raw_snapshot")
        ),
        sector_ranking=lambda as_of: _rs([{"sector": "Technology", "avg_rs": 92.0, "count": 20}]),
        industry_ranking=lambda as_of: _rs([{"industry": "Semiconductors", "sector": "Technology", "avg_rs": 95.0, "count": 8}]),
        market_leaders=lambda as_of, limit: _rs([{"ticker": "LEAD", "rs_rating": 99, "rs_raw": 4.2}]),
    )


class SnapshotCitationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = execute("market.snapshot", {"trade_traction": "supports", "leader_limit": 10}, runtime=_runtime())

    def test_the_claims_the_payload_measured_against_are_all_cited(self) -> None:
        cited = set(self.payload["doctrine_ids"])

        self.assertLessEqual(
            {
                "scope.data_integrity",
                "market.striking_distance_52w_high",
                "market.avoid_52w_low_list",
                "market.correction_depth_healthy_leader",
                "market.group_new_highs_signal",
                "market.industry_groups_leading_bull_count",
            },
            cited,
        )

    def test_the_convention_that_sized_the_growth_window_is_cited_beside_the_count(self) -> None:
        self.assertIn("convention.group_member_reading", self.payload["doctrine_ids"])
        self.assertIn("convention.trading_week", self.payload["doctrine_ids"])

    def test_every_cited_claim_resolves_in_the_registry(self) -> None:
        for claim_id in self.payload["doctrine_ids"]:
            get_claim(claim_id)

    def test_a_snapshot_that_measured_nothing_cites_only_what_it_could_stand_behind(self) -> None:
        def nothing(as_of: str, *args: object) -> ProviderSnapshot[list[dict[str, object]]]:
            raise ProviderUnavailable("ibd-rs-rating", "fixture_withholds_rows", operation="top")

        runtime = Runtime(
            price_history=lambda ticker, as_of: (_ for _ in ()).throw(
                ProviderUnavailable("yfinance", "fixture_withholds_bars", operation="daily_bars")
            ),
            finviz_breadth=lambda as_of: (_ for _ in ()).throw(
                ProviderUnavailable("finviz", "fixture_withholds_breadth", operation="raw_snapshot")
            ),
            sector_ranking=nothing,
            industry_ranking=nothing,
            market_leaders=lambda as_of, limit: nothing(as_of),
        )

        payload = execute("market.snapshot", {"trade_traction": "supports"}, runtime=runtime)

        # The leader signal names the claim it was withheld under, and nothing else was read.
        self.assertEqual(payload["doctrine_ids"], ["scope.data_integrity", "market.bottoming_signal_checklist"])


if __name__ == "__main__":
    unittest.main()
