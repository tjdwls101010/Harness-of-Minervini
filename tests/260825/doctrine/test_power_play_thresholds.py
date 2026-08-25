"""The Power Play criteria, compared with the sentence they were compiled from.

Every number here comes out of one quotation, so the test's job is to hold the compiled
threshold against the words rather than against the code that reads it. A comparator that
says the wrong thing passes silently forever otherwise: nothing downstream can tell "less
than eight weeks" from "eight weeks or less".
"""

from __future__ import annotations

import unittest

from scripts.minervini import doctrine


CLAIM = "fundamentals.power_play_exception"


class TheAdvanceIsBoundedTheWayTheSourceBoundedIt(unittest.TestCase):
    def test_exactly_eight_weeks_is_not_less_than_eight_weeks(self):
        """"shoots the stock price up 100 percent or more in less than eight weeks"."""

        signal = doctrine.evaluate_gate(CLAIM, "advance_maximum_weeks", 8.0)

        self.assertEqual(signal["state"], "fail")

    def test_a_shorter_advance_clears_it(self):
        self.assertEqual(doctrine.evaluate_gate(CLAIM, "advance_maximum_weeks", 7.8)["state"], "pass")


if __name__ == "__main__":
    unittest.main()
