"""Every reading that says "latest" has to mean the quarter the company last filed.

A quarter filed without the figure a reading needs leaves that reading's series ending a
quarter earlier. Reading "the latest" off the series then promotes a stale quarter to the
company's current one, and the number goes out under a field name that says otherwise. The
band with the source's own window was repaired for this two rounds ago; the rest of the
readings on the same page were not, and neither was the trailing year the price is divided by.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


_ENDS = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def quarter(year: int, index: int, eps: float | None, revenue: float = 100.0) -> dict:
    fact = {"period": f"{year}-Q{index}", "end": f"{year}-{_ENDS[index]}", "revenue": revenue, "diluted_shares": 100.0}
    if eps is not None:
        fact["eps"] = eps
        fact["net_income"] = eps * 100
    return fact


# Eight quarters doubling year over year, then a ninth filed with revenue and no earnings.
_QUARTERS = [quarter(2024, index, eps) for index, eps in zip((1, 2, 3, 4), (0.10, 0.20, 0.30, 0.40))]
_QUARTERS += [quarter(2025, index, eps) for index, eps in zip((1, 2, 3, 4), (0.20, 0.40, 0.60, 0.80))]
_QUARTERS += [quarter(2026, 1, None, revenue=120.0)]


def read(**declared) -> dict:
    evidence = {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-05-01", "form": "10-Q", "accounting_basis": "US-GAAP", "quarterly": _QUARTERS, "annual": []}]}
    return evaluate_fundamentals(evidence, as_of="2026-05-08", **declared)


class TheLatestQuarterHasNoPairSoNoReadingClaimsOne(unittest.TestCase):
    def test_the_latest_filed_quarter_is_the_one_without_earnings(self) -> None:
        payload = read()

        self.assertEqual(payload["quarterly"]["latest_filed_period"], "2026-Q1")
        self.assertEqual([point["period"] for point in payload["quarterly"]["eps_yoy_growth"]][-1], "2025-Q4")

    def test_the_superperformance_band_does_not_publish_the_quarter_before(self) -> None:
        reading = read()["growth"]["superperformance_quarterly_earnings_growth"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "latest_filed_quarter_has_no_year_over_year_pair")

    def test_the_practitioner_band_does_not_publish_it_either(self) -> None:
        reading = read()["growth"]["practitioner_readings"]["zanger_quarterly_growth_target"]["band"]

        self.assertEqual(reading["state"], "unavailable")

    def test_the_sequential_run_is_not_read_from_a_stale_tail(self) -> None:
        reading = read()["growth"]["practitioner_readings"]["minervini_sequential_acceleration"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "latest_filed_quarter_has_no_year_over_year_pair")

    def test_the_window_stays_anchored_to_the_latest_filed_quarter(self) -> None:
        # Three quarters ending at 2025-Q4 are not "the most recent three quarters" when the
        # company has filed 2026-Q1 since.
        reading = read()["growth"]["minimum_quarterly_earnings_growth"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["window"], [])


class TodaysPriceNeedsAYearThatEndsAtTodaysQuarter(unittest.TestCase):
    """The trailing year ends where the filings end, and the filings end at 2026-Q1.

    Reading the last point of the earnings series instead put a year closing in December under
    a May price, and published it as `reported` with a route beside it. A denominator a quarter
    out of date is not a smaller error than a missing one -- it is the same error with a number
    on it.
    """

    def test_a_trailing_year_that_stops_short_leaves_the_multiple_unavailable(self) -> None:
        reading = read(last_close=100.0)["valuation"]["price_earnings_ratio"]

        self.assertIsNone(reading["trailing_12m_eps"])
        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["missing_inputs"], ["filed_quarters_for_a_complete_trailing_year"])


if __name__ == "__main__":
    unittest.main()
