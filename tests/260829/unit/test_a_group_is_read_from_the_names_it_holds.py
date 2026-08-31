"""A group's reading comes from the names the harness could place inside it.

The RS source ranks groups by an average and publishes no membership, so the six-slot group
vector this replaces had five slots permanently `unavailable` and a sixth that echoed the
caller's own word back.  What can be measured is what the market's ranked leaders -- already
fetched, already read from their own bars -- say about the group they are classified into.
"""

from __future__ import annotations

import unittest

import pandas as pd

from scripts.minervini import doctrine
from scripts.minervini.market_evidence import build_market_evidence


WEEK = doctrine.parameter("convention.trading_week", "sessions_per_trading_week")
LOOKBACK = doctrine.parameter("convention.group_member_reading", "new_high_growth_lookback_weeks") * WEEK
# Enough completed sessions for the window to span the 52 weeks it names -- the window is
# bounded by date, and 52 x the registered trading week of business days reaches back only
# 361 calendar days. LOOKBACK stays a session count: how far back the earlier count is taken
# is an offset the registry states in weeks, not a period an extreme is measured over.
WINDOW = 270
GROUP_NEW_HIGHS = "market.group_new_highs_signal"
STRIKING_DISTANCE = "market.striking_distance_52w_high"


def _bars(closes: list[float]) -> list[dict[str, object]]:
    index = pd.bdate_range("2024-01-01", periods=len(closes))
    return [
        {"date": stamp.date().isoformat(), "high": value, "low": value * 0.99, "close": value, "completed": True}
        for stamp, value in zip(index, closes)
    ]


def _flat(length: int = WINDOW + LOOKBACK + 20, value: float = 100.0) -> list[float]:
    return [value] * length


def _breaking_out_now(length: int = WINDOW + LOOKBACK + 20) -> list[float]:
    """A year at 100, a dip through the lookback window, and a new high on the last session."""

    values = _flat(length, 100.0)
    for index in range(length - LOOKBACK - 1, length - 1):
        values[index] = 90.0
    values[-1] = 120.0
    return values


def _at_a_high_throughout(length: int = WINDOW + LOOKBACK + 20) -> list[float]:
    return [100.0 + index * 0.1 for index in range(length)]


def _well_below_its_high(length: int = WINDOW + LOOKBACK + 20) -> list[float]:
    """Peaks at 100 and closes 10% under it -- inside the 5-15% striking-distance band."""

    values = [100.0] * length
    values[-1] = 90.0
    return values


def _evidence(*, sector_rows, leader_rows, leader_history, leader_groups):
    return build_market_evidence(
        qqq_daily_ohlcv=None,
        finviz_html=None,
        sector_rows=None,
        industry_rows=sector_rows,
        leader_rows=leader_rows,
        trade_traction={"state": "supports"},
        leader_history=leader_history,
        leader_groups=leader_groups,
    )


