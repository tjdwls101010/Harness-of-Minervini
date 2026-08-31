"""What a market leader is doing, measured, rather than a word somebody typed beside its rank.

The RS source ranks tickers and says nothing about behavior, so the evidence builder stood a
placeholder in that slot for every leader it received. The placeholder reports `observed`, and
`observed` is not `supports` -- which made the favorable regime unreachable from any live
snapshot, not because the market never qualified but because one signal could never be met.

The three readings below are the deterministic ones the corpus states about a leader's price:
how far it sits from a new 52-week high, whether it is printing on the 52-week-low list, and
how deep its correction from the last peak has run.
"""

from __future__ import annotations

import unittest

from scripts.minervini.market_evidence import build_market_evidence


# Enough completed sessions for the window to span the 52 weeks it names. The window is
# bounded by date, and a business-day range skips weekends and no holidays -- so 52 x the
# registered trading week reaches back only 361 calendar days, three short of the year.
WINDOW = 270


def bars(closes: list[float], *, start: str = "2025-01-02") -> list[dict]:
    import pandas as pd

    index = pd.bdate_range(start, periods=len(closes))
    return [
        {"date": stamp.date().isoformat(), "open": close, "high": close, "low": close, "close": close, "volume": 1_000_000}
        for stamp, close in zip(index, closes)
    ]


def evidence(history: dict[str, list[dict]], rows: list[dict] | None = None) -> dict:
    return build_market_evidence(
        qqq_daily_ohlcv=None,
        finviz_html=None,
        sector_rows=None,
        industry_rows=None,
        leader_rows=rows if rows is not None else [{"ticker": ticker, "rs_rating": 99} for ticker in history],
        leader_history=history,
        trade_traction=None,
    )


class HowFarFromANewHigh(unittest.TestCase):
    """"Within striking distance (5 to 15 percent) of a new 52-week high" is a measurement.

    It is a band, so what goes out is the distance, the range, and which side of it the stock
    sat on -- and a stock nearer than five percent is nearer than the range, not outside it.
    """

    def test_a_leader_eight_percent_off_its_high_sits_inside_the_range(self) -> None:
        history = {"AAA": bars([100.0] * (WINDOW - 1) + [92.0])}
        leader = evidence(history)["leaders"][0]

        self.assertEqual(leader["distance_from_52w_high"]["measured"], 8.0)
        self.assertEqual(leader["distance_from_52w_high"]["source_range"], [5, 15])
        self.assertEqual(leader["distance_from_52w_high"]["state"], "within_source_range")

    def test_a_leader_at_its_high_is_nearer_than_the_range(self) -> None:
        history = {"AAA": bars([90.0] * (WINDOW - 1) + [100.0])}
        leader = evidence(history)["leaders"][0]

        self.assertEqual(leader["distance_from_52w_high"]["measured"], 0.0)
        self.assertEqual(leader["distance_from_52w_high"]["state"], "below_source_range")


class TheListToStayAwayFrom(unittest.TestCase):
    """"Every day there is a list of stocks to avoid: the 52-week-low list."

    The claim carries no threshold, so what is published is whether this completed session
    printed the lowest low of the ticker's own 52 weeks -- which is what puts it on that list.
    """

    def test_a_leader_closing_at_its_own_52_week_low_is_on_the_list(self) -> None:
        leader = evidence({"AAA": bars([100.0] * (WINDOW - 1) + [40.0])})["leaders"][0]

        self.assertIs(leader["on_52w_low_list"]["measured"], True)

    def test_a_leader_off_its_low_is_not(self) -> None:
        """The year's low is inside the window and is not this session's, which is the whole test."""

        leader = evidence({"AAA": bars([100.0] * 60 + [40.0] + [100.0] * (WINDOW - 61))})["leaders"][0]

        self.assertIs(leader["on_52w_low_list"]["measured"], False)


class HowDeepTheCorrectionRan(unittest.TestCase):
    """25 to 35 percent is the healthy range, and fifty percent is where the source stops.

    The band reports where the depth sat; the gate is the only thing here that can refuse, and
    it refuses at the fifty percent the source named for even a severe bear market.
    """

    def test_a_thirty_percent_correction_sits_inside_the_healthy_range(self) -> None:
        leader = evidence({"AAA": bars([100.0] * 130 + [70.0] + [75.0] * 130)})["leaders"][0]

        self.assertEqual(leader["correction_depth"]["measured"], 30.0)
        self.assertEqual(leader["correction_depth"]["state"], "within_source_range")
        self.assertEqual(leader["correction_gate"]["state"], "pass")

    def test_a_correction_past_fifty_percent_fails_the_gate(self) -> None:
        leader = evidence({"AAA": bars([100.0] * 130 + [40.0] + [45.0] * 130)})["leaders"][0]

        self.assertEqual(leader["correction_depth"]["measured"], 60.0)
        self.assertEqual(leader["correction_gate"]["state"], "fail")


class TheBehaviorWordIsNoLongerSomethingACallerCanType(unittest.TestCase):
    """A state read off the bars, and a caller's word ignored where the bars can answer.

    The band never carries the state alone: a leader supports only when the gate its own
    correction has to clear passed and the distance from a new high is inside the range or
    nearer. A stock on the 52-week-low list contradicts, which is the source's own instruction.
    """

    def test_a_leader_near_its_high_with_a_shallow_correction_supports(self) -> None:
        leader = evidence({"AAA": bars([100.0] * 130 + [80.0] + [92.0] * 130)})["leaders"][0]

        self.assertEqual(leader["behavior"]["state"], "supports")

    def test_a_leader_on_the_low_list_contradicts_whatever_the_caller_typed(self) -> None:
        rows = [{"ticker": "AAA", "rs_rating": 99, "behavior": "positive"}]
        leader = evidence({"AAA": bars([100.0] * (WINDOW - 1) + [40.0])}, rows)["leaders"][0]

        self.assertEqual(leader["behavior"]["state"], "contradicts")

    def test_a_leader_with_no_history_is_unavailable_rather_than_observed(self) -> None:
        leader = evidence({}, [{"ticker": "AAA", "rs_rating": 99}])["leaders"][0]

        self.assertEqual(leader["behavior"]["state"], "unavailable")
        self.assertEqual(leader["behavior"]["reason"], "leader_price_history_not_read")


class EveryReadingNamesTheClaimItCameFrom(unittest.TestCase):
    def test_the_three_deterministic_leader_claims_are_cited(self) -> None:
        leader = evidence({"AAA": bars([100.0] * (WINDOW - 1) + [92.0])})["leaders"][0]

        self.assertEqual(leader["distance_from_52w_high"]["doctrine_id"], "market.striking_distance_52w_high")
        self.assertEqual(leader["on_52w_low_list"]["doctrine_id"], "market.avoid_52w_low_list")
        self.assertEqual(leader["correction_depth"]["doctrine_id"], "market.correction_depth_healthy_leader")


if __name__ == "__main__":
    unittest.main()
