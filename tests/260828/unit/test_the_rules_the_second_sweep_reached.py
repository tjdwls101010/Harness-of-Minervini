"""Nine more rules a mutation sweep changed without any test noticing.

The first sweep over this phase found four. Widening it to the guards the second review round
added found nine more of the same kind: a rule with a reason written beside it in the code and
nothing anywhere asserting it. One survivor was left without a test on purpose -- the trailing
year's window bounds are subsumed by the completeness check that runs beside them, confirmed
identical over four hundred randomly generated filing sets -- and its reasoning is recorded in
the plan rather than pinned by a test that could only restate the code.
"""

from __future__ import annotations

from tests.filings import annual, filing

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals
from scripts.minervini.providers.sec import normalize_filed_facts


_ENDS = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def quarter(year: int, index: int, eps: float | None, revenue: float = 100.0) -> dict:
    fact = {"period": f"{year}-Q{index}", "end": f"{year}-{_ENDS[index]}", "revenue": revenue, "diluted_shares": 100.0}
    if eps is not None:
        fact["eps"] = eps
        fact["net_income"] = eps * 100
    return fact


def read(filings: list[dict], **declared) -> dict:
    return evaluate_fundamentals({"source": "sec_filed_facts", "filings": filings}, as_of="2026-05-08", **declared)


class AStretchThatTiesIsReportedAtItsShortest(unittest.TestCase):
    """A company that grew at one rate for a decade ties with itself at every span.

    Every window from five years to nine reaches the same compound rate, so the band reads the
    same whichever wins. What differs is the span and the periods published beside it, and an
    arbitrary winner there is a field the reader cannot account for. The tie goes to the fewest
    years the rate actually held, which is the smallest claim the filings support.
    """

    def test_a_decade_at_one_rate_reports_the_five_year_stretch(self) -> None:
        years = [annual(year, round(1.4 ** (year - 2016), 10)) for year in range(2016, 2026)]
        reading = read([filing(years=years)], leader_category="market_leader")["category_reading"]["readings"]["market_leader_earnings_growth_pace"]

        self.assertEqual(reading["best_stretch"]["measured"], 40.0)
        self.assertEqual(reading["best_stretch_span_years"], 5)
        self.assertEqual(reading["best_stretch_periods"], ["2016", "2021"])


class TheEvaluatorRefusesABreakoutItsAsOfCannotSee(unittest.TestCase):
    """A breakout after `as_of` is a request error, not a reading with a gap in it.

    The capability refuses it before the evaluator is called, so this guard is the second
    reader of the same question -- and the two have to agree. Letting a future date through
    computes the multiple at a session the point-in-time answer has not reached.
    """

    def test_a_breakout_date_past_as_of_raises(self) -> None:
        years = [annual(year, round(1.4 ** (year - 2016), 10)) for year in range(2016, 2026)]

        with self.assertRaises(ValueError):
            read([filing(years=years)], last_close=100.0, breakout_close=50.0, breakout_date="2026-06-01")


class ReturnOnEquityIsTheLatestYearThatHasBoth(unittest.TestCase):
    """The reading is what the equity earned, and "what" means most recently.

    Both years on file carry earnings and equity, so nothing refuses either one. Reading the
    earliest publishes a rate the company left behind years ago under the same field name and
    the same band, with only `period` saying which year it was.
    """

    def test_the_older_year_is_not_the_one_reported(self) -> None:
        years = [annual(2024, 1.0, net_income=100.0, stockholders_equity=1000.0), annual(2025, 1.2, net_income=200.0, stockholders_equity=1000.0)]
        reading = read([filing(years=years)])["profitability"]["return_on_equity"]

        self.assertEqual(reading["period"], "2025")
        self.assertEqual(reading["roe_pct"], 20.0)


