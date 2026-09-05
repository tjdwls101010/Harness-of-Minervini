"""The whole path, from SEC documents to a fundamentals verdict.

The provider's own output shape is the thing under test here: what `normalize_filed_facts`
returns is what the evaluator has to be able to reach a verdict from. Building the fixture
as SEC's two documents rather than as the normalized form is the point -- the previous
fixtures were hand-written in the normalized shape and carried fields the provider has never
emitted, which is how a live path that always came back INCOMPLETE went unnoticed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.providers.sec import normalize_filed_facts


from tests.filings import AS_OF, CIK, bars, company_facts, submissions


def price_snapshot() -> ProviderSnapshot:
    return ProviderSnapshot(bars("2024-01-02", AS_OF, 100.0), SnapshotMeta(provider="yfinance", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"completed_only": True}))


def run(**request) -> dict:
    normalized = normalize_filed_facts(company_facts(), submissions(), as_of=AS_OF)
    snapshot = ProviderSnapshot(normalized, SnapshotMeta(provider="sec", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), coverage={"filed_only": True}))
    # The capability reads its own price now, so a fixture that leaves the hook undeclared
    # reaches the live provider -- a unit-speed test making a network call nobody asked for.
    runtime = Runtime(fundamentals_evidence=lambda ticker, as_of, cik: snapshot, price_history=lambda ticker, as_of: price_snapshot())
    return execute("ticker.fundamentals", {"ticker": "TEST", "cik": CIK, "as_of": AS_OF, **request}, runtime=runtime)


class TheProviderSendsEnoughToDecide(unittest.TestCase):
    def test_accelerating_filed_facts_support_convergence(self) -> None:
        payload = run()

        self.assertEqual(payload["data"]["fundamentals_state"], "supports_convergence")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["missing"], [])

    def test_a_declared_going_concern_doubt_still_governs(self) -> None:
        payload = run(going_concern="substantial_doubt")

        self.assertEqual(payload["data"]["fundamentals_state"], "does_not_support_convergence")

    def test_the_narrative_checks_are_named_as_a_boundary_not_as_a_gap(self) -> None:
        payload = run()

        integrity = payload["data"]["integrity"]
        self.assertEqual(integrity["going_concern"]["state"], "not_evaluated")
        self.assertEqual(integrity["accounting_integrity"]["state"], "not_evaluated")
        self.assertEqual([item["id"] for item in payload["missing"]], [])


class TheEnvelopeAdmitsWhatItRead(unittest.TestCase):
    """A fixed list of one claim said far less than the payload used.

    Every reading in this capability now names the claim it came from, and the envelope's
    citation list is the reader's index into them. Leaving it at `scope.data_integrity` meant
    a result citing two dozen claims declared one, which is the same drift in the other
    direction as a list that overstates.
    """

    def test_the_claims_the_payload_names_are_the_claims_the_envelope_cites(self) -> None:
        payload = run(leader_category="turnaround")

        cited = payload["doctrine_ids"]
        self.assertIn("scope.data_integrity", cited)
        self.assertIn("fundamentals.minimum_quarterly_earnings_growth", cited)
        self.assertIn("fundamentals.code_33_triple_acceleration", cited)
        self.assertIn("fundamentals.turnaround_qualifying_criteria", cited)
        self.assertEqual(len(cited), len(set(cited)))
        self.assertEqual(cited[0], "scope.data_integrity")

    def test_a_category_nobody_declared_is_not_cited(self) -> None:
        payload = run()

        self.assertNotIn("fundamentals.turnaround_qualifying_criteria", payload["doctrine_ids"])


if __name__ == "__main__":
    unittest.main()
