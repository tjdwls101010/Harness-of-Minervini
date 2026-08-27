"""What the price paid per dollar of earnings says, which the source says is very little alone.

A price-earnings ratio needs a price, and this evaluator holds filings, so the price arrives
as a declared input. What is published beside the number is the source's own frame: by itself
the multiple ranks among the most useless statistics on Wall Street, and a low one is a reason
to look for the reason rather than a bargain.

The one thing the source does quantify is the expansion: a multiple that doubled or tripled
over twelve to twenty-four months of rising price is a late-stage signal. Two numbers, from two
dates, and both of them measured rather than assumed.
"""

from __future__ import annotations

import unittest

from scripts.minervini.fundamentals import evaluate_fundamentals


def quarter(period: str, end: str, eps: float, filed_at: str) -> dict:
    return {"period": period, "end": end, "eps": eps, "revenue": 100.0, "net_income": eps * 10, "diluted_shares": 100.0, "filed_at": filed_at}


FILINGS = [
    ("2024-04-25", [("2024-Q1", "2024-03-31", 0.25)]),
    ("2024-07-25", [("2024-Q2", "2024-06-30", 0.25)]),
    ("2024-10-25", [("2024-Q3", "2024-09-30", 0.25)]),
    ("2025-02-20", [("2024-Q4", "2024-12-31", 0.25)]),
    ("2025-04-25", [("2025-Q1", "2025-03-31", 0.50)]),
    ("2025-07-25", [("2025-Q2", "2025-06-30", 0.50)]),
    ("2025-10-24", [("2025-Q3", "2025-09-30", 0.50)]),
    ("2026-02-19", [("2025-Q4", "2025-12-31", 0.50)]),
]


def evidence() -> dict:
    filings = [
        {"filed_at": filed_at, "form": "10-Q", "accounting_basis": "US-GAAP", "annual": [],
         "quarterly": [{"period": period, "end": end, "eps": eps, "revenue": 100.0, "net_income": eps * 10, "diluted_shares": 100.0} for period, end, eps in rows]}
        for filed_at, rows in FILINGS
    ]
    return {"source": "sec_filed_facts", "filings": filings}


def valuation(**declared) -> dict:
    return evaluate_fundamentals(evidence(), as_of="2026-05-08", **declared)["valuation"]


class TheMultipleItself(unittest.TestCase):
    def test_without_a_price_there_is_no_ratio_and_the_input_is_named(self) -> None:
        reading = valuation()["price_earnings_ratio"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["missing_inputs"], ["last_close"])

    def test_the_ratio_is_the_close_over_the_trailing_year(self) -> None:
        # Four quarters at 0.50 make a trailing year of 2.00; a close of 70 is 35 times it.
        reading = valuation(last_close=70.0)["price_earnings_ratio"]

        self.assertEqual(reading["trailing_12m_eps"], 2.0)
        self.assertEqual(reading["pe_ratio"], 35.0)
        self.assertEqual(reading["state"], "reported")

    def test_the_source_says_the_number_decides_nothing_on_its_own(self) -> None:
        reading = valuation(last_close=70.0)["price_earnings_ratio"]

        self.assertIn("fundamentals.pe_useless_alone", reading["doctrine_ids"])
        self.assertNotIn("state_verdict", reading)

    def test_a_company_that_did_not_earn_has_no_meaningful_multiple(self) -> None:
        losing = {"source": "sec_filed_facts", "filings": [{"filed_at": "2026-02-19", "form": "10-K", "accounting_basis": "US-GAAP", "annual": [],
                  "quarterly": [{"period": f"2025-Q{n + 1}", "end": f"2025-{(n + 1) * 3:02d}-30", "eps": -0.25, "revenue": 100.0, "net_income": -25.0, "diluted_shares": 100.0} for n in range(4)]}]}
        reading = evaluate_fundamentals(losing, as_of="2026-05-08", last_close=70.0)["valuation"]["price_earnings_ratio"]

        self.assertEqual(reading["state"], "not_meaningful")
        self.assertEqual(reading["reason"], "trailing_12m_eps_not_positive")
        self.assertIsNone(reading["pe_ratio"])

    def test_the_low_multiple_warning_needs_peers_this_evaluator_does_not_hold(self) -> None:
        reading = valuation(last_close=70.0)["anti_low_pe_bargain_trap"]

        self.assertEqual(reading["state"], "not_evaluated")
        self.assertEqual(reading["missing_inputs"], ["peer_group_pe_ratios", "eps_growth_comparison"])


class HowFarTheMultipleExpanded(unittest.TestCase):
    def test_a_doubling_inside_the_window_sits_in_the_late_stage_range(self) -> None:
        # At the breakout the trailing year was 1.00 and the close 17.50, so seventeen and a
        # half times. Now it is 35 times: an expansion of 100 percent, a multiple of two.
        reading = valuation(last_close=70.0, breakout_close=17.50, breakout_date="2025-03-14")["pe_expansion"]

        self.assertEqual(reading["pe_ratio_at_breakout"], 17.5)
        self.assertEqual(reading["pe_ratio_current"], 35.0)
        self.assertEqual(reading["expansion"]["measured"], 100.0)
        self.assertEqual(reading["expansion"]["source_range"], [100, 200])
        self.assertEqual(reading["expansion"]["state"], "within_source_range")
        self.assertEqual(reading["multiple"]["measured"], 2.0)
        self.assertEqual(reading["elapsed"]["measured"], 13)

    def test_the_breakout_multiple_uses_only_what_had_been_filed_by_then(self) -> None:
        # 2025-Q1 was filed on 2025-04-25, six weeks after the breakout. Counting it would
        # credit the buyer with earnings nobody had published yet.
        reading = valuation(last_close=70.0, breakout_close=17.50, breakout_date="2025-03-14")["pe_expansion"]

        self.assertEqual(reading["trailing_12m_eps_at_breakout"], 1.0)
        self.assertEqual(reading["filings_available_at_breakout"], ["2024-04-25", "2024-07-25", "2024-10-25", "2025-02-20"])

    def test_without_a_breakout_the_expansion_names_what_it_needed(self) -> None:
        reading = valuation(last_close=70.0)["pe_expansion"]

        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["missing_inputs"], ["breakout_close", "breakout_date"])




class AMonthIsNotOverUntilItsDayArrives(unittest.TestCase):
    """Twelve to twenty-four months is a window of elapsed months, and a month that has not
    reached its own day has not elapsed. Counting the calendar difference alone put a stock
    inside the source's window nearly a month before it arrived there."""

    def test_a_partial_twelfth_month_is_eleven_completed_months(self) -> None:
        # 2025-03-31 to 2026-03-09: the twelfth month completes on the 31st, not the 9th.
        reading = evaluate_fundamentals(evidence(), as_of="2026-03-09", last_close=70.0, breakout_close=17.50, breakout_date="2025-03-31")["valuation"]["pe_expansion"]

        self.assertEqual(reading["elapsed"]["measured"], 11)
        self.assertEqual(reading["elapsed"]["state"], "below_source_range")

    def test_the_month_completes_on_its_own_day(self) -> None:
        reading = evaluate_fundamentals(evidence(), as_of="2026-03-31", last_close=70.0, breakout_close=17.50, breakout_date="2025-03-31")["valuation"]["pe_expansion"]

        self.assertEqual(reading["elapsed"]["measured"], 12)
        self.assertEqual(reading["elapsed"]["state"], "within_source_range")


if __name__ == "__main__":
    unittest.main()
