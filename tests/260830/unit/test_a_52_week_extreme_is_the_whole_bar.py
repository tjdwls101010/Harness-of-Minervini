"""The 52-week high and low are what the stock traded at, not where it happened to close.

The two criteria that read them are hard gates, and the source settles neither: it says
"at least 30 percent above its 52-week low" and "within at least 25 percent of its 52-week
high" without ever saying whether the extreme is a closing value or an intraday one. What
settles it is that this harness already answered the question one module over --
`market_evidence._leader_price_behavior` reads a leader's distance from a 52-week high off
`max(highs)` -- so measuring the same phrase off closes here made "52-week high" mean two
different things inside one harness, and the eligibility half was the looser of the two.

The two criteria move in opposite directions under the change, which is why one fixture
cannot show both. An intraday low is at or below the closing low, so the distance above it
can only grow and criterion 6 can only get easier; an intraday high is at or above the
closing high, so the distance below it can only grow and criterion 7 can only get harder.
Measured over 464 names on 2026-08-27, criterion 7 lost 8 passes and criterion 6 gained 28.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.minervini.technical import build_eligibility_evidence


def history(closes: list[float], *, highs: list[float] | None = None, lows: list[float] | None = None) -> pd.DataFrame:
    """Bars whose wicks a test can name, so an extreme can sit off the closing series."""

    index = pd.bdate_range("2024-01-02", periods=len(closes))
    close = pd.Series(closes, index=index)
    high = close * 1.01 if highs is None else pd.Series(highs, index=index)
    low = close * 0.99 if lows is None else pd.Series(lows, index=index)
    return pd.DataFrame(
        {
            "Open": close,
            "High": np.maximum(high, close),
            "Low": np.minimum(low, close),
            "Close": close,
            "Volume": np.full(len(close), 1_000_000),
        },
        index=index,
    )


def criteria(evidence: dict) -> dict:
    return {signal["id"]: signal for signal in evidence["trend_template"]}


class AnExtremeIsTakenFromTheWholeBar(unittest.TestCase):
    def test_a_spike_above_the_closing_high_is_the_52_week_high(self) -> None:
        """One session that traded far above where it closed, and never came back.

        The closing series never sees it, so the stock reads 20 percent below its high and
        passes; the tape saw it, and the stock is 33 percent below what it actually traded at.
        """

        closes = np.linspace(60.0, 150.0, 300).tolist()
        peak = 225.0
        highs = [close * 1.01 for close in closes]
        highs[200] = peak

        evidence = build_eligibility_evidence(history(closes, highs=highs), rs_rating=90)
        near_high = criteria(evidence)["trend_template.price_near_52_week_high"]

        self.assertEqual(near_high["state"], "fail")
        self.assertAlmostEqual(near_high["basis"]["measured"], (1 - closes[-1] / peak) * 100, places=4)

    def test_an_undercut_below_the_closing_low_is_the_52_week_low(self) -> None:
        """The same bar, the other end -- and the other direction.

        A shakeout that printed below every close raises the distance above the low, so a
        stock the closing series held just under the 30 percent line clears it. The gate the
        source states is a floor, and a lower low can only put the price further above it.
        """

        closes = np.linspace(100.0, 128.0, 300).tolist()
        trough = 90.0
        lows = [close * 0.99 for close in closes]
        lows[60] = trough

        on_closes = build_eligibility_evidence(history(closes), rs_rating=90)
        with_wick = build_eligibility_evidence(history(closes, lows=lows), rs_rating=90)

        self.assertEqual(criteria(on_closes)["trend_template.price_above_52_week_low"]["state"], "fail")
        above_low = criteria(with_wick)["trend_template.price_above_52_week_low"]
        self.assertEqual(above_low["state"], "pass")
        self.assertAlmostEqual(above_low["basis"]["measured"], (closes[-1] / trough - 1) * 100, places=4)


if __name__ == "__main__":
    unittest.main()
