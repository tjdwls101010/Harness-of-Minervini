"""The snapshot places its ranked leaders into groups and counts from their own bars.

Group membership comes from a mutable current classification, so this path exists only for
the current session -- and a snapshot taken against a past session has to say the membership
was never read rather than attach today's taxonomy to it.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

import unittest
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from scripts.minervini import doctrine
from scripts.minervini.clock import resolve_as_of
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable
from scripts.minervini.windows import DAYS_IN_A_WEEK


TODAY = resolve_as_of().date
LOOKBACK_WEEKS = doctrine.parameter("convention.group_member_reading", "new_high_growth_lookback_weeks")
# Bars, for placing the fixture dip. The reading itself steps back on the calendar, and
# these fixtures trade every session, so the two land on the same bar.
LOOKBACK = 20
WINDOW = 260


def _frame(values: np.ndarray) -> pd.DataFrame:
    close = pd.Series(values, index=pd.bdate_range(end=TODAY, periods=len(values)))
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)},
        index=close.index,
    )


def _breaking_out() -> np.ndarray:
    """Flat for a year, dipping through the lookback window, and a new high on the last bar."""

    values = np.full(WINDOW + LOOKBACK + 20, 100.0)
    values[-LOOKBACK - 1 : -1] = 90.0
    values[-1] = 120.0
    return values


def _held_its_high() -> np.ndarray:
    return np.array([100.0 + index * 0.1 for index in range(WINDOW + LOOKBACK + 20)])


def _price(frame: pd.DataFrame) -> ProviderSnapshot[pd.DataFrame]:
    return rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime.now(timezone.utc), as_of=TODAY, coverage={"completed_only": True})


def _rows(rows: list[dict[str, object]]) -> ProviderSnapshot[list[dict[str, object]]]:
    return rows_snapshot(rows, provider="ibd-rs-rating", retrieved_at=datetime.now(timezone.utc), as_of=TODAY)


def _classification(symbol: str) -> ProviderSnapshot[dict[str, str]]:
    groups = {
        "BREAK": {"symbol": "BREAK", "sector": "Technology", "industry": "Semiconductors"},
        "HELD": {"symbol": "HELD", "sector": "Technology", "industry": "Semiconductors"},
    }
    if symbol not in groups:
        raise ProviderUnavailable("yfinance", "classification_missing", operation="current_classification")
    return rows_snapshot(groups[symbol], provider="yfinance", retrieved_at=datetime.now(timezone.utc), as_of=TODAY, coverage={"kind": "current_classification_only", "historical": False})


def _runtime() -> Runtime:
    frames = {"QQQ": _held_its_high(), "BREAK": _breaking_out(), "HELD": _held_its_high()}
    return Runtime(
        price_history=lambda ticker, as_of: _price(_frame(frames[ticker])),
        current_classification=_classification,
        finviz_breadth=lambda as_of: (_ for _ in ()).throw(
            ProviderUnavailable("finviz", "fixture_withholds_breadth", operation="raw_snapshot")
        ),
        sector_ranking=lambda as_of: _rows([{"sector": "Technology", "avg_rs": 92.0, "count": 20}]),
        industry_ranking=lambda as_of: _rows(
            [
                {"industry": "Semiconductors", "sector": "Technology", "avg_rs": 95.0, "count": 8},
                {"industry": "Chemicals", "sector": "Materials", "avg_rs": 61.0, "count": 12},
            ]
        ),
        market_leaders=lambda as_of, limit: _rows(
            [{"ticker": "BREAK", "rs_rating": 99, "rs_raw": 4.2}, {"ticker": "HELD", "rs_rating": 97, "rs_raw": 3.9}]
        ),
    )


class GroupMembershipTests(unittest.TestCase):
    def test_an_industry_counts_the_ranked_leaders_the_classification_placed_inside_it(self) -> None:
        payload = execute("market.snapshot", {"trade_traction": "supports", "leader_limit": 10}, runtime=_runtime())

        industries = {group["name"]: group for group in payload["data"]["group_ranks"]["industries"]}

        self.assertEqual(industries["Semiconductors"]["member_sample"]["ranked_leaders_in_group"], ["BREAK", "HELD"])
        reading = next(item for item in industries["Semiconductors"]["signal_vector"] if item["metric"] == "new_highs")
        self.assertEqual(reading["state"], "supports")
        measured = reading["value"]["measured"]

        self.assertEqual({key: measured[key] for key in ("now", "earlier", "of_names_read")}, {"now": 2, "earlier": 1, "of_names_read": 2})
        # The two moments the counts were taken at, four weeks of calendar time apart.
        self.assertEqual(measured["lookback_weeks"], LOOKBACK_WEEKS)
        self.assertEqual(
            date.fromisoformat(measured["read_at"]) - date.fromisoformat(measured["compared_with"]),
            timedelta(days=LOOKBACK_WEEKS * DAYS_IN_A_WEEK),
        )
        self.assertEqual(industries["Chemicals"]["member_sample"]["reason"], "no_ranked_leader_in_this_group")

    def test_the_group_summary_counts_the_advancing_groups_against_the_source_range(self) -> None:
        payload = execute("market.snapshot", {"trade_traction": "supports", "leader_limit": 10}, runtime=_runtime())

        summary = next(signal for signal in payload["signals"] if signal["id"] == "industry_leadership")

        self.assertEqual(summary["state"], "observed")
        self.assertEqual(summary["value"]["groups_showing_a_group_advance"], ["Semiconductors"])
        self.assertEqual(summary["value"]["count"]["doctrine_id"], "market.industry_groups_leading_bull_count")
        self.assertEqual(summary["value"]["count"]["measured"], 1)

    def test_a_past_session_reads_no_membership_and_names_the_reason(self) -> None:
        payload = execute(
            "market.snapshot", {"as_of": "2025-12-31", "trade_traction": "supports", "leader_limit": 10}, runtime=_runtime()
        )

        industries = {group["name"]: group for group in payload["data"]["group_ranks"]["industries"]}

        self.assertEqual(industries["Semiconductors"]["member_sample"]["reason"], "leader_classification_not_read")
        self.assertIn(
            "historical_session_has_no_current_classification",
            {item["reason"] for item in payload["missing"] if item["id"] == "leader_classification"},
        )


if __name__ == "__main__":
    unittest.main()
