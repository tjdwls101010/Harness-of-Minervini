"""Reading the extremes off two more columns made this function depend on them.

Its own docstring says it rejects missing OHLC evidence, and until this slice that was true
because `Close` was the only column it read. `High` and `Low` arrived without the same
guarantee: a NaN is skipped by `min` and `max`, so a year with one unknown low published a
definitive `fail` on a floor it could not have measured -- the guessed pass-or-fail the
constitution refuses, reintroduced by the change that was meant to remove one.

The two ends are separate criteria and fail separately. An unknown low says nothing about
whether the high is known, and killing both on either would refuse a reading that is there.

Dropping the offending session instead would be the worse repair: measuring on the survivors
is what made a history half full of holes read as a short one, which is the defect the shared
price reader exists to stop. A session whose prices are missing is still a session the window
covers.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.minervini.technical import build_eligibility_evidence


ABOVE_LOW = "trend_template.price_above_52_week_low"
NEAR_HIGH = "trend_template.price_near_52_week_high"


def bars(*, sessions: int = 300) -> pd.DataFrame:
    index = pd.bdate_range(end="2026-08-27", periods=sessions)
    close = pd.Series(np.linspace(60.0, 150.0, sessions), index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(sessions, 1_000_000.0)},
        index=index,
    )


def criteria(frame: pd.DataFrame) -> dict:
    evidence = build_eligibility_evidence(frame, rs_rating=90)
    return {signal["id"]: signal for signal in evidence["trend_template"]}


class AnExtremeNeedsItsPrices(unittest.TestCase):
    def test_an_unknown_low_inside_the_window_leaves_the_floor_unmeasured(self) -> None:
        frame = bars()
        frame.iloc[150, frame.columns.get_loc("Low")] = np.nan

        measured = criteria(frame)

        self.assertEqual(measured[ABOVE_LOW]["state"], "unavailable")
        self.assertIsNone(measured[ABOVE_LOW]["basis"]["measured"])
        # The other end was measured, and says so.
        self.assertEqual(measured[NEAR_HIGH]["state"], "pass")

    def test_an_unknown_high_inside_the_window_leaves_the_ceiling_unmeasured(self) -> None:
        frame = bars()
        frame.iloc[150, frame.columns.get_loc("High")] = np.nan

        measured = criteria(frame)

        self.assertEqual(measured[NEAR_HIGH]["state"], "unavailable")
        self.assertIsNone(measured[NEAR_HIGH]["basis"]["measured"])
        self.assertEqual(measured[ABOVE_LOW]["state"], "pass")

    def test_an_unknown_price_before_the_window_does_not_reach_it(self) -> None:
        """A gap the year does not cover is not this year's gap."""

        frame = bars(sessions=600)
        frame.iloc[10, frame.columns.get_loc("Low")] = np.nan

        self.assertEqual(criteria(frame)[ABOVE_LOW]["state"], "pass")

    def test_a_repeated_column_is_refused_by_name_rather_than_deep_inside(self) -> None:
        """Two columns called High make `bars["High"]` a frame, and `float()` of one is a crash.

        A provider flattening a multi-level header produces exactly this, and the shared price
        reader already names it. Reading the extremes off two more columns brought the shape
        here too, where it surfaced as a TypeError from the arithmetic instead.
        """

        frame = bars()
        duplicated = pd.concat([frame, frame[["High"]]], axis=1)

        with self.assertRaises(ValueError) as raised:
            build_eligibility_evidence(duplicated, rs_rating=90)

        self.assertIn("repeat", str(raised.exception).lower())


if __name__ == "__main__":
    unittest.main()
