"""The registry owns the numbers: move one and the reducers move with it.

Asserting a reducer's literal equals the registry's value only proves the two agree
today. Changing the registry and watching the verdict follow proves the reducer is
reading it, which is the difference between a single source of truth and a copy.
"""

from __future__ import annotations

import contextlib
import copy
import json
import pathlib
import unittest

import pandas as pd

from scripts.minervini import doctrine
from scripts.minervini.risk import reduce_risk
from scripts.minervini.technical import build_eligibility_evidence


REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "doctrine" / "claims.json"


@contextlib.contextmanager
def threshold_moved(claim_id: str, name: str, **changes: object):
    """Swap one registry threshold for the duration of a test, in memory only.

    An earlier version rewrote the checked-in registry and restored it afterwards,
    which made the suite unrunnable read-only and left a corrupt registry behind if a
    run died between the two writes. Substituting the loader keeps the edit where it
    belongs -- inside the test.
    """

    edited = copy.deepcopy(json.loads(REGISTRY.read_text(encoding="utf-8")))
    record = next(item for item in edited["claims"] if item["id"] == claim_id)
    record["thresholds"][name].update(changes)
    loader = doctrine._load_registry
    doctrine._load_registry = lambda: edited
    try:
        yield
    finally:
        doctrine._load_registry = loader


def rising_history(sessions: int = 260) -> pd.DataFrame:
    index = pd.bdate_range(end="2026-08-21", periods=sessions)
    return pd.DataFrame({"Close": [50.0 + value * 0.4 for value in range(sessions)]}, index=index)


def pulled_back_history(sessions: int = 260) -> pd.DataFrame:
    """A rising series that gives back ground at the end, so both 52-week gates can move."""

    closes = [50.0 + value * 0.4 for value in range(sessions - 10)]
    peak = closes[-1]
    closes.extend(peak * (1 - 0.003 * (step + 1)) for step in range(10))
    return pd.DataFrame({"Close": closes}, index=pd.bdate_range(end="2026-08-21", periods=sessions))


def trend_signal(identifier: str, rs_rating: int, frame: pd.DataFrame | None = None) -> dict:
    evidence = build_eligibility_evidence(rising_history() if frame is None else frame, rs_rating=rs_rating)
    return next(signal for signal in evidence["trend_template"] if signal["id"] == identifier)


CONVERGED = {
    "mode": "prospective",
    "market": {"state": "pass"},
    "eligibility": {"state": "pass"},
    "setup": {"setup_state": "ready"},
    "fundamentals": {"state": "pass"},
    "risk": {"entry_price": 100.0, "stop_price": 94.0, "upside_price": 112.0, "average_gain_pct": 20.0},
}


class TrendTemplateParityTests(unittest.TestCase):
    def test_the_relative_strength_minimum_comes_from_the_registry(self) -> None:
        self.assertEqual(trend_signal("trend_template.relative_strength_minimum", 72)["state"], "pass")

        with threshold_moved("eligibility.standard_trend_template", "relative_strength_minimum", value=75):
            self.assertEqual(trend_signal("trend_template.relative_strength_minimum", 72)["state"], "fail")

    def test_the_required_text_is_rendered_from_the_registry_not_written_by_hand(self) -> None:
        with threshold_moved("eligibility.standard_trend_template", "relative_strength_minimum", value=75):
            signal = trend_signal("trend_template.relative_strength_minimum", 80)

        self.assertIn("75", signal["basis"]["required"])

    def test_the_distance_above_the_52_week_low_comes_from_the_registry(self) -> None:
        self.assertEqual(trend_signal("trend_template.price_above_52_week_low", 80)["state"], "pass")

        with threshold_moved("eligibility.standard_trend_template", "minimum_pct_above_52_week_low", value=500):
            self.assertEqual(trend_signal("trend_template.price_above_52_week_low", 80)["state"], "fail")

    def test_the_distance_below_the_52_week_high_comes_from_the_registry(self) -> None:
        frame = pulled_back_history()
        self.assertEqual(trend_signal("trend_template.price_near_52_week_high", 80, frame)["state"], "pass")

        with threshold_moved("eligibility.standard_trend_template", "maximum_pct_below_52_week_high", value=2):
            self.assertEqual(trend_signal("trend_template.price_near_52_week_high", 80, frame)["state"], "fail")


class RiskSpineParityTests(unittest.TestCase):
    def test_the_initial_stop_ceiling_comes_from_the_registry(self) -> None:
        self.assertEqual(reduce_risk(CONVERGED)["verdict"], "BUY-READY")

        with threshold_moved("risk.initial_stop_and_reward", "initial_stop_ceiling_pct", value=5):
            result = reduce_risk(CONVERGED)

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("initial_stop_pct", result["failed"])

    def test_the_half_average_gain_multiple_comes_from_the_registry(self) -> None:
        with threshold_moved("risk.initial_stop_and_reward", "half_average_gain_multiple", value=0.25):
            result = reduce_risk(CONVERGED)

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("half_average_gain_cap", result["failed"])

    def test_the_reward_to_risk_minimum_comes_from_the_registry(self) -> None:
        with threshold_moved("risk.initial_stop_and_reward", "reward_to_risk_minimum", value=5):
            result = reduce_risk(CONVERGED)

        self.assertEqual(result["verdict"], "AVOID")
        self.assertIn("reward_to_risk", result["failed"])

    def test_the_breakeven_trigger_comes_from_the_registry(self) -> None:
        held = {
            "mode": "active",
            "as_of": "2026-08-21",
            "entry_price": 100.0,
            "entry_date": "2026-08-10",
            "stop_price": 90.0,
            "current_price": 132.0,
            "completed_price_path": {"state": "clear", "checked_level": 90.0, "from": "2026-08-10", "through": "2026-08-21", "bars_checked": 8},
        }

        self.assertTrue(reduce_risk(held)["risk_controls"]["breakeven_protection_required"])

        with threshold_moved("risk.profit_protection_at_3r", "breakeven_protection_trigger_r", value=9):
            self.assertFalse(reduce_risk(held)["risk_controls"]["breakeven_protection_required"])


if __name__ == "__main__":
    unittest.main()
