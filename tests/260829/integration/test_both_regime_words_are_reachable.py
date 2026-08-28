"""Favorable and defensive are both reachable from provider-shaped evidence.

Phase 5's completion criterion. Before the leader reading was measured and the verdict set was
narrowed to the signals doctrine can decide, `favorable` could not be produced by any snapshot
and the defensive rule's second arm was dead.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.minervini.clock import resolve_as_of
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta


TODAY = resolve_as_of().date
FINVIZ = Path(__file__).resolve().parents[2] / "260817" / "fixtures" / "market_evidence" / "finviz_partial.html"


def _frame(values: np.ndarray) -> pd.DataFrame:
    close = pd.Series(values, index=pd.bdate_range(end=TODAY, periods=len(values)))
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)},
        index=close.index,
    )


def _advancing() -> np.ndarray:
    return np.array([100.0 + index * 0.2 for index in range(300)])


def _broken() -> np.ndarray:
    """A peak at 200 and a slide to 100 -- past the source's 50% correction ceiling."""

    return np.concatenate([np.linspace(80, 200, 150), np.linspace(200, 100, 150)])


def _price(frame: pd.DataFrame) -> ProviderSnapshot[pd.DataFrame]:
    return ProviderSnapshot(
        frame,
        SnapshotMeta(provider="yfinance", retrieved_at=datetime.now(timezone.utc), as_of=TODAY, coverage={"completed_only": True}),
    )


def _rs(rows: list[dict[str, object]]) -> ProviderSnapshot[list[dict[str, object]]]:
    return ProviderSnapshot(rows, SnapshotMeta(provider="ibd-rs-rating", retrieved_at=datetime.now(timezone.utc), as_of=TODAY))


def _runtime(leader_values: np.ndarray, *, breadth: bool = True) -> Runtime:
    frames = {"QQQ": _advancing(), "LEAD": leader_values}
    return Runtime(
        price_history=lambda ticker, as_of: _price(_frame(frames[ticker])),
        current_classification=lambda symbol: ProviderSnapshot(
            {"symbol": symbol, "sector": "Technology", "industry": "Semiconductors"},
            SnapshotMeta(
                provider="yfinance",
                retrieved_at=datetime.now(timezone.utc),
                as_of=TODAY,
                coverage={"kind": "current_classification_only", "historical": False},
            ),
        ),
        finviz_breadth=(
            (
                lambda as_of: ProviderSnapshot(
                    FINVIZ.read_text(encoding="utf-8"),
                    SnapshotMeta(provider="finviz", retrieved_at=datetime.now(timezone.utc), as_of=TODAY, content_sha256="fixture"),
                )
            )
            if breadth
            else (lambda as_of: (_ for _ in ()).throw(ProviderUnavailable("finviz", "fixture_withholds_breadth", operation="raw_snapshot")))
        ),
        sector_ranking=lambda as_of: _rs([{"sector": "Technology", "avg_rs": 92.0, "count": 20}]),
        industry_ranking=lambda as_of: _rs([{"industry": "Semiconductors", "sector": "Technology", "avg_rs": 95.0, "count": 8}]),
        market_leaders=lambda as_of, limit: _rs([{"ticker": "LEAD", "rs_rating": 99, "rs_raw": 4.2}]),
    )


class RegimeReachabilityFromProvidersTests(unittest.TestCase):
    def test_a_leader_holding_its_high_under_supporting_traction_produces_favorable(self) -> None:
        payload = execute("market.snapshot", {"trade_traction": "supports", "leader_limit": 10}, runtime=_runtime(_advancing()))

        self.assertEqual(payload["data"]["regime"]["judgment"], "favorable")
        self.assertEqual(
            {row["signal_id"]: row["state"] for row in payload["data"]["regime"]["evidence"]},
            {"leader_traction": "supports", "trade_traction": "supports"},
        )

    def test_a_leader_past_the_correction_ceiling_under_contradicting_traction_produces_defensive(self) -> None:
        payload = execute("market.snapshot", {"trade_traction": "contradicts", "leader_limit": 10}, runtime=_runtime(_broken()))

        self.assertEqual(payload["data"]["regime"]["judgment"], "defensive")
        self.assertEqual(
            {row["signal_id"]: row["state"] for row in payload["data"]["regime"]["evidence"]},
            {"leader_traction": "contradicts", "trade_traction": "contradicts"},
        )

    def test_the_breadth_the_snapshot_could_not_read_is_context_and_not_a_verdict(self) -> None:
        payload = execute(
            "market.snapshot", {"trade_traction": "supports", "leader_limit": 10}, runtime=_runtime(_advancing(), breadth=False)
        )

        self.assertEqual(payload["data"]["regime"]["judgment"], "favorable")
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(
            {row["signal_id"]: row["state"] for row in payload["data"]["regime"]["context"]},
            {"qqq_21ema_switch": "supports", "market_breadth": "unavailable"},
        )


if __name__ == "__main__":
    unittest.main()