class TheRunStopsWhereTheSourceStoppedLooking(unittest.TestCase):
    """"The most recent one to four quarters" is where he looked, so four is where counting ends.

    A fifth accelerating quarter is not adverse -- it is simply past the window the claim
    describes. Reporting five under a claim whose own quotation says four makes the number
    disagree with the sentence printed beside it.
    """

    def test_five_accelerating_quarters_are_reported_as_four(self) -> None:
        quarters = [quarter(2024, index, 0.10) for index in (1, 2, 3, 4)]
        quarters += [quarter(2025, index, eps) for index, eps in zip((1, 2, 3, 4), (0.11, 0.13, 0.16, 0.20))]
        quarters += [quarter(2026, index, eps) for index, eps in zip((1, 2), (0.30, 0.50))]
        reading = read([filing(quarterly=quarters)])["growth"]["practitioner_readings"]["minervini_sequential_acceleration"]

        self.assertEqual([point["yoy_pct"] for point in read([filing(quarterly=quarters)])["quarterly"]["eps_yoy_growth"]][-5:], [30.0, 60.0, 100.0, 172.7272727273, 284.6153846154])
        self.assertEqual(reading["state"], "reported")
        self.assertEqual(reading["consecutive_accelerating_quarters"], 4)


class AQuarterThatMatchedTheOneBeforeDidNotAccelerate(unittest.TestCase):
    """Accelerating is faster than the quarter before, and the same speed is not faster.

    A hundred percent following a hundred percent is a company holding its pace. Counting it as
    a run of one turns "sequentially accelerating" into "not decelerating", which is a different
    claim and a weaker one.
    """

    def test_a_repeated_growth_rate_leaves_the_run_at_zero(self) -> None:
        quarters = [quarter(2024, index, 0.10) for index in (1, 2, 3, 4)]
        quarters += [quarter(2025, index, eps) for index, eps in zip((1, 2, 3, 4), (0.11, 0.13, 0.16, 0.20))]
        quarters += [quarter(2026, 1, 0.22)]
        reading = read([filing(quarterly=quarters)])["growth"]["practitioner_readings"]["minervini_sequential_acceleration"]

        self.assertEqual([point["yoy_pct"] for point in read([filing(quarterly=quarters)])["quarterly"]["eps_yoy_growth"]][-2:], [100.0, 100.0])
        self.assertEqual(reading["consecutive_accelerating_quarters"], 0)


class EarningsWithoutSalesNeedsBothFromOneQuarter(unittest.TestCase):
    """The claim is about one quarter's earnings outrunning that same quarter's sales.

    The latest quarter was filed without revenue, so the sales series ends a quarter earlier.
    Pairing the two ends publishes a quarter's earnings growth against a different quarter's
    sales decline and calls the combination cost-cutting.
    """

    def test_a_latest_quarter_without_revenue_leaves_the_pattern_unread(self) -> None:
        quarters = [quarter(2024, index, 0.10, revenue=100.0) for index in (1, 2, 3, 4)]
        quarters += [quarter(2025, index, 0.20, revenue=90.0) for index in (1, 2, 3)]
        quarters += [quarter(2025, 4, 0.25, revenue=None)]
        payload = read([filing(quarterly=quarters)])

        self.assertEqual([point["period"] for point in payload["quarterly"]["eps_yoy_growth"]][-1], "2025-Q4")
        self.assertEqual([point["period"] for point in payload["quarterly"]["revenue_yoy_growth"]][-1], "2025-Q3")
        reading = payload["growth"]["earnings_without_sales_growth"]
        self.assertEqual(reading["reason"], "matching_latest_earnings_and_sales_growth_required")
        self.assertIsNone(reading["earnings_grew_without_sales"])


