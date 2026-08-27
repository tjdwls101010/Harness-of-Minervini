"""Rules the seventh review round put in: placeability, equality, and which column a block reads."""

from __future__ import annotations

from datetime import date
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from scripts.minervini import management_evidence
from scripts.minervini.management_evidence import build_management_evidence
from scripts.minervini.risk import reduce_risk


AS_OF = "2026-08-21"
DEFENSE = "management.market_defense_tightens_stops"
EARNINGS = "management.earnings_awareness_while_holding"


def frame(closes: list[float], *, end: str = "2025-12-26", volumes: list[float] | None = None) -> pd.DataFrame:
    index = pd.bdate_range(end=end, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": volumes if volumes is not None else np.full(len(close), 1_000_000.0)},
        index=index,
    )


def held(**extra: object) -> dict:
    stop = float(extra.pop("stop_price", 90.0))
    return {
        "mode": "active",
        "as_of": AS_OF,
        "entry_price": 100.0,
        "entry_date": "2026-08-10",
        "stop_price": stop,
        "current_price": float(extra.pop("current_price", 104.0)),
        "completed_price_path": {"state": "clear", "checked_level": stop, "from": "2026-08-10", "through": AS_OF, "bars_checked": 9},
        **extra,
    }


class ATighterStopHasToBePlaceable(unittest.TestCase):
    def test_a_tightened_level_above_the_last_price_is_reported_and_not_acted_on(self) -> None:
        result = reduce_risk(held(market={"state": "defensive"}, current_price=92.0))

        self.assertEqual(result["verdict"], "HOLD")
        self.assertEqual([action["doctrine_id"] for action in result["management_actions"]], [])
        defense = result["management_evidence"]["market_defense"]
        self.assertIs(defense["tighten_to_is_placeable"], False)
        self.assertEqual(defense["not_placeable_reason"], "tightened_level_is_at_or_above_the_last_price")

    def test_a_level_below_the_last_price_still_raises_the_stop(self) -> None:
        result = reduce_risk(held(market={"state": "defensive"}, current_price=104.0))

        self.assertIn(DEFENSE, [action["doctrine_id"] for action in result["management_actions"]])


class AReportDueTodayIsNotAheadOfToday(unittest.TestCase):
    def test_earnings_on_the_as_of_session_is_its_own_state_and_still_a_review(self) -> None:
        result = reduce_risk(held(earnings_date=AS_OF))

        earnings = result["management_evidence"]["earnings"]
        self.assertIs(earnings["ahead"], False)
        self.assertIs(earnings["due_on_as_of"], True)
        review = next(action for action in result["management_actions"] if action["doctrine_id"] == EARNINGS)
        self.assertEqual(review["reason"], "earnings_due_on_as_of")


class EqualityIsNeitherAPullbackNorANewHigh(unittest.TestCase):
    def test_a_flat_stretch_has_no_reaction_and_no_new_high(self) -> None:
        bars = frame([100.0] * 30)
        result = build_management_evidence(bars, entry_date=bars.index[26].date(), as_of=bars.index[-1].date(), breakout_date=bars.index[26].date())

        block = result["post_breakout_behavior"]
        self.assertEqual(block["natural_reactions"], [])
        self.assertEqual(block["sessions_since_new_high"], 3)
        self.assertEqual(block["last_new_closing_high"], bars.index[26].date().isoformat())


class ABlockReadsOnlyItsOwnColumns(unittest.TestCase):
    def test_a_broken_volume_does_not_void_an_average_of_closes(self) -> None:
        volumes = [1_000_000.0] * 29 + [float("nan")]
        bars = frame([100.0] * 30, volumes=volumes)
        result = build_management_evidence(bars, entry_date=bars.index[26].date(), as_of=bars.index[-1].date())

        self.assertEqual(result["twenty_day_average"]["state"], "above")

    def test_a_broken_close_anywhere_voids_the_recursive_average(self) -> None:
        closes = [100.0 + index for index in range(120)]
        bars = frame(closes)
        bars.iloc[30, bars.columns.get_loc("Close")] = float("nan")
        result = build_management_evidence(bars, entry_date=bars.index[110].date(), as_of=bars.index[-1].date(), management_average="ema21")

        # The EMA is recursive from the first bar, so the bad close is inside its computation.
        self.assertEqual(result["moving_average_trail"]["reason"], "invalid_ohlc_history")
        self.assertEqual(result["moving_average_extension"]["reason"], "invalid_ohlc_history")


class TheFirstSessionsNameTheirGaps(unittest.TestCase):
    def test_a_breakout_too_early_for_a_volume_baseline_says_so(self) -> None:
        bars = frame([100.0] * 10)
        result = build_management_evidence(bars, entry_date=bars.index[0].date(), as_of=bars.index[-1].date(), breakout_date=bars.index[0].date())

        block = result["post_breakout_behavior"]["first_sessions"]
        self.assertEqual(block["volume_baseline_reason"], "insufficient_history_for_volume_baseline")
        self.assertEqual(block["missing_inputs"], ["volume_baseline"])


class TheSlopeWindowsComeFromTheRegistry(unittest.TestCase):
    def test_the_slope_reads_the_registered_lengths(self) -> None:
        bars = frame([100.0 + index * 0.1 for index in range(120)])
        real = management_evidence.doctrine.parameter

        def shorter(claim_id: str, name: str) -> float:
            if claim_id == "convention.long_average_slope_window":
                return {"long_average_sessions": 50, "slope_lookback_sessions": 5}[name]
            return real(claim_id, name)

        with mock.patch.object(management_evidence.doctrine, "parameter", side_effect=shorter):
            block = build_management_evidence(bars, entry_date=bars.index[110].date(), as_of=bars.index[-1].date())["stage3_transition"]

        self.assertEqual(block["sma200_average_sessions"], 50)
        self.assertEqual(block["sma200_lookback_sessions"], 5)
        self.assertEqual(block["sma200_state"], "reported")

    def test_exactly_enough_history_publishes_the_slope(self) -> None:
        enough = frame([100.0] * 220)
        short = frame([100.0] * 219)

        self.assertEqual(build_management_evidence(enough, entry_date=enough.index[200].date(), as_of=enough.index[-1].date())["stage3_transition"]["sma200_state"], "reported")
        self.assertEqual(build_management_evidence(short, entry_date=short.index[200].date(), as_of=short.index[-1].date())["stage3_transition"]["sma200_state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
