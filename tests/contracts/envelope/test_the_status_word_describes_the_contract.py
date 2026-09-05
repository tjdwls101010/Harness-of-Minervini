"""What `status` says, and what `declared_inputs` has to list.

`status` describes contract completeness rather than verdict polarity. A negative verdict
supported by a declaration is still an answer built on filings that never arrived, and reading
it as `ok` tells a caller the evidence was whole. And a declaration the payload acts on has to
appear among the declarations the payload lists, or the two disagree about what was supplied.
"""

from __future__ import annotations

from tests.providers import rows_snapshot

from datetime import date, datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute


from tests.integration.operations.test_the_live_path_reaches_a_verdict import AS_OF, CIK, bars, company_facts, submissions
from scripts.minervini.providers.sec import normalize_filed_facts


def run(evidence: dict | None = None, **request) -> dict:
    normalized = evidence if evidence is not None else normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
    filings = rows_snapshot(normalized, provider="sec", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"filed_only": True})
    prices = rows_snapshot(bars("2024-01-02", AS_OF, 100.0), provider="yfinance", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True})
    runtime = Runtime(fundamentals_evidence=lambda ticker, as_of, cik: filings, price_history=lambda ticker, as_of: prices)
    return execute("ticker.fundamentals", {"ticker": "TEST", "cik": CIK, "as_of": AS_OF, **request}, runtime=runtime)


class RequiredEvidenceStillMissingIsAPartialAnswer(unittest.TestCase):
    def test_a_verdict_a_declaration_settled_does_not_make_the_contract_whole(self) -> None:
        payload = run(evidence={"source": "sec_filed_facts", "filings": []}, going_concern="substantial_doubt")

        self.assertEqual(payload["data"]["fundamentals_state"], "does_not_support_convergence")
        self.assertTrue(any(item["required"] for item in payload["missing"]))
        self.assertEqual(payload["status"], "partial")

    def test_a_complete_reading_is_still_ok(self) -> None:
        payload = run()

        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["status"], "ok")


class ADeclarationThePayloadActsOnIsListedAmongTheDeclarations(unittest.TestCase):
    def test_the_market_regime_appears_in_declared_inputs(self) -> None:
        payload = run(market_regime="bull")

        self.assertEqual(payload["data"]["growth"]["bull_market_quarterly_earnings_growth"]["market_regime"], "bull")
        self.assertEqual(payload["data"]["declared_inputs"]["market_regime"], "bull")

    def test_an_undeclared_regime_is_listed_as_undeclared(self) -> None:
        payload = run()

        self.assertIsNone(payload["data"]["declared_inputs"]["market_regime"])


if __name__ == "__main__":
    unittest.main()
