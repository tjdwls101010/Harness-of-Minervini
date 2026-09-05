"""Three places where a number was rounded, dropped or replaced before it was used.

A trailing year of real but tiny earnings was rounded to zero and then called a company that
did not earn, and a sum too large for binary64 was reported as quarters nobody filed. The
highest trailing year on file was thrown away the moment the current one had to be rolled
forward, so a turnaround compared itself with a peak it had already beaten. And a month that
had reached the last day its start date can reach was called unfinished, which is thirty days
of a source's window in the cases where a fiscal quarter ends on the thirty-first.
"""

from __future__ import annotations

from tests.filings import evidence, quarter

from datetime import date
import unittest

from scripts.minervini.fundamentals import _completed_months, _trailing_twelve_months, evaluate_fundamentals


def point(period: str, end: str, value: float) -> dict:
    return {"period": period, "end": end, "value": value}


class EarningsTooSmallToPrintAreStillEarnings(unittest.TestCase):
    def test_a_trailing_year_that_rounds_to_zero_is_not_a_company_that_lost_money(self) -> None:
        quarters = [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", 1e-12) for n in range(4)]
        reading = evaluate_fundamentals(evidence(quarters), as_of="2026-05-08", last_close=1.0)["valuation"]["price_earnings_ratio"]

        self.assertEqual(reading["state"], "reported")
        self.assertEqual(reading["pe_ratio"], 250000000000.0)

    def test_a_sum_beyond_what_the_arithmetic_can_hold_says_so(self) -> None:
        quarters = [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", 1e308) for n in range(4)]
        reading = evaluate_fundamentals(evidence(quarters), as_of="2026-05-08", last_close=1.0)["valuation"]["price_earnings_ratio"]

        self.assertEqual(reading["state"], "not_meaningful")
        self.assertEqual(reading["reason"], "trailing_12m_eps_beyond_arithmetic_range")


class ThePriorPeakIsTheHighestOnFileByEitherRoute(unittest.TestCase):
    """Which route the current year needed says nothing about the years before it.

    A company whose four filed quarters once summed to forty, and whose recent quarters have to
    be rolled forward, had the forty discarded -- so the turnaround criterion compared five
    against four and a half and reported the old peak recovered.
    """

    def test_a_direct_window_still_counts_toward_the_prior_peak(self) -> None:
        series = [point(f"2023-Q{n + 1}", f"2023-{(n + 1) * 3:02d}-28", 10.0) for n in range(4)]
        series += [point("2024-Q1", "2024-03-28", 1.0), point("2024-Q2", "2024-06-28", 1.0)]
        series += [point("2025-Q1", "2025-03-28", 1.5), point("2025-Q2", "2025-06-28", 1.5)]
        annual = [point("2024", "2024-12-31", 4.0)]

        current, peak, route = _trailing_twelve_months(series, annual)

        self.assertEqual(route, "annual_rolled_forward_by_filed_quarters")
        self.assertEqual(current, 5.0)
        self.assertEqual(peak, 40.0)


class AMonthEndsOnTheLastDayItCanReach(unittest.TestCase):
    def test_february_completes_a_month_that_began_on_the_thirty_first(self) -> None:
        self.assertEqual(_completed_months(date(2025, 1, 31), date(2025, 2, 28)), 1)

    def test_a_leap_day_anniversary_lands_on_the_twenty_eighth(self) -> None:
        self.assertEqual(_completed_months(date(2024, 2, 29), date(2025, 2, 28)), 12)

    def test_a_day_short_of_the_last_day_is_still_short(self) -> None:
        self.assertEqual(_completed_months(date(2025, 1, 31), date(2025, 2, 27)), 0)
        self.assertEqual(_completed_months(date(2025, 3, 31), date(2026, 3, 30)), 11)



class TheRouteTravelsWithEveryTrailingYear(unittest.TestCase):
    """Three blocks publish a trailing year and only one of them said where it came from.

    The turnaround criterion can reach `satisfied` on that number over a failed gate, and the
    breakout multiple is the denominator of the whole expansion reading, so both need the same
    disclosure the price-earnings block already carries.
    """

    @staticmethod
    def two_full_years() -> list[dict]:
        return [quarter(f"{year}-Q{n + 1}", f"{year}-{(n + 1) * 3:02d}-30", 0.25 * (2 if year == 2025 else 1)) for year in (2024, 2025) for n in range(4)]

    def test_the_turnaround_names_the_route_of_the_year_it_read(self) -> None:
        reading = evaluate_fundamentals(evidence(self.two_full_years()), as_of="2026-05-08", leader_category="turnaround")["category_reading"]["readings"]

        self.assertEqual(reading["turnaround_qualifying_criteria"]["trailing_12m_route"], "four_consecutive_filed_quarters")

    def test_the_breakout_multiple_names_the_route_of_its_denominator(self) -> None:
        reading = evaluate_fundamentals(evidence(self.two_full_years()), as_of="2026-05-08", last_close=40.0, breakout_close=20.0, breakout_date="2026-03-02")["valuation"]["pe_expansion"]

        self.assertEqual(reading["trailing_12m_route_at_breakout"], "four_consecutive_filed_quarters")



class TheShareBaseTheTrailingYearWasBuiltFrom(unittest.TestCase):
    """A rolled-forward year adds a fiscal year's per-share figure to quarters filed after it.

    A split between the two restates one side and not the other, and no arithmetic here can
    see that: the split is a price-history fact and this evaluator holds filings. So the two
    filed counts are published side by side, the shape decision 273 chose for the compound
    rates -- the reader sees a hundred against four hundred and knows what happened.
    """

    def test_the_two_counts_travel_with_the_multiple(self) -> None:
        quarters = [quarter(f"{year}-Q{n + 1}", f"{year}-{(n + 1) * 3:02d}-30", 0.25) for year in (2024, 2025) for n in range(4)]
        reading = evaluate_fundamentals(evidence(quarters, [{"period": "2024", "end": "2024-12-31", "eps": 1.0, "diluted_shares": 25.0}]), as_of="2026-05-08", last_close=10.0)["valuation"]["price_earnings_ratio"]

        self.assertEqual(reading["trailing_12m_diluted_shares"], {"latest_annual": 25.0, "latest_quarter": 100.0})


if __name__ == "__main__":
    unittest.main()
