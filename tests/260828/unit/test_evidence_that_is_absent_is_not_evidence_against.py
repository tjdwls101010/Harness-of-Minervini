"""Three blocks that answered a question nobody had the evidence to ask.

The distinction the constitution draws is between a known failure and missing evidence, and
these three collapsed it in three different ways. A latest filed quarter with no earnings
figure dropped out of the series, so an older quarter became the headline and its growth was
published as the company's current growth. A turnaround criterion whose second branch could
not be measured reported the whole disjunction false. And two acceleration blocks with no
comparable pair on file reported a count of zero and an answer of no.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float | None, *, revenue: float = 100.0) -> dict:
    fact = {"period": period, "end": end, "revenue": revenue, "net_income": 10.0, "diluted_shares": 100.0}
    return fact if eps is None else {**fact, "eps": eps}


def evidence(quarters: list[dict], years: list[dict] | None = None) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": quarters, "annual": years or []}]}


def read(quarters: list[dict], **declared) -> dict:
    return evaluate_fundamentals(evidence(quarters), as_of="2026-05-08", **declared)


class TheLatestFiledQuarterIsTheHeadlineOrThereIsNone(unittest.TestCase):
    """A quarter that was filed without the figure is not a quarter that was never filed.

    Dropping it let the quarter before it become "the most recent", so a company whose latest
    report carried no earnings line had the previous quarter's growth published as its current
    growth -- and that reading is the one the convergence conjunction reads.
    """

    @staticmethod
    def latest_without_earnings() -> list[dict]:
        rows = [quarter(f"{year}-Q{n + 1}", f"{year}-{(n + 1) * 3:02d}-30", 0.20 * (2 if year == 2025 else 1)) for year in (2024, 2025) for n in range(4)]
        return rows + [quarter("2026-Q1", "2026-03-31", None)]

    def test_the_band_does_not_fall_back_to_an_older_quarter(self) -> None:
        result = read(self.latest_without_earnings())

        minimum = result["growth"]["minimum_quarterly_earnings_growth"]
        self.assertEqual(minimum["state"], "unavailable")
        self.assertEqual(minimum["reason"], "latest_filed_quarter_has_no_year_over_year_pair")

    def test_convergence_is_not_reached_on_a_stale_quarter(self) -> None:
        result = read(self.latest_without_earnings())

        self.assertEqual(result["quality"]["state"], "unavailable")
        self.assertEqual(result["fundamentals_state"], "incomplete")


class AnUnknownBranchDoesNotMakeADisjunctionFalse(unittest.TestCase):
    def test_a_failed_gate_beside_an_unmeasured_peak_is_not_a_refusal(self) -> None:
        quarters = [quarter("2024-Q1", "2024-03-31", 1.0), quarter("2025-Q1", "2025-03-31", 3.0)]
        reading = read(quarters, leader_category="turnaround")["category_reading"]["readings"]["turnaround_qualifying_criteria"]

        self.assertEqual(reading["gate"]["state"], "fail")
        self.assertIsNone(reading["trailing_12m_eps_at_or_above_prior_peak"])
        self.assertIsNone(reading["satisfied"])


class NoComparablePairIsNotAnAnswerOfNo(unittest.TestCase):
    @staticmethod
    def one_pair_a_year_apart() -> list[dict]:
        return [quarter("2024-Q1", "2024-03-31", 1.0), quarter("2025-Q1", "2025-03-31", 3.0)]

    def test_the_sequential_run_is_unknown_rather_than_zero(self) -> None:
        reading = read(self.one_pair_a_year_apart())["growth"]["practitioner_readings"]["minervini_sequential_acceleration"]

        self.assertIsNone(reading["consecutive_accelerating_quarters"])
        self.assertEqual(reading["state"], "unavailable")

    def test_the_history_lookback_answers_unknown_rather_than_no(self) -> None:
        reading = read(self.one_pair_a_year_apart())["growth"]["earnings_history_lookback"]

        self.assertIsNone(reading["some_form_of_acceleration"])
        self.assertEqual(reading["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
