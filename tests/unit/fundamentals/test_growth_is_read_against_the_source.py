"""Growth measured against the ranges the source actually named.

Every fundamentals claim in the registry carries `failure: needs_review` -- not one of them
decides a verdict by itself, because this source treats fundamentals as convergence evidence
and keeps its hard gates for the trend template and for risk. And the growth numbers are
bands, not gates: "many successful growth managers require a minimum of 20 to 25 percent"
is a range, so a reading reports where it sat and which edge is the good one.

What was here before decided `contradicts` when growth fell fifteen points from its own
recent peak, and called any positive margin change `supports`. Neither number is in either
corpus.
"""

from __future__ import annotations

from tests.filings import evidence as shared_evidence, quarter as shared_quarter

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float, revenue: float, net_income: float) -> dict:
    return shared_quarter(period, end, eps, revenue=revenue, net_income=net_income)


def evidence(quarters: list[dict], annual: list[dict] | None = None) -> dict:
    return shared_evidence(quarters=quarters, years=annual or [])


# Year-ago quarters, then this year's, so every point has something to grow from.
def year_pair(this_year_eps: list[float], *, revenue: list[float] | None = None, net_income: list[float] | None = None) -> list[dict]:
    base_eps = [1.00, 1.00, 1.00, 1.00]
    sales = revenue or [100.0, 100.0, 100.0, 100.0]
    income = net_income or [10.0, 10.0, 10.0, 10.0]
    rows = [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", base_eps[n], 100.0, 10.0) for n in range(4)]
    rows += [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", this_year_eps[n], sales[n], income[n]) for n in range(4)]
    return rows


class TheMinimumIsARangeAndTheReadingSaysWhereItSat(unittest.TestCase):
    def test_growth_above_the_range_is_reported_as_past_its_good_edge(self) -> None:
        result = evaluate_fundamentals(evidence(year_pair([1.10, 1.15, 1.20, 1.30])), as_of="2026-05-10")

        reading = result["growth"]["minimum_quarterly_earnings_growth"]
        self.assertEqual(reading["role"], "band")
        self.assertEqual(reading["measured"], 30.0)
        self.assertEqual(reading["source_range"], [20, 25])
        self.assertEqual(reading["direction"], "higher_is_better")
        self.assertEqual(reading["state"], "above_source_range")

    def test_growth_short_of_the_range_is_reported_as_short_of_it(self) -> None:
        result = evaluate_fundamentals(evidence(year_pair([1.05, 1.06, 1.08, 1.10])), as_of="2026-05-10")

        reading = result["growth"]["minimum_quarterly_earnings_growth"]
        self.assertEqual(reading["measured"], 10.0)
        self.assertEqual(reading["state"], "below_source_range")

    def test_growth_inside_the_range_is_neither_a_pass_nor_a_failure(self) -> None:
        result = evaluate_fundamentals(evidence(year_pair([1.10, 1.15, 1.20, 1.22])), as_of="2026-05-10")

        reading = result["growth"]["minimum_quarterly_earnings_growth"]
        self.assertEqual(reading["measured"], 22.0)
        self.assertEqual(reading["state"], "within_source_range")


class TheHigherBarsAreContextBesideTheMinimum(unittest.TestCase):
    def test_superperformance_is_reported_without_deciding_anything(self) -> None:
        result = evaluate_fundamentals(evidence(year_pair([1.10, 1.15, 1.20, 1.45])), as_of="2026-05-10")

        growth = result["growth"]
        self.assertEqual(growth["superperformance_quarterly_earnings_growth"]["measured"], 45.0)
        self.assertEqual(growth["superperformance_quarterly_earnings_growth"]["state"], "above_source_range")
        self.assertEqual(growth["minimum_quarterly_earnings_growth"]["state"], "above_source_range")

    def test_the_bull_market_bar_is_not_read_without_a_declared_regime(self) -> None:
        result = evaluate_fundamentals(evidence(year_pair([1.10, 1.15, 1.20, 1.45])), as_of="2026-05-10")

        reading = result["growth"]["bull_market_quarterly_earnings_growth"]
        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["missing_inputs"], ["market_regime_classification"])

    def test_a_declared_regime_lets_the_bull_market_bar_be_read(self) -> None:
        result = evaluate_fundamentals(evidence(year_pair([1.10, 1.15, 1.20, 1.45])), as_of="2026-05-10", market_regime="bull")

        reading = result["growth"]["bull_market_quarterly_earnings_growth"]
        self.assertEqual(reading["measured"], 45.0)
        self.assertEqual(reading["source_range"], [40, 100])
        self.assertEqual(reading["state"], "within_source_range")


class DecelerationIsReportedAgainstAnExampleAndNeverAsALimit(unittest.TestCase):
    def test_the_source_gave_an_illustration_so_the_reading_gives_distances(self) -> None:
        # 60% then 25% is the shape the source described. Its numbers are references, not a
        # limit, so what is published is the two rates and nothing that reads as a verdict.
        rows = year_pair([1.60, 1.50, 1.40, 1.25])
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        reading = result["growth"]["earnings_deceleration"]
        self.assertEqual(reading["latest_yoy_pct"], 25.0)
        self.assertEqual(reading["previous_yoy_pct"], 40.0)
        self.assertEqual(reading["decelerated"], True)
        self.assertNotIn("state", reading)
        self.assertNotIn("gates", reading)


class TheTwoQuarterAverageTravelsBesideTheRawRate(unittest.TestCase):
    def test_a_lumpy_pair_is_smoothed_the_way_the_tactic_says(self) -> None:
        rows = year_pair([1.10, 1.15, 1.60, 1.10])
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        smoothing = result["growth"]["two_quarter_rolling_average"]
        self.assertEqual(smoothing["window_quarters"], 2)
        self.assertEqual(smoothing["eps_yoy_pct"], 35.0)
        # Canonical, so it binds -- which says whose standard it is, not that it decides.
        self.assertEqual(smoothing["binds"], True)


if __name__ == "__main__":
    unittest.main()


class TheStateIsWhereTheMeasurementsSat(unittest.TestCase):
    """One question, one answer: the verdict word comes from the readings beside it.

    The block used to answer it twice -- once in a `quality` component built from invented
    slowdown thresholds, once in the readings a reader can see -- and the two could disagree.
    """

    def annual(self) -> list[dict]:
        return [{"period": "2023", "eps": 1.60, "revenue": 340.0}, {"period": "2024", "eps": 2.30, "revenue": 400.0}, {"period": "2025", "eps": 3.70, "revenue": 480.0}]

    def test_growth_past_the_minimum_range_supports_convergence(self) -> None:
        result = evaluate_fundamentals(evidence(year_pair([1.10, 1.15, 1.20, 1.30]), self.annual()), as_of="2026-05-10")

        self.assertEqual(result["fundamentals_state"], "supports_convergence")
        self.assertEqual(result["quality"]["minimum_growth_state"], "above_source_range")

    def test_growth_short_of_the_minimum_range_does_not(self) -> None:
        result = evaluate_fundamentals(evidence(year_pair([1.05, 1.06, 1.08, 1.10]), self.annual()), as_of="2026-05-10")

        self.assertEqual(result["fundamentals_state"], "does_not_support_convergence")
        self.assertEqual(result["quality"]["minimum_growth_state"], "below_source_range")

    def test_growth_inside_the_minimum_range_supports_it(self) -> None:
        # Inside the range the source called a minimum is at the minimum, which is what the
        # source says a growth manager accepts.
        result = evaluate_fundamentals(evidence(year_pair([1.10, 1.15, 1.20, 1.22]), self.annual()), as_of="2026-05-10")

        self.assertEqual(result["fundamentals_state"], "supports_convergence")

    def test_no_year_over_year_pair_is_incomplete_rather_than_a_failure(self) -> None:
        only_this_year = [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", 1.10, 100.0, 10.0) for n in range(4)]
        result = evaluate_fundamentals(evidence(only_this_year, self.annual()), as_of="2026-05-10")

        self.assertEqual(result["fundamentals_state"], "incomplete")
        self.assertIn("quarterly_eps_yoy_growth", result["missing"])

    def test_the_state_and_the_reading_beside_it_can_never_disagree(self) -> None:
        for latest, expected in ((1.30, "supports_convergence"), (1.10, "does_not_support_convergence")):
            with self.subTest(latest=latest):
                result = evaluate_fundamentals(evidence(year_pair([1.10, 1.15, 1.20, latest]), self.annual()), as_of="2026-05-10")
                reading = result["growth"]["minimum_quarterly_earnings_growth"]

                self.assertEqual(result["quality"]["minimum_growth_state"], reading["state"])
                self.assertEqual(result["fundamentals_state"], expected)


class NothingInTheBlockCarriesANumberNoSourceGave(unittest.TestCase):
    """The margin trend and the annual reading, which both had limits of their own.

    A margin one hundredth of a point higher than last quarter was `supports`; an annual EPS
    rise of twenty percent was too, borrowed from a quarterly band the source stated about
    quarters. Both are reported now, and neither states a verdict the corpus does not.
    """

    def test_a_hairline_margin_rise_is_a_change_and_not_an_endorsement(self) -> None:
        rows = year_pair([1.30, 1.30, 1.30, 1.30], net_income=[10.0, 10.0, 10.0, 10.01])
        result = evaluate_fundamentals(evidence(rows), as_of="2026-05-10")

        margin = result["growth"]["margin_trend"]
        self.assertEqual(margin["latest_change_pct_points"], 0.01)
        self.assertNotIn("state", margin)

    def test_the_annual_reading_reports_growth_without_a_borrowed_limit(self) -> None:
        annual = [{"period": "2024", "eps": 2.00, "revenue": 400.0}, {"period": "2025", "eps": 2.20, "revenue": 420.0}]
        result = evaluate_fundamentals(evidence(year_pair([1.30, 1.30, 1.30, 1.30]), annual), as_of="2026-05-10")

        reading = result["annual_growth"]
        self.assertEqual(reading["eps_yoy_pct"], 10.0)
        self.assertEqual(reading["doctrine_id"], "fundamentals.annual_earnings_requirement")
        self.assertNotIn("state", reading)
        # Judgment-only in the registry: quarterly strength has to translate into annual
        # results, and the source puts no number on "strong".
        self.assertEqual(reading["computability"], "judgment_only")