class TheLookbackIsTheYearsTheSourceLookedBack(unittest.TestCase):
    """One to two years is a range, and the lookback reads to its far edge.

    The acceleration in this history sits in the second year back. Reading only the near edge
    examines four quarters instead of eight and answers "no acceleration" for a company that
    accelerated inside the window the source named.
    """

    def test_acceleration_in_the_second_year_back_is_still_inside_the_window(self) -> None:
        quarters = [quarter(2023, index, 0.10, revenue=100.0) for index in (1, 2, 3, 4)]
        quarters += [quarter(2024, index, eps, revenue=revenue) for index, eps, revenue in zip((1, 2, 3, 4), (0.11, 0.13, 0.16, 0.20), (101.0, 104.0, 109.0, 116.0))]
        quarters += [quarter(2025, index, eps, revenue=revenue) for index, eps, revenue in zip((1, 2, 3, 4), (0.22, 0.25, 0.28, 0.31), (121.0, 123.0, 124.0, 124.5))]
        reading = read([filing(quarterly=quarters)])["growth"]["earnings_history_lookback"]

        self.assertEqual(len(reading["periods_examined"]), 8)
        self.assertEqual(reading["periods_examined"][0], "2024-Q1")
        self.assertEqual(reading["quarters_accelerating_in_both"], ["2024-Q2", "2024-Q3", "2024-Q4"])
        self.assertIs(reading["some_form_of_acceleration"], True)


class OneQuarterlyFilingMeansTheRegistrantFilesQuarters(unittest.TestCase):
    """"This registrant does not file quarters" is a claim about the registrant, not one filing.

    A 20-F beside a 10-Q says the quarters exist and this fetch did not reach them, which is a
    gap worth re-running. Saying they are not filed at all closes a question the filings
    themselves answer the other way.
    """

    def test_a_twenty_f_beside_a_ten_q_leaves_the_quarterly_gaps_standing(self) -> None:
        missing = read([filing("20-F"), filing("10-Q")])["missing"]

        self.assertIn("quarterly_eps", missing)
        self.assertNotIn("quarterly_facts_not_filed_by_this_registrant", missing)

    def test_a_registrant_filing_only_annual_reports_says_so_once(self) -> None:
        missing = read([filing("20-F"), filing("20-F/A")])["missing"]

        self.assertIn("quarterly_facts_not_filed_by_this_registrant", missing)
        self.assertNotIn("quarterly_eps", missing)


class AFactIsReadUnderTheFormItsSubmissionDeclares(unittest.TestCase):
    """The fact's own `form` and the submission index have to name the same document.

    They disagree when a fact is tagged under one form and filed under an accession the index
    records as another, and the two together are the only thing that places the fact in time.
    Taking the accession alone puts a figure inside a filing that does not contain it.
    """

    @staticmethod
    def normalized(fact_form: str) -> dict:
        rows = [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 4.0, "accn": "0000042-26-000001", "filed": "2026-02-20", "form": "10-K", "fy": 2025, "fp": "FY"},
            {"start": "2026-01-01", "end": "2026-03-31", "val": 1.1, "accn": "0000042-26-000002", "filed": "2026-05-01", "form": fact_form, "fy": 2026, "fp": "Q1"},
        ]
        company_facts = {"cik": 42, "entityName": "Form Mismatch, Inc.", "facts": {"us-gaap": {"EarningsPerShareDiluted": {"label": "EPS diluted", "units": {"USD/shares": rows}}}}}
        submissions = {"cik": 42, "filings": {"recent": {
            "accessionNumber": ["0000042-26-000001", "0000042-26-000002"],
            "filingDate": ["2026-02-20", "2026-05-01"],
            "reportDate": ["2025-12-31", "2026-03-31"],
            "form": ["10-K", "10-Q"],
        }}}
        return normalize_filed_facts(company_facts, submissions, as_of="2026-05-08")

    def test_a_fact_whose_form_matches_its_submission_is_kept(self) -> None:
        quarters = {fact["period"] for record in self.normalized("10-Q")["filings"] for fact in record["quarterly"]}

        self.assertEqual(quarters, {"2026-Q1"})

    def test_a_fact_tagged_under_another_form_is_left_out(self) -> None:
        quarters = {fact["period"] for record in self.normalized("10-K")["filings"] for fact in record["quarterly"]}

        self.assertEqual(quarters, set())


if __name__ == "__main__":
    unittest.main()
