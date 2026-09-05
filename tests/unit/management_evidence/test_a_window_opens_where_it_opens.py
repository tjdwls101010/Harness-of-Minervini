"""Where a measurement's own window starts, and at what precision its limit is printed.

An event stamped on the session a window opens on is the coordinate system that window is
entirely inside. An event one session later is inside the window. Two blocks were passing
neighbouring positions to that question and getting the opposite answers. And a cap printed
beside the measurement it bounds has to be printed at the precision the measurement is.
"""

from __future__ import annotations

from datetime import date
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.management_evidence import build_management_evidence
from scripts.minervini.risk import reduce_risk


def frame(closes: np.ndarray, *, splits: dict[int, float] | None = None) -> pd.DataFrame:
    index = pd.bdate_range("2026-05-01", periods=len(closes))
    bars = pd.DataFrame(
        {"Open": closes, "High": closes * 1.01, "Low": closes * 0.99, "Close": closes, "Volume": np.full(len(closes), 1_000_000.0), "Stock Splits": np.zeros(len(closes))},
        index=index,
    )
    for position, factor in (splits or {}).items():
        bars.iloc[position, bars.columns.get_loc("Stock Splits")] = factor
    return bars


class TheExtensionIsMeasuredFromWhereTheBaseWasDeclared(unittest.TestCase):
    def test_a_split_the_session_after_entry_is_inside_the_window(self) -> None:
        # The base top is in the coordinate system the position was entered in, and the last
        # close is on the far side of the event: the percentage between them is arithmetic
        # over two different shares.
        bars = frame(np.r_[np.full(61, 100.0), np.full(9, 50.0)], splits={61: 2.0})
        block = build_management_evidence(bars, entry_date=bars.index[60].date(), as_of=bars.index[-1].date(), base_top=100.0)["base_extension"]

        self.assertEqual(block["state"], "unavailable")
        self.assertEqual(block["reason"], "share_split_inside_window")
        self.assertEqual(block["date"], bars.index[61].date().isoformat())

    def test_a_split_on_the_entry_session_is_the_system_the_position_was_opened_in(self) -> None:
        bars = frame(np.r_[np.full(60, 100.0), np.full(10, 50.0)], splits={60: 2.0})
        block = build_management_evidence(bars, entry_date=bars.index[60].date(), as_of=bars.index[-1].date(), base_top=50.0)["base_extension"]

        self.assertEqual(block["state"], "reported")
        self.assertEqual(block["extension_pct"], 0.0)


class TheAdvanceBeginsInWhicheverSystemItsFirstSessionPrinted(unittest.TestCase):
    def test_a_split_on_the_stage2_anchor_does_not_refuse_the_decline(self) -> None:
        closes = np.full(60, 100.0)
        closes[31] = 90.0
        bars = frame(closes, splits={20: 2.0})
        block = build_management_evidence(bars, entry_date=bars.index[40].date(), as_of=bars.index[-1].date(), stage2_start=bars.index[20].date())["largest_decline_since_stage2_start"]

        self.assertEqual(block["state"], "reported")
        self.assertEqual(block["measured_from"], bars.index[20].date().isoformat())
        self.assertEqual(block["daily"]["largest_pct"], -10.0)

    def test_a_split_the_session_after_the_anchor_still_refuses_it(self) -> None:
        closes = np.full(60, 100.0)
        closes[31] = 90.0
        bars = frame(closes, splits={21: 2.0})
        block = build_management_evidence(bars, entry_date=bars.index[40].date(), as_of=bars.index[-1].date(), stage2_start=bars.index[20].date())["largest_decline_since_stage2_start"]

        self.assertEqual(block["state"], "unavailable")
        self.assertEqual(block["date"], bars.index[21].date().isoformat())


class ACapIsPrintedAtThePrecisionItIsCheckedAt(unittest.TestCase):
    def test_the_half_average_gain_cap_is_not_tidied_below_the_stop_it_admits(self) -> None:
        result = reduce_risk({
            "mode": "prospective",
            "market": "favorable",
            "eligibility": "eligible",
            "setup": "ready",
            "fundamentals": "supports_convergence",
            "entry_price": 100.0,
            "stop_price": 99.499996,
            "upside_price": 102.0,
            "average_gain_pct": 1.00001,
        })

        controls = result["risk_controls"]
        self.assertNotIn("half_average_gain_cap", result["failed"])
        self.assertGreaterEqual(controls["half_average_gain_cap_pct"], controls["initial_stop_pct"])


if __name__ == "__main__":
    unittest.main()
