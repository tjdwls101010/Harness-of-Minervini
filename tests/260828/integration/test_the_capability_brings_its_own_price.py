"""The multiple needs a price, and the harness holds the bars -- so the capability fetches them.

Asking the caller for a close would let a number that disagrees with the completed bars decide
a reading. `ticker.fundamentals` reads the last completed session itself, and derives the
breakout-session close from the same history rather than taking one on trust.

A price provider with nothing to give does not stop the filings from reaching a verdict. The
multiple is not filed evidence, so its absence is reported where the multiple would have been.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta
from scripts.minervini.providers.sec import normalize_filed_facts

from .test_the_live_path_reaches_a_verdict import AS_OF, CIK, bars, company_facts, submissions


def run(price_history=None, **request) -> dict:
    normalized = normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
    filings = ProviderSnapshot(normalized, SnapshotMeta(provider="sec", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"filed_only": True}))
    prices = price_history or (lambda ticker, as_of: ProviderSnapshot(bars("2024-01-02", AS_OF, 100.0), SnapshotMeta(provider="yfinance", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})))
    runtime = Runtime(fundamentals_evidence=lambda ticker, as_of, cik: filings, price_history=prices)
    return execute("ticker.fundamentals", {"ticker": "TEST", "cik": CIK, "as_of": AS_OF, **request}, runtime=runtime)


class ThePriceComesFromTheBars(unittest.TestCase):
    def test_the_last_completed_close_becomes_the_multiple(self) -> None:
        payload = run()

        reading = payload["data"]["valuation"]["price_earnings_ratio"]
        self.assertEqual(reading["state"], "reported")
        self.assertEqual(reading["trailing_12m_eps"], 3.7)
        self.assertEqual(reading["last_close"], round(100.0 + (len(pd.bdate_range("2024-01-02", AS_OF)) - 1) * 0.01, 10))

    def test_the_price_provider_is_named_among_the_sources(self) -> None:
        payload = run()

        self.assertEqual(sorted(source["provider"] for source in payload["sources"]), ["sec", "yfinance"])

    def test_a_breakout_date_is_priced_from_that_session(self) -> None:
        payload = run(breakout_date="2025-03-14")

        expansion = payload["data"]["valuation"]["pe_expansion"]
        self.assertEqual(expansion["breakout_date"], "2025-03-14")
        self.assertIsNotNone(expansion["pe_ratio_at_breakout"])
        self.assertEqual(expansion["elapsed"]["measured"], 13)

    def test_a_breakout_date_after_as_of_is_refused_as_a_request_error(self) -> None:
        payload = run(breakout_date="2026-06-01")

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual([item["id"] for item in payload["missing"]], ["breakout_date"])


class TheFilingsStillDecideWithoutAPrice(unittest.TestCase):
    def test_an_unavailable_price_provider_leaves_the_verdict_standing(self) -> None:
        def refuse(ticker, as_of):
            raise ProviderUnavailable("yfinance", "no_data", operation="daily_bars")

        payload = run(price_history=refuse)

        self.assertEqual(payload["data"]["fundamentals_state"], "supports_convergence")
        self.assertEqual(payload["data"]["valuation"]["price_earnings_ratio"]["state"], "unavailable")
        self.assertEqual(payload["data"]["valuation"]["price_earnings_ratio"]["missing_inputs"], ["last_close"])
        self.assertEqual([item["id"] for item in payload["missing"]], ["daily_bars"])
        self.assertIs(payload["missing"][0]["required"], False)


if __name__ == "__main__":
    unittest.main()
