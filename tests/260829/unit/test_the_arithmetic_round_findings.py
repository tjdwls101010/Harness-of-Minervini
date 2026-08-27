"""What the arithmetic and envelope lenses found in the first Phase 5 review round."""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.market import evaluate_market_snapshot
from scripts.minervini.market_evidence import build_market_evidence


SESSIONS = 52 * doctrine.parameter("convention.trading_week", "sessions_per_trading_week")


def _bars(highs: list[float], lows: list[float] | None = None, *, dated: bool = True) -> list[dict[str, object]]:
    lows = lows if lows is not None else [value * 0.99 for value in highs]
    return [
        {
            **({"date": f"d{index:04d}"} if dated else {}),
            "high": high,
            "low": lows[index],
            "close": high,
            "completed": True,
        }
        for index, high in enumerate(highs)
    ]


def _leader(history: object, rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    evidence = build_market_evidence(
        qqq_daily_ohlcv=None,
        finviz_html=None,
        sector_rows=None,
        industry_rows=None,
        leader_rows=rows or [{"ticker": "LEAD"}],
        trade_traction={"state": "supports"},
        leader_history={"LEAD": history},
    )
    return evidence["leaders"][0]


class SeriesGuardTests(unittest.TestCase):
    def test_a_newest_first_history_is_refused_rather_than_read_backwards(self) -> None:
        rows = _bars([100.0] * SESSIONS)
        leader = _leader(list(reversed(rows)))

        self.assertEqual(leader["behavior"]["reason"], "leader_price_history_not_read")

    def test_a_price_at_or_below_zero_makes_the_history_unreadable(self) -> None:
        highs = [100.0] * SESSIONS
        lows = [99.0] * (SESSIONS - 1) + [0.0]
        leader = _leader(_bars(highs, lows))

        self.assertEqual(leader["behavior"]["state"], "unavailable")
        self.assertIsNone(leader["correction_depth"]["measured"])

    def test_a_peak_the_window_opens_after_is_not_measured_from(self) -> None:
        """The window is the year; a peak older than it belongs to no reading here."""

        highs = [200.0] + [100.0] * SESSIONS
        lows = [200.0] + [95.0] * SESSIONS
        leader = _leader(_bars(highs, lows))

        self.assertAlmostEqual(leader["correction_depth"]["measured"], 5.0, places=6)

    def test_a_session_that_gave_back_its_own_high_is_a_decline_from_that_high(self) -> None:
        highs = [90.0] * (SESSIONS - 1) + [100.0]
        lows = [89.0] * (SESSIONS - 1) + [40.0]
        leader = _leader(_bars(highs, lows))

        # The running peak reaches 100 on the same session the 40 printed, so that session's
        # own give-back is the deepest decline in the window rather than the 55.6% measured
        # from the 90 that preceded it. A stock that traded 100 down to 40 did decline 60%.
        self.assertAlmostEqual(leader["correction_depth"]["measured"], 60.0, places=6)

    def test_two_rows_for_one_ticker_are_read_as_one_leader(self) -> None:
        evidence = build_market_evidence(
            qqq_daily_ohlcv=None,
            finviz_html=None,
            sector_rows=None,
            industry_rows=None,
            leader_rows=[{"ticker": "LEAD", "rs_rating": 99}, {"ticker": "LEAD", "rs_rating": 98}],
            trade_traction={"state": "supports"},
            leader_history={"LEAD": _bars([100.0 + index * 0.1 for index in range(SESSIONS)])},
        )

        self.assertEqual([leader["ticker"] for leader in evidence["leaders"]], ["LEAD"])


class SampleHonestyTests(unittest.TestCase):
    def test_a_group_with_no_member_says_so_only_when_every_leader_was_classified(self) -> None:
        history = {"LEAD": _bars([100.0 + index * 0.1 for index in range(SESSIONS + 20)])}
        evidence = build_market_evidence(
            qqq_daily_ohlcv=None,
            finviz_html=None,
            sector_rows=None,
            industry_rows=[{"industry": "Semiconductors"}],
            leader_rows=[{"ticker": "LEAD"}],
            trade_traction={"state": "supports"},
            leader_history=history,
            leader_groups={},
        )

        sample = evidence["industries"][0]["member_sample"]

        self.assertEqual(sample["reason"], "classification_incomplete_for_the_ranked_leaders")
        self.assertEqual(sample["unclassified"], ["LEAD"])


class OneAnswerPerQuestionTests(unittest.TestCase):
    def test_a_group_whose_reading_was_never_taken_reaches_the_missing_list(self) -> None:
        snapshot = evaluate_market_snapshot(
            {
                "breadth": {"state": "observed"},
                "qqq_21ema": {"state": "on"},
                "sectors": [],
                "industries": [
                    {"name": "Semiconductors", "basis": {}, "new_highs": {"state": "unavailable", "reason": "no_ranked_leader_in_this_group"}, "striking_distance_names": {"state": "unavailable"}}
                ],
                "leaders": [{"ticker": "LEAD", "behavior": {"state": "supports"}}],
                "trade_traction": {"state": "supports"},
            }
        )

        self.assertIn("industries.group_reading", {item["id"] for item in snapshot["missing"]})
        self.assertEqual(snapshot["evidence_quality"]["status"], "partial")

    def test_a_non_finite_group_count_does_not_decide_a_rank(self) -> None:
        groups = [
            {"name": "Broken", "basis": {"rank": 2}, "new_highs": {"state": "observed", "measured": {"now": float("nan")}}, "striking_distance_names": {"state": "observed"}},
            {"name": "Sound", "basis": {"rank": 1}, "new_highs": {"state": "observed", "measured": {"now": 1}}, "striking_distance_names": {"state": "observed"}},
        ]
        snapshot = evaluate_market_snapshot(
            {"breadth": None, "qqq_21ema": None, "sectors": groups, "industries": [], "leaders": [], "trade_traction": None}
        )

        self.assertEqual([group["name"] for group in snapshot["group_ranks"]["sectors"]], ["Sound", "Broken"])


if __name__ == "__main__":
    unittest.main()
