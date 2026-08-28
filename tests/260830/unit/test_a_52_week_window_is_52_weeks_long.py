"""A window that is not 52 weeks long cannot produce a 52-week high.

`min(252, len(close))` is a bar count with no coverage requirement, so a history of any
length at all produced a number the envelope labelled a 52-week extreme. The error it makes
is not noise, it is directional, and it runs opposite ways on the two criteria: a truncated
window has a higher low, so the distance above it shrinks and criterion 6 reads a **fail**
that a full year would have passed; and it has a lower high, so the distance below it
shrinks and criterion 7 reads a **pass** the year would have failed. Measured against the
full-year reading over 464 names, a 200-session window disagreed on 22 and 23 of them
respectively -- and never once in the other direction.

The false fail is the one that costs. `evaluate_eligibility` reads a standard `fail` before
the Primary Base route opens, so a stock too young to have a 52-week low was rejected on
its 52-week low -- by the route that exists for stocks too young to have one. That is the
constitution's own line inverted: unavailable evidence produced a guessed fail, and the
guess became AVOID.

The window is bounded by a date rather than a bar count for the same reason. Counting bars
made the window's length depend on how often the stock traded, so a name whose sessions were
thinned by a halt took its "52-week" extremes from a window reaching years back.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.minervini.eligibility import EligibilityEvidence, evaluate_eligibility
from scripts.minervini.technical import build_eligibility_evidence


ABOVE_LOW = "trend_template.price_above_52_week_low"
NEAR_HIGH = "trend_template.price_near_52_week_high"


def frame(closes: list[float], index: pd.DatetimeIndex, *, highs: list[float] | None = None) -> pd.DataFrame:
    close = pd.Series(closes, index=index)
    high = close * 1.01 if highs is None else pd.Series(highs, index=index)
    return pd.DataFrame(
        {
            "Open": close,
            "High": np.maximum(high, close),
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000),
        },
        index=index,
    )


def criteria(evidence: dict) -> dict:
    return {signal["id"]: signal for signal in evidence["trend_template"]}


class AYearIsAYear(unittest.TestCase):
    def test_a_history_short_of_a_year_measures_neither_52_week_criterion(self) -> None:
        """Eight months of trading, and the two criteria that need twelve say so."""

        sessions = 170
        closes = np.linspace(40.0, 50.0, sessions).tolist()
        index = pd.bdate_range(end="2026-08-27", periods=sessions)

        measured = criteria(build_eligibility_evidence(frame(closes, index), rs_rating=90))

        self.assertEqual(measured[ABOVE_LOW]["state"], "unavailable")
        self.assertEqual(measured[NEAR_HIGH]["state"], "unavailable")
        self.assertIsNone(measured[ABOVE_LOW]["basis"]["measured"])
        self.assertIsNone(measured[NEAR_HIGH]["basis"]["measured"])

    def test_an_unmeasurable_criterion_no_longer_rejects_a_young_stock(self) -> None:
        """The defect end to end, at the reducer that read the guessed fail.

        Eight months of trading, a real base near the end, and a breakout out of it -- the
        stock the Primary Base route was written for. It rose 26 percent across its whole
        listed life, so a window truncated to that life put it under the 30 percent floor,
        and the standard route returned AVOID before the recent-IPO route was consulted.
        """

        advance = np.linspace(42.0, 52.0, 130)
        base = np.concatenate([np.linspace(52.0, 45.0, 18), np.linspace(45.0, 51.0, 20)])
        closes = np.concatenate([advance, base, [53.0]]).tolist()
        index = pd.bdate_range(end="2026-08-27", periods=len(closes))

        measured = build_eligibility_evidence(
            frame(closes, index), rs_rating=90, primary_base_quality="supports"
        )
        result = evaluate_eligibility(EligibilityEvidence.from_mapping(measured))

        self.assertEqual(result.route, "recent_ipo_primary_base")
        self.assertEqual(result.eligibility_state, "eligible")
        self.assertEqual([signal.id for signal in result.signals if signal.state == "fail"], [])

    def test_the_window_reaches_back_a_year_and_not_however_far_252_bars_reach(self) -> None:
        """A name that trades one session in three, so 252 bars span three years.

        The bar count made the window's length a function of how often the stock traded.
        This one's spike is nineteen months old -- outside any 52-week window and inside a
        252-bar one -- so counting bars had it deciding a hard gate today.
        """

        sessions = 260
        closes = np.linspace(60.0, 150.0, sessions).tolist()
        # One session every third weekday: 260 bars now reach back roughly three years.
        index = pd.bdate_range(end="2026-08-27", periods=sessions * 3)[::3]
        highs = [close * 1.01 for close in closes]
        highs[120] = 260.0

        spike_age = (index[-1] - index[120]).days
        self.assertGreater(spike_age, 365, "the fixture must put the spike outside a 52-week window")

        measured = criteria(build_eligibility_evidence(frame(closes, index, highs=highs), rs_rating=90))

        self.assertEqual(measured[NEAR_HIGH]["state"], "pass")


if __name__ == "__main__":
    unittest.main()
