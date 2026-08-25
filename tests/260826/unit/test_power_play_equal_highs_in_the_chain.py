"""Advancing the chain past a bar is a statement about that bar, not about its price.

The descent walks the candidate tops downward, and a bar it declines has to stop being found.
Doing that by lowering the price ceiling below it looks equivalent and is not: two sessions can
print exactly the same high, and one of them can be a confirmed turning point while the other is
not. Lowering the ceiling past the first deletes the second, and a reviewer reproduced `qualified`
over a confirmed top failing both the six-week limit and the depth gate that way.

Named by date, the search advances and takes nothing else with it.

Pinned at the measurement rather than through a full chain. The reviewer's frame was described
rather than published, and every chain geometry tried here puts the confirmed high *first* --
the segmenter anchors the earliest bar of a plateau, and the search takes the earliest session
that printed its maximum, so the two rules agree on which of a pair of equal highs is reached.
What is certain is that the primitive below is the one the walk turns on, and that naming a date
can never remove a session naming a price would have kept.
"""

from __future__ import annotations

import pandas as pd
import unittest

from scripts.minervini.power_play import measure_power_play
from scripts.minervini.power_play_evidence import compile_power_play_spec


def two_sessions_at_one_price():
    """A frame whose highest price is printed twice, weeks apart."""
    closes = [50.0] * 40 + [90.0] * 5 + [70.0] * 10 + [90.0] * 5 + [60.0] * 20
    index = pd.bdate_range("2026-01-02", periods=len(closes))
    frame = pd.DataFrame({"Open": closes, "Close": closes}, index=index)
    frame["High"] = closes
    frame["Low"] = [close * 0.99 for close in closes]
    frame["Volume"] = 1_000_000.0
    frame["Stock Splits"] = 0.0
    frame["Dividends"] = 0.0
    return frame


class AnExcludedSessionTakesNoOtherWithIt(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = two_sessions_at_one_price()
        self.spec = compile_power_play_spec()
        self.first = measure_power_play(self.frame, self.spec)

    def test_the_fixture_really_prints_the_high_twice(self) -> None:
        highs = self.frame["High"]
        self.assertEqual(int((highs == highs.max()).sum()), 10)

    def test_the_search_takes_the_first_session_that_printed_it(self) -> None:
        self.assertEqual(self.first["peak_high"], float(self.frame["High"].max()))

    def test_excluding_that_session_finds_the_next_one_at_the_same_price(self) -> None:
        again = measure_power_play(
            self.frame, self.spec, excluding=frozenset({self.first["peak_date"]})
        )

        self.assertEqual(again["peak_high"], self.first["peak_high"])
        self.assertGreater(again["peak_date"], self.first["peak_date"])

    def test_where_lowering_the_price_bound_would_have_lost_it(self) -> None:
        """The behaviour being replaced, kept as the reason the date exists."""
        below = measure_power_play(self.frame, self.spec, below=self.first["peak_high"])

        self.assertLess(below["peak_high"], self.first["peak_high"])


if __name__ == "__main__":
    unittest.main()
