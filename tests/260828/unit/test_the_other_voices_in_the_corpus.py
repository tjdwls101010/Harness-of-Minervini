"""What the practitioners this harness reads for contrast say about the same numbers.

Three of them measure quarterly growth differently, and two of them say the price-earnings ratio
and return on equity are things they never look at. None of that can move a Minervini verdict --
the canonical layer is the default and the practice layer fills gaps, never overrides -- but a
reader deciding on a measurement should be able to see who else in the corpus disagrees, and in
their own words rather than in a paraphrase attributed to them.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float) -> dict:
    return {"period": period, "end": end, "eps": eps, "revenue": 100.0, "net_income": eps * 10, "diluted_shares": 100.0}


def evidence(quarters: list[dict]) -> dict:
    return {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": "10-K", "accounting_basis": "US-GAAP", "quarterly": quarters, "annual": []}]}


def two_years(recent: list[float]) -> list[dict]:
    rows = [quarter(f"2024-Q{n + 1}", f"2024-{(n + 1) * 3:02d}-30", 1.00) for n in range(4)]
    return rows + [quarter(f"2025-Q{n + 1}", f"2025-{(n + 1) * 3:02d}-30", recent[n]) for n in range(4)]


def contrast(recent: list[float]) -> dict:
    return evaluate_fundamentals(evidence(two_years(recent)), as_of="2026-05-08")["growth"]["practitioner_readings"]


class ThreeWaysToReadTheSameQuarter(unittest.TestCase):
    def test_zangers_range_is_measured_and_marked_as_his_and_not_the_default(self) -> None:
        reading = contrast([1.10, 1.20, 1.30, 1.35])["zanger_quarterly_growth_target"]

        self.assertEqual(reading["attributed_to"], "Zanger")
        self.assertIs(reading["binds"], False)
        self.assertEqual(reading["band"]["measured"], 35.0)
        self.assertEqual(reading["band"]["source_range"], [30, 40])
        self.assertEqual(reading["band"]["state"], "within_source_range")

    def test_the_sequential_run_is_counted_over_the_quarters_the_source_inspects(self) -> None:
        reading = contrast([1.10, 1.20, 1.30, 1.35])["minervini_sequential_acceleration"]

        # Growth of 10, 20, 30 then 35: each higher than the last, so three of the four
        # inspected quarters accelerated on the one before them.
        self.assertEqual(reading["lookback_quarters"], [1, 4])
        self.assertEqual(reading["consecutive_accelerating_quarters"], 3)
        self.assertIs(reading["binds"], True)
        self.assertNotIn("gate", reading)

    def test_a_run_that_broke_last_quarter_counts_zero(self) -> None:
        # Growth of 10, 20, 30 then 25: the run is sequential up to the quarter it stopped
        # being, and the source is looking at the most recent quarters, not the best ones.
        reading = contrast([1.10, 1.20, 1.30, 1.25])["minervini_sequential_acceleration"]

        self.assertEqual(reading["consecutive_accelerating_quarters"], 0)

    def test_ritchie_declines_to_measure_it_and_says_so_in_his_own_words(self) -> None:
        reading = contrast([1.10, 1.20, 1.30, 1.35])["ritchie_explosive_growth_only"]

        self.assertEqual(reading["computability"], "judgment_only")
        self.assertIn("mechanical", reading["quotation"])
        self.assertNotIn("band", reading)


class WhoElseLooksAtTheMultipleAndTheReturn(unittest.TestCase):
    def test_the_multiple_carries_the_two_views_the_corpus_records(self) -> None:
        views = evaluate_fundamentals(evidence(two_years([1.10, 1.20, 1.30, 1.35])), as_of="2026-05-08", last_close=70.0)["valuation"]["practitioner_views"]

        self.assertEqual([view["attributed_to"] for view in views], ["Minervini", "Ritchie II"])
        self.assertIn("rarely concern myself", views[0]["quotation"])

    def test_the_return_on_equity_carries_the_voice_that_agrees_without_a_number(self) -> None:
        views = evaluate_fundamentals(evidence(two_years([1.10, 1.20, 1.30, 1.35])), as_of="2026-05-08")["profitability"]["practitioner_views"]

        self.assertEqual([view["attributed_to"] for view in views], ["Ryan"])
        self.assertIs(views[0]["binds"], False)


if __name__ == "__main__":
    unittest.main()
