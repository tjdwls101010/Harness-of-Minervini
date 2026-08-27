"""What the envelope says about the price it fetched, and about the date the caller named.

The capability's own prose promises `partial` when the price provider has nothing to give. It was
returning `ok`, so a page that says "the multiple is unavailable" arrived under a status word
meaning the question has a finished answer. A stale snapshot was worse: it published a close from
an earlier session as the last completed one, with no gap named at all.

And a breakout date naming no completed session was being dropped between the request and the
evaluator, so the envelope echoed the date in `request` while the reading beside it said no
breakout date had been supplied.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta
from scripts.minervini.providers.sec import normalize_filed_facts

from .test_the_live_path_reaches_a_verdict import AS_OF, CIK, company_facts, submissions


def bars(end: str, close: float = 100.0) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-02", end)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": [close + n * 0.01 for n in range(len(index))], "Volume": 1_000_000}, index=index)


def snapshot(frame: pd.DataFrame, as_of: str, stale: bool = False) -> ProviderSnapshot[pd.DataFrame]:
    return ProviderSnapshot(frame, SnapshotMeta(provider="yfinance", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(as_of), coverage={"completed_only": True}, stale=stale))


def run(price_history=None, **request) -> dict:
    normalized = normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
    filings = ProviderSnapshot(normalized, SnapshotMeta(provider="sec", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"filed_only": True}))
    prices = price_history or (lambda ticker, as_of: snapshot(bars(AS_OF), AS_OF))
    runtime = Runtime(fundamentals_evidence=lambda ticker, as_of, cik: filings, price_history=prices)
    return execute("ticker.fundamentals", {"ticker": "TEST", "cik": CIK, "as_of": AS_OF, **request}, runtime=runtime)


class TheStatusWordMatchesTheGap(unittest.TestCase):
    def test_an_unavailable_price_provider_is_partial_as_the_prose_promises(self) -> None:
        def refuse(ticker, as_of):
            raise ProviderUnavailable("yfinance", "no_data", operation="daily_bars")

        payload = run(price_history=refuse)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["data"]["fundamentals_state"], "supports_convergence")

    def test_a_history_that_stops_early_withholds_the_multiple_rather_than_dating_it_wrong(self) -> None:
        payload = run(price_history=lambda ticker, as_of: snapshot(bars("2026-05-06"), "2026-05-06", stale=True))

        self.assertEqual(payload["status"], "partial")
        reading = payload["data"]["valuation"]["price_earnings_ratio"]
        self.assertEqual(reading["state"], "unavailable")
        self.assertEqual(reading["missing_inputs"], ["last_close"])
        self.assertIn("stale_price_evidence", [item["id"] for item in payload["missing"]])

    def test_a_history_reaching_the_session_is_ok(self) -> None:
        payload = run()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["valuation"]["price_earnings_ratio"]["state"], "reported")


class ADateThatNamesNoSession(unittest.TestCase):
    def test_a_breakout_date_with_no_completed_bar_is_refused_at_the_seam(self) -> None:
        payload = run(breakout_date="2025-03-15")

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual([item["id"] for item in payload["missing"]], ["breakout_date"])
        self.assertEqual(payload["missing"][0]["reason"], "no_completed_session_on_breakout_date")

    def test_a_breakout_date_on_a_session_is_read(self) -> None:
        payload = run(breakout_date="2025-03-14")

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["valuation"]["pe_expansion"]["breakout_date"], "2025-03-14")


class TheExpansionMeasuresWhatItSays(unittest.TestCase):
    def test_the_filings_list_says_available_rather_than_used(self) -> None:
        payload = run(breakout_date="2025-03-14")

        expansion = payload["data"]["valuation"]["pe_expansion"]
        self.assertIn("filings_available_at_breakout", expansion)
        self.assertNotIn("filings_used_at_breakout", expansion)



class ADateTheCallerGaveIsNotAMissingDate(unittest.TestCase):
    def test_a_stale_history_withholds_the_close_and_keeps_the_date(self) -> None:
        payload = run(price_history=lambda ticker, as_of: snapshot(bars("2026-05-06"), "2026-05-06", stale=True), breakout_date="2025-03-14")

        expansion = payload["data"]["valuation"]["pe_expansion"]
        self.assertEqual(expansion["missing_inputs"], ["breakout_close"])
        self.assertEqual(expansion["breakout_date"], "2025-03-14")


if __name__ == "__main__":
    unittest.main()
