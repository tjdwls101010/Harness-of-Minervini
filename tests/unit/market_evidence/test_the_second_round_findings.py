"""What the second Phase 5 review round found in the code the first round produced.

Each test is one finding, named by what the corrected code was still doing that the source
does not say.
"""

from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from scripts.minervini import doctrine
from scripts.minervini.market import evaluate_market_snapshot
from scripts.minervini.market_evidence import build_market_evidence


# Enough completed sessions for the window to span the 52 weeks it names. A business-day
# range skips weekends and no holidays, so 52 x the trading week reaches back only 361
# calendar days -- three short of the year the window is bounded by.
SESSIONS = 270
_FIRST_SESSION = pd.Timestamp("2025-01-02")


def _session(index: int) -> str:
    """The index-th business day of a run ending on a fixed session.

    Ordering tokens were enough while the window was a bar count. It is bounded by date now,
    so a fixture has to state sessions a calendar can measure a year across.
    """

    return (_FIRST_SESSION + pd.tseries.offsets.BDay(index)).date().isoformat()


def _leaders(supports: int, contradicts: int, unavailable: int) -> list[dict[str, object]]:
    states = ["supports"] * supports + ["contradicts"] * contradicts + ["unavailable"] * unavailable
    return [{"ticker": f"L{index}", "behavior": {"state": state}} for index, state in enumerate(states)]


def _evidence(**overrides: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "breadth": {"state": "observed", "sections": {}},
        "qqq_21ema": {"state": "on"},
        "sectors": [],
        "industries": [],
        "leaders": _leaders(1, 0, 0),
        "trade_traction": {"state": "supports"},
    }
    evidence.update(overrides)
    return evidence


def _signal(snapshot: dict[str, object], identifier: str) -> dict[str, object]:
    return next(item for item in snapshot["signal_vector"] if item["id"] == identifier)


class LeaderTractionMajorityTests(unittest.TestCase):
    def test_a_majority_of_the_read_names_is_not_a_majority_of_the_ranked_leaders(self) -> None:
        """Four of ten hold their ground, four were never read, and the source's word is
        "the majority of leaders" -- of the list, not of the part of it that answered."""

        snapshot = evaluate_market_snapshot(_evidence(leaders=_leaders(4, 2, 4)))

        traction = _signal(snapshot, "leader_traction")
        self.assertEqual(traction["state"], "mixed")
        self.assertNotEqual(snapshot["regime"]["judgment"], "favorable")

    def test_a_majority_of_the_ranked_leaders_holding_ground_still_supports(self) -> None:
        snapshot = evaluate_market_snapshot(_evidence(leaders=_leaders(6, 2, 2)))

        self.assertEqual(_signal(snapshot, "leader_traction")["state"], "supports")
        self.assertEqual(snapshot["regime"]["judgment"], "favorable")



def _reading_date(history: dict[str, list[dict[str, object]]]) -> date:
    """The last session the fixture carries -- the date the group reading is taken at.

    A fixture with no dated session has no group reading to take, so any date will do there.
    """

    dated = []
    for rows in history.values():
        for row in rows:
            try:
                dated.append(date.fromisoformat(str(row.get("date"))))
            except (TypeError, ValueError):
                # A fixture that deliberately carries a broken date has no reading to take.
                continue
    return max(dated) if dated else date(2026, 1, 2)

def _bars(rows: list[tuple[float, float, float]]) -> list[dict[str, object]]:
    return [
        {"date": _session(index), "high": high, "low": low, "close": close, "completed": True}
        for index, (high, low, close) in enumerate(rows)
    ]


class CorrectionDepthOrderingTests(unittest.TestCase):
    def test_a_low_is_measured_against_a_peak_the_sessions_before_it_established(self) -> None:
        """A daily bar records a high and a low and not which came first, so a decline read
        from a peak to a low inside the same session is a sequence the source's "peak to low"
        never states and the bar cannot support.

        Here the deepest decline the ordering is known for is 80 to 49."""

        rows = [(80.0, 79.0, 79.5)] * (SESSIONS - 2) + [(100.0, 49.0, 95.0), (98.0, 90.0, 95.0)]
        evidence = build_market_evidence(
            qqq_daily_ohlcv=None,
            finviz_html=None,
            sector_rows=None,
            industry_rows=None,
            leader_rows=[{"ticker": "LEAD"}],
            trade_traction={"state": "supports"},
            leader_history={"LEAD": _bars(rows)},
            leader_groups=None,
            as_of=_reading_date({"LEAD": _bars(rows)}),
        )

        leader = evidence["leaders"][0]

        self.assertAlmostEqual(leader["correction_depth"]["measured"], 38.75, places=2)
        self.assertEqual(leader["correction_gate"]["state"], "pass")


def _group(name: str, new_highs: object, striking: object) -> dict[str, object]:
    return {"name": name, "new_highs": new_highs, "striking_distance_names": striking, "basis": {"as_of": "2026-08-27"}}


class GroupReadingStateTests(unittest.TestCase):
    def test_a_signal_the_source_never_stated_for_sectors_is_not_missing_evidence(self) -> None:
        """Every sector reports the group-advance signal as out of scope, so the summary over
        them has nothing withheld to report -- it has a claim that does not reach sectors."""

        sectors = [_group("Technology", {"state": "not_applicable"}, {"state": "reported", "count": 3})]
        snapshot = evaluate_market_snapshot(_evidence(sectors=sectors))

        summary = _signal(snapshot, "sector_leadership")
        self.assertEqual(summary["state"], "not_applicable")
        self.assertNotIn("sectors.group_reading", snapshot["evidence_quality"]["missing_ids"])

    def test_a_group_reading_that_was_never_taken_reaches_the_missing_list(self) -> None:
        """The first round wired only `new_highs` to the missing list, so a group whose
        striking-distance count was never read still left the envelope looking complete."""

        sectors = [_group("Energy", {"state": "not_applicable"}, {"state": "unavailable", "reason": "no_ranked_leader_in_this_group"})]
        snapshot = evaluate_market_snapshot(_evidence(sectors=sectors))

        self.assertIn("sectors.striking_distance_names", snapshot["evidence_quality"]["missing_ids"])
        self.assertEqual(snapshot["evidence_quality"]["status"], "partial")

    def test_an_industry_with_no_group_advance_reading_is_still_unavailable(self) -> None:
        industries = [_group("Semiconductors", {"state": "unavailable"}, {"state": "reported", "count": 2})]
        snapshot = evaluate_market_snapshot(_evidence(industries=industries))

        self.assertEqual(_signal(snapshot, "industry_leadership")["state"], "unavailable")
        self.assertIn("industries.new_highs", snapshot["evidence_quality"]["missing_ids"])


if __name__ == "__main__":
    unittest.main()
