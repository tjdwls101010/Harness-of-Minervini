"""The per-leader fan-out degrades one name at a time.

Reading a leader's own bars turned one provider call into 2N of them, and everything in that
loop is optional evidence: no single leader's oddity may take down the whole market snapshot,
and no leader the harness failed to read may leave the envelope looking complete.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from scripts.minervini.clock import resolve_as_of
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta


TODAY = resolve_as_of().date


def _frame() -> pd.DataFrame:
    close = pd.Series([100.0 + index * 0.2 for index in range(300)], index=pd.bdate_range(end=TODAY, periods=300))
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)},
        index=close.index,
    )


def _snapshot(data: object, provider: str = "yfinance") -> ProviderSnapshot[object]:
    return ProviderSnapshot(
        data,
        SnapshotMeta(provider=provider, retrieved_at=datetime.now(timezone.utc), as_of=TODAY, coverage={"completed_only": True}),
    )


def _rs(rows: list[dict[str, object]]) -> ProviderSnapshot[list[dict[str, object]]]:
    return ProviderSnapshot(rows, SnapshotMeta(provider="ibd-rs-rating", retrieved_at=datetime.now(timezone.utc), as_of=TODAY))


def _runtime(price_history, *, leaders: list[dict[str, object]], classification=None) -> Runtime:
    return Runtime(
        price_history=price_history,
        current_classification=classification
        or (lambda symbol: (_ for _ in ()).throw(ProviderUnavailable("yfinance", "withheld", operation="current_classification"))),
        finviz_breadth=lambda as_of: (_ for _ in ()).throw(ProviderUnavailable("finviz", "withheld", operation="raw_snapshot")),
        sector_ranking=lambda as_of: _rs([]),
        industry_ranking=lambda as_of: _rs([]),
        market_leaders=lambda as_of, limit: _rs(leaders),
    )


class LeaderFanOutTests(unittest.TestCase):
    def test_a_history_that_is_not_a_frame_becomes_that_leader_s_gap(self) -> None:
        def prices(ticker: str, as_of: str) -> ProviderSnapshot[object]:
            return _snapshot(_frame() if ticker in {"QQQ", "GOOD"} else "not a frame")

        payload = execute(
            "market.snapshot",
            {"trade_traction": "supports"},
            runtime=_runtime(prices, leaders=[{"ticker": "GOOD", "rs_rating": 99}, {"ticker": "ODD", "rs_rating": 97}]),
        )

        leaders = {leader["ticker"]: leader for leader in payload["data"]["leaders"]}
        self.assertEqual(leaders["GOOD"]["behavior"]["state"], "supports")
        self.assertEqual(leaders["ODD"]["behavior"]["state"], "unavailable")
        self.assertIn("ODD", {item.get("ticker") for item in payload["missing"]})

    def test_an_exception_the_provider_contract_does_not_name_becomes_that_leader_s_gap(self) -> None:
        def prices(ticker: str, as_of: str) -> ProviderSnapshot[object]:
            if ticker == "ODD":
                raise RuntimeError("the provider raised something else entirely")
            return _snapshot(_frame())

        payload = execute(
            "market.snapshot",
            {"trade_traction": "supports"},
            runtime=_runtime(prices, leaders=[{"ticker": "GOOD", "rs_rating": 99}, {"ticker": "ODD", "rs_rating": 97}]),
        )

        self.assertEqual(payload["operation"], "market.snapshot")
        leaders = {leader["ticker"]: leader for leader in payload["data"]["leaders"]}
        self.assertEqual(leaders["GOOD"]["behavior"]["state"], "supports")
        self.assertIn(
            "RuntimeError",
            " ".join(str(item.get("reason")) for item in payload["missing"] if item.get("ticker") == "ODD"),
        )

    def test_a_classification_that_is_not_a_mapping_becomes_that_leader_s_gap(self) -> None:
        payload = execute(
            "market.snapshot",
            {"trade_traction": "supports"},
            runtime=_runtime(
                lambda ticker, as_of: _snapshot(_frame()),
                leaders=[{"ticker": "GOOD", "rs_rating": 99}],
                classification=lambda symbol: _snapshot("not a mapping"),
            ),
        )

        self.assertEqual(payload["data"]["leaders"][0]["group"], None)
        self.assertIn("GOOD", {item.get("ticker") for item in payload["missing"]})

    def test_the_fan_out_reads_no_more_leaders_than_the_limit_allowed(self) -> None:
        seen: list[str] = []

        def prices(ticker: str, as_of: str) -> ProviderSnapshot[object]:
            seen.append(ticker)
            return _snapshot(_frame())

        execute(
            "market.snapshot",
            {"trade_traction": "supports", "leader_limit": 2},
            runtime=_runtime(prices, leaders=[{"ticker": f"L{index}", "rs_rating": 99 - index} for index in range(25)]),
        )

        self.assertEqual([ticker for ticker in seen if ticker != "QQQ"], ["L0", "L1"])

    def test_a_history_with_no_readable_bar_is_named_in_missing(self) -> None:
        def prices(ticker: str, as_of: str) -> ProviderSnapshot[object]:
            return _snapshot(_frame() if ticker == "QQQ" else pd.DataFrame())

        payload = execute(
            "market.snapshot",
            {"trade_traction": "supports"},
            runtime=_runtime(prices, leaders=[{"ticker": "EMPTY", "rs_rating": 99}]),
        )

        self.assertEqual(payload["data"]["leaders"][0]["behavior"]["state"], "unavailable")
        self.assertIn("EMPTY", {item.get("ticker") for item in payload["missing"]})


if __name__ == "__main__":
    unittest.main()
