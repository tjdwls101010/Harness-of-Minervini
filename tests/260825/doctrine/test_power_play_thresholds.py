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


class TheFlagIsBoundedTheWayTheSourceBoundedIt(unittest.TestCase):
    """"the following criteria must be met: ... not correcting more than 20 to 25 percent over
    a period of three to six weeks (some can emerge after only 12 days)."

    The source gave two ranges inside filter language, so each range's loose end is a limit and
    the range itself still reports where the measurement sat. Both are needed: without the gate
    a ten-week flag and a forty percent correction qualify, and without the band a twenty
    percent correction and a twenty-five percent one read identically.
    """

    def test_a_flag_past_six_weeks_is_not_a_power_play_flag(self):
        self.assertEqual(doctrine.evaluate_gate(CLAIM, "flag_maximum_weeks", 10.0)["state"], "fail")

    def test_a_flag_inside_six_weeks_clears_the_limit(self):
        self.assertEqual(doctrine.evaluate_gate(CLAIM, "flag_maximum_weeks", 4.0)["state"], "pass")

    def test_a_correction_past_twenty_five_percent_is_not_a_power_play_flag(self):
        self.assertEqual(doctrine.evaluate_gate(CLAIM, "flag_maximum_decline_gate_pct", 33.6)["state"], "fail")

    def test_the_band_still_reports_where_inside_the_range_it_sat(self):
        """A gate cannot say that twenty percent and twenty-five percent are different."""

        shallow = doctrine.evaluate_band(CLAIM, "flag_maximum_decline_pct", 20.0)
        deep = doctrine.evaluate_band(CLAIM, "flag_maximum_decline_pct", 24.9)

        self.assertEqual(shallow["measured"], 20.0)
        self.assertEqual(deep["measured"], 24.9)

    def test_the_twelve_day_exception_survives_the_duration_band(self):
        """"some can emerge after only 12 days" -- 2.4 weeks is short of the range and still legal.

        The band's report about a short flag must not become a verdict about it; the sessions
        gate is what the source made binding at the low end.
        """
        self.assertEqual(doctrine.evaluate_gate(CLAIM, "flag_minimum_sessions", 12)["state"], "pass")
        self.assertNotIn(doctrine.evaluate_band(CLAIM, "flag_duration_weeks", 2.4)["state"], {"fail", "pass"})


if __name__ == "__main__":
    unittest.main()
