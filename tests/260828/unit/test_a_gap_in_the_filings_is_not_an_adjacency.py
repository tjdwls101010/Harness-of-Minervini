"""Two periods either sit next to each other on the calendar or they do not, and a filter cannot tell.

Every multi-period reading here was picking values by position after filtering the rows that
carried the metric. A company that filed no EPS for 2024 therefore had its 2022 and 2023 figures
compared and published under the periods 2023 and 2024; four annual rows spanning 2020 to 2025
were compounded as a three-year rate; and a quarter missing from the middle of a series was
treated as adjacent to the one before the gap.

The period label is the only thing that knows. It travels with the value now, and a reading whose
periods are not consecutive is unavailable with the reason rather than computed anyway.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, eps: float, revenue: float = 100.0, net_income: float = 10.0) -> dict:
    ends = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}
    year, label = period.split("-")
    return {"period": period, "end": f"{year}-{ends[label]}", "eps": eps, "revenue": revenue, "net_income": net_income, "diluted_shares": 100.0}


def evidence(quarters: list[dict], annual: list[dict]) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-20", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": quarters, "annual": annual}]}


class AnnualGrowthNamesTheYearsItUsed(unittest.TestCase):
    def test_a_year_with_no_earnings_filed_leaves_the_rate_unread(self) -> None:
        annual = [
            {"period": "2022", "end": "2022-12-31", "eps": 1.0, "revenue": 100.0},
            {"period": "2023", "end": "2023-12-31", "eps": 2.0, "revenue": 110.0},
            {"period": "2024", "end": "2024-12-31", "revenue": 121.0},
        ]
        result = evaluate_fundamentals(evidence([], annual), as_of="2026-05-08")

        growth = result["annual_growth"]
        self.assertIsNone(growth["eps_yoy_pct"])
        self.assertEqual(growth["revenue_yoy_pct"], 10.0)
        self.assertEqual(growth["periods"], ["2023", "2024"])

    def test_a_missing_year_between_two_filed_ones_is_not_a_year_over_year(self) -> None:
        annual = [
            {"period": "2022", "end": "2022-12-31", "eps": 1.0, "revenue": 100.0},
            {"period": "2024", "end": "2024-12-31", "eps": 2.0, "revenue": 200.0},
        ]
        result = evaluate_fundamentals(evidence([], annual), as_of="2026-05-08")

        self.assertIsNone(result["annual_growth"]["eps_yoy_pct"])
        self.assertIsNone(result["annual_growth"]["revenue_yoy_pct"])


class ACompoundRateSpansTheYearsItClaims(unittest.TestCase):
    def test_the_span_is_counted_in_years_not_in_rows(self) -> None:
        # Four rows spanning 2020 to 2025. Reading three rows back lands on 2020 and compounds a
        # five-year span as a three-year rate; the year three back is 2022.
        annual = [{"period": p, "end": f"{p}-12-31", "eps": v, "revenue": 100.0} for p, v in [("2020", 1.0), ("2022", 2.0), ("2024", 4.0), ("2025", 8.0)]]
        result = evaluate_fundamentals(evidence([], annual), as_of="2026-05-08")

        self.assertEqual(result["growth"]["acceleration_vs_historical_growth_rate"]["trailing_3yr_eps_cagr_pct"], 58.7401051968)

    def test_a_year_missing_at_the_far_end_leaves_the_rate_unread(self) -> None:
        annual = [{"period": p, "end": f"{p}-12-31", "eps": v, "revenue": 100.0} for p, v in [("2020", 1.0), ("2021", 2.0), ("2024", 4.0), ("2025", 8.0)]]
        result = evaluate_fundamentals(evidence([], annual), as_of="2026-05-08")

        self.assertIsNone(result["growth"]["acceleration_vs_historical_growth_rate"]["trailing_3yr_eps_cagr_pct"])

    def test_the_rate_is_read_from_the_year_exactly_three_back(self) -> None:
        annual = [{"period": p, "end": f"{p}-12-31", "eps": v, "revenue": 100.0} for p, v in [("2021", 9.0), ("2022", 1.0), ("2023", 1.1), ("2024", 1.21), ("2025", 1.331)]]
        result = evaluate_fundamentals(evidence([], annual), as_of="2026-05-08")

        self.assertEqual(result["growth"]["acceleration_vs_historical_growth_rate"]["trailing_3yr_eps_cagr_pct"], 10.0)

    def test_a_loss_in_the_ending_year_does_not_raise(self) -> None:
        annual = [{"period": p, "end": f"{p}-12-31", "eps": v, "revenue": 100.0} for p, v in [("2022", 1.0), ("2023", 1.0), ("2024", 1.0), ("2025", -1.0)]]
        result = evaluate_fundamentals(evidence([], annual), as_of="2026-05-08")

        reading = result["growth"]["acceleration_vs_historical_growth_rate"]
        self.assertIsNone(reading["trailing_3yr_eps_cagr_pct"])
        self.assertEqual(reading["reason"], "compound_rate_requires_positive_endpoints")


class GrowthFromALossIsNotGrowth(unittest.TestCase):
    def test_a_loss_that_doubled_is_not_a_hundred_percent_increase(self) -> None:
        quarters = [quarter(f"2024-Q{n}", -1.0, net_income=-10.0) for n in range(1, 5)]
        quarters += [quarter(f"2025-Q{n}", -2.0, net_income=-20.0) for n in range(1, 5)]
        annual = [{"period": "2024", "end": "2024-12-31", "eps": 1.0, "revenue": 100.0}, {"period": "2025", "end": "2025-12-31", "eps": 1.2, "revenue": 120.0}]
        result = evaluate_fundamentals(evidence(quarters, annual), as_of="2026-05-08")

        self.assertEqual(result["quarterly"]["eps_yoy_growth"], [])
        self.assertEqual(result["growth"]["minimum_quarterly_earnings_growth"]["state"], "unavailable")
        self.assertNotEqual(result["fundamentals_state"], "supports_convergence")


class TheTrailingYearEndsAtTheLatestQuarter(unittest.TestCase):
    def test_a_stale_four_quarter_window_is_not_the_current_trailing_year(self) -> None:
        quarters = [quarter(f"2024-Q{n}", 1.0) for n in range(1, 5)] + [quarter("2025-Q2", 9.0)]
        result = evaluate_fundamentals(evidence(quarters, []), as_of="2026-05-08", last_close=100.0)

        reading = result["valuation"]["price_earnings_ratio"]
        self.assertIsNone(reading["trailing_12m_eps"])
        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["missing_inputs"], ["filed_quarters_for_a_complete_trailing_year"])


class Code33CountsConsecutiveQuarters(unittest.TestCase):
    @staticmethod
    def accelerating(skip: frozenset[str] = frozenset()) -> list[dict]:
        """Three years where every quarter's growth rate beats the quarter before, on all three.

        Rates, not levels: linear growth in the levels makes the year-over-year rates fall, which
        is a deceleration and the opposite of what Code 33 asks for.
        """

        rows = []
        eps = {f"2023-Q{n}": 1.00 for n in range(1, 5)}
        revenue = {f"2023-Q{n}": 100.0 for n in range(1, 5)}
        rows += [quarter(f"2023-Q{n}", 1.00, 100.0, 10.0) for n in range(1, 5)]
        for offset, year in enumerate(("2024", "2025"), start=1):
            for n in range(1, 5):
                step = (offset - 1) * 4 + n
                period, before = f"{year}-Q{n}", f"{int(year) - 1}-Q{n}"
                eps[period] = eps[before] * (1 + (10 + 10 * step) / 100)
                revenue[period] = revenue[before] * (1 + (2 + step) / 100)
                if period in skip:
                    continue
                margin = 10.0 + step
                rows.append(quarter(period, round(eps[period], 6), round(revenue[period], 6), round(revenue[period] * margin / 100, 6)))
        return rows

    def test_every_quarter_accelerating_is_the_code(self) -> None:
        result = evaluate_fundamentals(evidence(self.accelerating(), []), as_of="2026-05-08")

        self.assertEqual(result["growth"]["code_33_triple_acceleration"]["gate"]["state"], "pass")

    def test_a_missing_quarter_breaks_the_run(self) -> None:
        # The same history with 2025-Q2 never filed. Three surviving records on either side of
        # a gap are not three consecutive quarters.
        result = evaluate_fundamentals(evidence(self.accelerating({"2025-Q2"}), []), as_of="2026-05-08")

        code = result["growth"]["code_33_triple_acceleration"]
        self.assertLess(code["consecutive_quarters"], 3)
        self.assertEqual(code["gate"]["state"], "fail")

    def test_a_latest_quarter_missing_a_cylinder_is_unavailable_rather_than_a_pass(self) -> None:
        rows = [quarter(f"2024-Q{n}", 1.00) for n in range(1, 5)]
        rows += [quarter("2025-Q1", 1.10, 105.0, 11.0), quarter("2025-Q2", 1.20, 110.0, 13.2), quarter("2025-Q3", 1.30, 115.0, 16.1)]
        # The latest filed quarter has earnings but no sales, so one cylinder cannot be judged.
        rows.append({"period": "2025-Q4", "end": "2025-12-31", "eps": 1.40, "net_income": 19.8, "diluted_shares": 100.0})
        result = evaluate_fundamentals(evidence(rows, []), as_of="2026-05-08")

        code = result["growth"]["code_33_triple_acceleration"]
        self.assertEqual(code["state"], "unavailable")
        self.assertEqual(code["reason"], "latest_filed_quarter_cannot_be_judged")


class TheBestStretchReportsItsOwnYears(unittest.TestCase):
    def test_the_share_change_covers_the_winning_window_not_the_latest_one(self) -> None:
        values = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 32.0, 32.0]
        shares = [100.0] * 6 + [50.0, 50.0]
        annual = [{"period": str(2018 + n), "end": f"{2018 + n}-12-31", "eps": values[n], "revenue": 100.0, "net_income": values[n] * 100, "diluted_shares": shares[n]} for n in range(8)]
        pace = evaluate_fundamentals(evidence([], annual), as_of="2026-05-08", leader_category="market_leader")["category_reading"]["readings"]["market_leader_earnings_growth_pace"]

        self.assertEqual(pace["best_stretch_periods"], ["2018", "2023"])
        self.assertEqual(pace["best_stretch_diluted_shares_change_pct"], 0.0)


class TheRollingAverageAndTheRunReadAdjacentQuarters(unittest.TestCase):
    def test_two_quarters_with_one_missing_between_them_are_not_a_rolling_pair(self) -> None:
        quarters = [quarter("2024-Q1", 1.00), quarter("2024-Q3", 1.00), quarter("2025-Q1", 1.10), quarter("2025-Q3", 1.30)]
        result = evaluate_fundamentals(evidence(quarters, []), as_of="2026-05-08")

        self.assertIsNone(result["growth"]["two_quarter_rolling_average"]["eps_yoy_pct"])
        # 2025-Q2 is not on file, so nothing on file is the quarter before 2025-Q3 -- which is
        # a history too short to answer, not a run that came out at zero.
        run = result["growth"]["practitioner_readings"]["minervini_sequential_acceleration"]
        self.assertIsNone(run["consecutive_accelerating_quarters"])
        self.assertEqual(run["state"], "unavailable")

    def test_the_band_window_names_only_the_quarters_it_actually_held(self) -> None:
        quarters = [quarter("2024-Q1", 1.00), quarter("2024-Q3", 1.00), quarter("2025-Q1", 1.10), quarter("2025-Q3", 1.30)]
        result = evaluate_fundamentals(evidence(quarters, []), as_of="2026-05-08")

        window = result["growth"]["minimum_quarterly_earnings_growth"]["window"]
        self.assertEqual([point["period"] for point in window], ["2025-Q3"])


if __name__ == "__main__":
    unittest.main()
