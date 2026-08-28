"""What the doctrine lens found in the first Phase 5 review round.

Each test is one finding, named by what the code was doing that the source does not say.
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine
from scripts.minervini.market import evaluate_market_snapshot
from scripts.minervini.market_evidence import build_market_evidence


SESSIONS = 52 * doctrine.parameter("convention.trading_week", "sessions_per_trading_week")


def _bars(values: list[float], lows: list[float] | None = None) -> list[dict[str, object]]:
    return [
        {"date": f"d{index:04d}", "high": value, "low": (lows[index] if lows else value * 0.99), "close": value, "completed": True}
        for index, value in enumerate(values)
    ]


def _evidence(*, leader_rows, leader_history, leader_groups=None, sector_rows=None, industry_rows=None):
    return build_market_evidence(
        qqq_daily_ohlcv=None,
        finviz_html=None,
        sector_rows=sector_rows,
        industry_rows=industry_rows,
        leader_rows=leader_rows,
        trade_traction={"state": "supports"},
        leader_history=leader_history,
        leader_groups=leader_groups,
    )


class DoctrineRoundTests(unittest.TestCase):
    def test_the_52_week_window_is_converted_through_the_registered_trading_week(self) -> None:
        """252 was a number this module invented; the registry owns the conversion."""

        self.assertEqual(SESSIONS, 260)
        history = {"LEAD": _bars([100.0] * (SESSIONS - 1))}
        evidence = _evidence(leader_rows=[{"ticker": "LEAD"}], leader_history=history)

        self.assertEqual(evidence["leaders"][0]["behavior"]["state"], "unavailable")

    def test_a_history_shorter_than_a_year_publishes_no_52_week_reading(self) -> None:
        evidence = _evidence(leader_rows=[{"ticker": "LEAD"}], leader_history={"LEAD": _bars([100.0, 101.0])})

        leader = evidence["leaders"][0]

        self.assertEqual(leader["behavior"]["reason"], "completed_sessions_short_of_a_52_week_window")
        self.assertIsNone(leader["distance_from_52w_high"]["measured"])
        self.assertEqual(leader["on_52w_low_list"]["state"], "unavailable")
        self.assertIsNone(leader["correction_depth"]["measured"])

    def test_a_new_high_today_does_not_erase_the_correction_it_recovered_from(self) -> None:
        """The claim is about the decline preceding the next new high, so a new high cannot be
        the peak the decline is measured from."""

        values = [200.0] * 10 + [100.0] * 10 + [201.0] * (SESSIONS - 20)
        evidence = _evidence(leader_rows=[{"ticker": "LEAD"}], leader_history={"LEAD": _bars(values, lows=values)})

        depth = evidence["leaders"][0]["correction_depth"]

        self.assertAlmostEqual(depth["measured"], 50.0, places=2)

    def test_a_session_printing_the_years_lowest_low_is_on_the_52_week_low_list(self) -> None:
        values = [100.0] * (SESSIONS - 1) + [50.0]
        evidence = _evidence(leader_rows=[{"ticker": "LEAD"}], leader_history={"LEAD": _bars(values, lows=values)})

        self.assertIs(evidence["leaders"][0]["on_52w_low_list"]["measured"], True)
        self.assertEqual(evidence["leaders"][0]["behavior"]["reason"], "printing_on_the_52_week_low_list")

    def test_the_group_advance_signal_is_not_claimed_for_a_sector(self) -> None:
        """The source states it for names in a particular industry."""

        history = {"LEAD": _bars([100.0 + index * 0.1 for index in range(SESSIONS + 20)])}
        groups = {"LEAD": {"sector": "Technology", "industry": "Semiconductors"}}
        evidence = _evidence(
            leader_rows=[{"ticker": "LEAD"}],
            leader_history=history,
            leader_groups=groups,
            sector_rows=[{"sector": "Technology"}],
            industry_rows=[{"industry": "Semiconductors"}],
        )

        self.assertEqual(evidence["sectors"][0]["new_highs"]["state"], "not_applicable")
        self.assertEqual(evidence["industries"][0]["new_highs"]["state"], "observed")

    def test_the_leading_group_count_is_read_only_against_the_industry_list(self) -> None:
        history = {"LEAD": _bars([100.0 + index * 0.1 for index in range(SESSIONS + 20)])}
        groups = {"LEAD": {"sector": "Technology", "industry": "Semiconductors"}}
        snapshot = evaluate_market_snapshot(
            _evidence(
                leader_rows=[{"ticker": "LEAD"}],
                leader_history=history,
                leader_groups=groups,
                sector_rows=[{"sector": "Technology"}],
                industry_rows=[{"industry": "Semiconductors"}],
            )
        )

        by_id = {signal["id"]: signal for signal in snapshot["signal_vector"]}

        self.assertIn("count", by_id["industry_leadership"]["value"])
        self.assertNotIn("count", by_id["sector_leadership"]["value"])

    def test_the_group_member_count_cites_the_convention_that_defined_its_sample(self) -> None:
        history = {"LEAD": _bars([100.0 + index * 0.1 for index in range(SESSIONS + 20)])}
        evidence = _evidence(
            leader_rows=[{"ticker": "LEAD"}],
            leader_history=history,
            leader_groups={"LEAD": {"sector": "Technology", "industry": "Semiconductors"}},
            industry_rows=[{"industry": "Semiconductors"}],
        )

        reading = evidence["industries"][0]["striking_distance_names"]

        self.assertIn("convention.group_member_reading", reading["sample_doctrine_ids"])


class LeaderMajorityTests(unittest.TestCase):
    def _snapshot(self, states: list[str]) -> dict[str, object]:
        return evaluate_market_snapshot(
            {
                "breadth": {"state": "observed"},
                "qqq_21ema": {"state": "on"},
                "sectors": [],
                "industries": [],
                "leaders": [{"ticker": f"L{index}", "behavior": {"state": state}} for index, state in enumerate(states)],
                "trade_traction": {"state": "supports"},
            }
        )

    def test_one_measured_leader_among_twenty_unread_ones_cannot_carry_the_market(self) -> None:
        snapshot = self._snapshot(["supports"] + ["unavailable"] * 19)

        by_id = {signal["id"]: signal for signal in snapshot["signal_vector"]}

        self.assertEqual(by_id["leader_traction"]["state"], "unavailable")
        self.assertEqual(snapshot["regime"]["judgment"], "incomplete")

    def test_a_majority_of_the_ranked_leaders_holding_their_ground_is_what_supports(self) -> None:
        """The second round narrowed this: the majority is of the ranked list, not of the
        part of it that answered -- see test_the_second_round_findings."""

        snapshot = self._snapshot(["supports", "supports", "supports", "unavailable"])

        by_id = {signal["id"]: signal for signal in snapshot["signal_vector"]}

        self.assertEqual(by_id["leader_traction"]["state"], "supports")
        self.assertEqual(by_id["leader_traction"]["doctrine_id"], "market.bottoming_signal_checklist")

    def test_no_majority_either_way_is_mixed_rather_than_a_verdict(self) -> None:
        snapshot = self._snapshot(["supports", "contradicts", "observed", "observed"])

        by_id = {signal["id"]: signal for signal in snapshot["signal_vector"]}

        self.assertEqual(by_id["leader_traction"]["state"], "mixed")


class SwitchIsNotAGateTests(unittest.TestCase):
    def _snapshot(self, switch: str, traction: str, leader: str) -> dict[str, object]:
        return evaluate_market_snapshot(
            {
                "breadth": {"state": "observed"},
                "qqq_21ema": {"state": switch},
                "sectors": [],
                "industries": [],
                "leaders": [{"ticker": "LEAD", "behavior": {"state": leader}}],
                "trade_traction": {"state": traction},
            }
        )

    def test_an_opt_in_tactic_does_not_veto_the_favorable_word(self) -> None:
        """tactic.market_cycle_swing_system's own note: do not promote this to a hard gate."""

        snapshot = self._snapshot("off", "supports", "supports")

        self.assertEqual(snapshot["regime"]["judgment"], "favorable")

    def test_an_opt_in_tactic_does_not_produce_the_defensive_word_either(self) -> None:
        snapshot = self._snapshot("off", "contradicts", "observed")

        self.assertEqual(snapshot["regime"]["judgment"], "cautious")


if __name__ == "__main__":
    unittest.main()