class GroupReadingTests(unittest.TestCase):
    def test_a_group_whose_ranked_names_are_newly_making_new_highs_supports_a_group_advance(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Semiconductors", "avg_rs": 92.0, "count": 20, "rank": 1, "as_of": "2026-08-26"}],
            leader_rows=[{"ticker": "BREAK", "rs_rating": 99}, {"ticker": "HELD", "rs_rating": 97}],
            leader_history={"BREAK": _bars(_breaking_out_now()), "HELD": _bars(_at_a_high_throughout())},
            leader_groups={"BREAK": {"sector": "Technology", "industry": "Semiconductors"}, "HELD": {"sector": "Technology", "industry": "Semiconductors"}},
        )

        group = evidence["industries"][0]

        self.assertEqual(group["new_highs"]["doctrine_id"], GROUP_NEW_HIGHS)
        self.assertEqual(group["new_highs"]["state"], "supports")
        self.assertEqual(group["new_highs"]["measured"], {"now": 2, "earlier": 1, "of_names_read": 2, "lookback_sessions": LOOKBACK})

    def test_a_group_whose_count_did_not_grow_reports_the_count_without_supporting(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Semiconductors", "avg_rs": 92.0, "count": 20, "rank": 1}],
            leader_rows=[{"ticker": "HELD", "rs_rating": 97}],
            leader_history={"HELD": _bars(_at_a_high_throughout())},
            leader_groups={"HELD": {"sector": "Technology", "industry": "Semiconductors"}},
        )

        group = evidence["industries"][0]

        self.assertEqual(group["new_highs"]["state"], "observed")
        self.assertEqual(group["new_highs"]["measured"]["now"], 1)
        self.assertEqual(group["new_highs"]["measured"]["earlier"], 1)

    def test_the_sample_the_count_was_taken_over_is_named_beside_it(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Semiconductors", "avg_rs": 92.0, "count": 20, "rank": 1}],
            leader_rows=[{"ticker": "HELD", "rs_rating": 97}, {"ticker": "OTHER", "rs_rating": 95}],
            leader_history={"HELD": _bars(_at_a_high_throughout()), "OTHER": _bars(_at_a_high_throughout())},
            leader_groups={"HELD": {"sector": "Technology", "industry": "Semiconductors"}, "OTHER": {"sector": "Energy", "industry": "Chemicals"}},
        )

        group = evidence["industries"][0]

        self.assertEqual(group["member_sample"]["state"], "reported")
        self.assertEqual(group["member_sample"]["ranked_leaders_in_group"], ["HELD"])
        self.assertEqual(group["member_sample"]["not_counted"], [])

    def test_a_group_holding_none_of_the_ranked_leaders_reports_that_rather_than_a_zero(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Oil", "avg_rs": 60.0, "count": 12, "rank": 2}],
            leader_rows=[{"ticker": "HELD", "rs_rating": 97}],
            leader_history={"HELD": _bars(_at_a_high_throughout())},
            leader_groups={"HELD": {"sector": "Technology", "industry": "Semiconductors"}},
        )

        group = evidence["industries"][0]

        self.assertEqual(
            group["member_sample"],
            {"state": "unavailable", "reason": "no_ranked_leader_in_this_group", "ranked_leaders_in_group": [], "not_counted": [], "unclassified": []},
        )
        self.assertEqual(group["new_highs"]["state"], "unavailable")
        self.assertEqual(group["new_highs"]["reason"], "no_ranked_leader_in_this_group")

    def test_with_no_classification_read_the_group_says_so_instead_of_naming_no_members(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Semiconductors", "avg_rs": 92.0, "count": 20, "rank": 1}],
            leader_rows=[{"ticker": "HELD", "rs_rating": 97}],
            leader_history={"HELD": _bars(_at_a_high_throughout())},
            leader_groups=None,
        )

        group = evidence["industries"][0]

        self.assertEqual(group["member_sample"]["reason"], "leader_classification_not_read")
        self.assertEqual(group["new_highs"]["reason"], "leader_classification_not_read")

    def test_a_word_the_caller_put_in_the_source_row_is_not_read_as_a_group_reading(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Oil", "avg_rs": 60.0, "count": 12, "rank": 2, "new_highs": "supports", "price_momentum": "supports"}],
            leader_rows=[],
            leader_history={},
            leader_groups={},
        )

        group = evidence["industries"][0]

        self.assertEqual(group["new_highs"]["state"], "unavailable")
        self.assertNotIn("price_momentum", group)
        self.assertEqual(group["source_row"]["new_highs"], "supports")

    def test_a_name_without_a_full_window_is_named_and_left_out_of_both_counts(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Semiconductors", "avg_rs": 92.0, "count": 20, "rank": 1}],
            leader_rows=[{"ticker": "HELD", "rs_rating": 97}, {"ticker": "YOUNG", "rs_rating": 95}],
            leader_history={"HELD": _bars(_at_a_high_throughout()), "YOUNG": _bars(_at_a_high_throughout(WINDOW - 10))},
            leader_groups={"HELD": {"sector": "Technology", "industry": "Semiconductors"}, "YOUNG": {"sector": "Technology", "industry": "Semiconductors"}},
        )

        group = evidence["industries"][0]

        self.assertEqual(group["member_sample"]["ranked_leaders_in_group"], ["HELD", "YOUNG"])
        self.assertEqual(group["member_sample"]["not_counted"], [{"ticker": "YOUNG", "reason": "completed_sessions_insufficient"}])
        self.assertEqual(group["new_highs"]["measured"]["of_names_read"], 1)

    def test_the_names_within_striking_distance_are_counted_against_the_source_range(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Semiconductors", "avg_rs": 92.0, "count": 20, "rank": 1}],
            leader_rows=[{"ticker": "NEAR", "rs_rating": 97}, {"ticker": "HELD", "rs_rating": 95}],
            leader_history={"NEAR": _bars(_well_below_its_high()), "HELD": _bars(_at_a_high_throughout())},
            leader_groups={"NEAR": {"sector": "Technology", "industry": "Semiconductors"}, "HELD": {"sector": "Technology", "industry": "Semiconductors"}},
        )

        group = evidence["industries"][0]

        self.assertEqual(group["striking_distance_names"]["doctrine_id"], STRIKING_DISTANCE)
        self.assertEqual(group["striking_distance_names"]["state"], "reported")
        self.assertEqual(group["striking_distance_names"]["measured"], {"within_source_range": 1, "of_names_read": 2})

    def test_every_group_reading_cites_the_claim_it_was_read_under(self) -> None:
        evidence = _evidence(
            sector_rows=[{"industry": "Semiconductors", "avg_rs": 92.0, "count": 20, "rank": 1}],
            leader_rows=[{"ticker": "HELD", "rs_rating": 97}],
            leader_history={"HELD": _bars(_at_a_high_throughout())},
            leader_groups={"HELD": {"sector": "Technology", "industry": "Semiconductors"}},
        )

        group = evidence["industries"][0]

        for reading in ("new_highs", "striking_distance_names"):
            self.assertIn("doctrine_id", group[reading], reading)
            self.assertIn("binds", group[reading], reading)
            doctrine.get_claim(group[reading]["doctrine_id"])

    def test_a_leader_carries_the_group_it_was_classified_into(self) -> None:
        evidence = _evidence(
            sector_rows=[],
            leader_rows=[{"ticker": "HELD", "rs_rating": 97}],
            leader_history={"HELD": _bars(_at_a_high_throughout())},
            leader_groups={"HELD": {"sector": "Technology", "industry": "Semiconductors"}},
        )

        self.assertEqual(evidence["leaders"][0]["group"], {"sector": "Technology", "industry": "Semiconductors"})


if __name__ == "__main__":
    unittest.main()
