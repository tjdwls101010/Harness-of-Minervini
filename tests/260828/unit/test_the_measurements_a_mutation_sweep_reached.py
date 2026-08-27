"""Four measurements a mutation sweep changed without any test noticing.

Each of these had a rule written into the code and a reason written beside it, and each
survived being inverted. A rule nothing tests is a rule the next edit removes for free, so
this file is the sweep's report turned into the assertions that were missing.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float, *, revenue: float = 100.0, net_income: float | None = None) -> dict:
    return {"period": period, "end": end, "eps": eps, "revenue": revenue, "net_income": eps * 10 if net_income is None else net_income, "diluted_shares": 100.0}


def annual(year: int, eps: float) -> dict:
    return {"period": str(year), "end": f"{year}-12-31", "eps": eps, "revenue": 100.0, "diluted_shares": 100.0}


def evidence(quarters: list[dict], years: list[dict] | None = None) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": quarters, "annual": years or []}]}


def read(quarters: list[dict], years: list[dict] | None = None, **declared) -> dict:
    return evaluate_fundamentals(evidence(quarters, years), as_of="2026-05-08", **declared)


class TheQuarterBeforeTheFirstIsLastYears(unittest.TestCase):
    """`_previous_quarter` is the only thing that knows a year ends between Q4 and Q1.

    Four quarters that cross a new year are still four consecutive quarters. Answering
    `2026-Q4` for what precedes `2026-Q1` breaks every window that spans a year boundary, and
    it breaks them silently -- the trailing year simply stops existing.
    """

    def test_four_quarters_across_a_new_year_are_still_a_trailing_year(self) -> None:
        quarters = [
            quarter("2025-Q2", "2025-06-30", 0.25),
            quarter("2025-Q3", "2025-09-30", 0.25),
            quarter("2025-Q4", "2025-12-31", 0.25),
            quarter("2026-Q1", "2026-03-31", 0.25),
        ]
        reading = read(quarters, last_close=50.0)["valuation"]["price_earnings_ratio"]

        self.assertEqual(reading["trailing_12m_eps"], 1.0)
        self.assertEqual(reading["trailing_12m_route"], "four_consecutive_filed_quarters")


class TooFewQuartersToJudgeIsNotAFailedGate(unittest.TestCase):
    """The count the source stated decides how much history Code 33 needs to say anything.

    With fewer judgeable quarters than the source asked for, the reading is unavailable. Taking
    the count from anywhere else lets a two-quarter history reach the gate and fail it, which
    reports a stock as not in a Code 33 situation when nobody could tell.
    """

    def test_two_judgeable_quarters_leave_the_reading_unavailable(self) -> None:
        quarters = [
            quarter("2024-Q1", "2024-03-31", 0.10),
            quarter("2024-Q2", "2024-06-30", 0.10),
            quarter("2024-Q3", "2024-09-30", 0.10),
            quarter("2025-Q1", "2025-03-31", 0.20),
            quarter("2025-Q2", "2025-06-30", 0.30),
            quarter("2025-Q3", "2025-09-30", 0.45),
        ]
        # Only 2025-Q2 and 2025-Q3 can be judged: 2025-Q1 has no 2024-Q4 before it.
        reading = read(quarters)["growth"]["code_33_triple_acceleration"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["reason"], "insufficient_quarters_for_triple_acceleration")
        self.assertEqual(reading["judged_quarters"], 2)


class NearThePeakIsNotAtThePeak(unittest.TestCase):
    """The claim's second route is "back to its old peak", and near it is not quantified.

    Ninety percent of the peak is a number nobody in the corpus named. Accepting it satisfies
    the turnaround criterion for a stock whose trailing year never recovered, which is the one
    thing this criterion exists to refuse.
    """

    def test_a_trailing_year_just_short_of_the_peak_does_not_satisfy_the_criterion(self) -> None:
        base = [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", 0.10) for n in range(4)]
        recent = [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", eps) for n, eps in enumerate([0.50, 0.12, 0.06, 0.06])]
        reading = read(base + recent, leader_category="turnaround")["category_reading"]["readings"]["turnaround_qualifying_criteria"]

        self.assertEqual(reading["trailing_12m_eps"], 0.74)
        self.assertEqual(reading["trailing_12m_eps_prior_peak"], 0.82)
        self.assertIs(reading["trailing_12m_eps_at_or_above_prior_peak"], False)
        self.assertIs(reading["satisfied"], False)


class AStretchCannotSpanAYearNobodyFiled(unittest.TestCase):
    """The source's five-to-ten-year stretch is five to ten years the company actually filed.

    With one year missing, no window of six filed rows is six consecutive years, so there is no
    stretch to report. Compounding the six rows anyway averages two eras and calls the result
    one company's best run.
    """

    def test_a_missing_year_leaves_no_best_stretch_at_all(self) -> None:
        years = [annual(year, 1.0 * (1.4 ** (year - 2016))) for year in range(2016, 2026) if year != 2020]
        reading = read([], years, leader_category="market_leader")["category_reading"]["readings"]["market_leader_earnings_growth_pace"]

        self.assertEqual(reading["best_stretch"]["state"], "unavailable")
        self.assertNotIn("best_stretch_span_years", reading)


if __name__ == "__main__":
    unittest.main()
