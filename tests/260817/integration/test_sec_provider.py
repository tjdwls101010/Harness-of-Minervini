from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from minervini.fundamentals import evaluate_fundamentals
from minervini.providers import ProviderUnavailable
from minervini.providers.sec import (
    fetch_company_facts,
    fetch_company_submissions,
    fetch_company_tickers,
    normalize_filed_facts,
)


FIXTURES = ROOT / "tests" / "260817" / "fixtures" / "providers" / "sec"
USER_AGENT = "Acme Research contact@example.com"


class FixtureResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FixtureGet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], int]] = []

    def __call__(self, url: str, *, headers: dict[str, str], timeout: int) -> FixtureResponse:
        self.calls.append((url, headers, timeout))
        if url.endswith("company_tickers.json"):
            name = "company_tickers.json"
        elif "/companyfacts/" in url:
            name = "companyfacts.json"
        elif "/submissions/" in url:
            name = "submissions.json"
        else:
            raise AssertionError(f"Unexpected SEC URL: {url}")
        return FixtureResponse(json.loads((FIXTURES / name).read_text()))


class SecProviderTests(unittest.TestCase):
    def test_fetches_validated_sec_documents_with_an_explicit_identifiable_user_agent(self) -> None:
        request_get = FixtureGet()

        tickers = fetch_company_tickers(
            request_get=request_get,
            user_agent=USER_AGENT,
            retrieved_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        )
        facts = fetch_company_facts("123456", request_get=request_get, user_agent=USER_AGENT)
        submissions = fetch_company_submissions("0000123456", request_get=request_get, user_agent=USER_AGENT)

        self.assertEqual(tickers.data["ACME"], {"cik": "0000123456", "title": "Acme Momentum, Inc."})
        self.assertEqual(facts.data["cik"], "0000123456")
        self.assertEqual(submissions.data["cik"], "0000123456")
        self.assertEqual(tickers.meta.as_of.isoformat(), "2026-08-17")
        self.assertEqual(tickers.meta.content_sha256, fixture_hash("company_tickers.json"))
        self.assertEqual(facts.meta.content_sha256, fixture_hash("companyfacts.json"))
        self.assertEqual(submissions.meta.content_sha256, fixture_hash("submissions.json"))
        self.assertEqual(submissions.meta.coverage["older_indexes"], "not_fetched")
        self.assertEqual([headers for _, headers, _ in request_get.calls], [{"User-Agent": USER_AGENT}] * 3)
        self.assertTrue(request_get.calls[1][0].endswith("CIK0000123456.json"))
        self.assertTrue(request_get.calls[2][0].endswith("CIK0000123456.json"))

    def test_retries_the_injected_sec_request_once_at_the_provider_boundary(self) -> None:
        request_get = FixtureGet()
        original_get = request_get.__call__
        attempts = 0

        def flaky_get(url: str, *, headers: dict[str, str], timeout: int) -> FixtureResponse:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("fixture timeout")
            return original_get(url, headers=headers, timeout=timeout)

        snapshot = fetch_company_tickers(request_get=flaky_get, user_agent=USER_AGENT)

        self.assertEqual(attempts, 2)
        self.assertIn("ACME", snapshot.data)

    def test_normalizes_only_facts_filed_by_as_of_for_the_fundamentals_evaluator(self) -> None:
        request_get = FixtureGet()
        facts = fetch_company_facts("123456", request_get=request_get, user_agent=USER_AGENT)
        submissions = fetch_company_submissions("123456", request_get=request_get, user_agent=USER_AGENT)

        evidence = normalize_filed_facts(facts.data, submissions.data, as_of="2026-05-10")
        evaluation = evaluate_fundamentals(evidence, as_of="2026-05-10")

        self.assertEqual(evidence["source"], "sec_filed_facts")
        self.assertEqual([filing["filed_at"] for filing in evidence["filings"]], ["2025-02-20", "2025-05-01", "2025-08-01", "2025-11-01", "2026-02-20", "2026-05-01", "2026-05-08"])
        self.assertEqual(evidence["filings"][-1]["quarterly"], [{"period": "2026-Q1", "end": "2026-03-31", "eps": 0.75, "revenue": 63.0, "net_income": 16.0, "diluted_shares": 101.0}])
        self.assertEqual(evaluation["quarterly"]["eps"][-1]["period"], "2026-Q1")
        self.assertEqual(evaluation["quarterly"]["eps"][-1]["value"], 0.75)
        self.assertEqual(evaluation["annual_growth"]["eps_yoy_pct"], 50.0)

    def test_uses_an_amendment_only_after_its_own_filing_date(self) -> None:
        request_get = FixtureGet()
        facts = fetch_company_facts("123456", request_get=request_get, user_agent=USER_AGENT)
        submissions = fetch_company_submissions("123456", request_get=request_get, user_agent=USER_AGENT)

        original = evaluate_fundamentals(normalize_filed_facts(facts.data, submissions.data, as_of="2026-05-05"), as_of="2026-05-05")
        amended = evaluate_fundamentals(normalize_filed_facts(facts.data, submissions.data, as_of="2026-05-10"), as_of="2026-05-10")

        self.assertEqual(original["quarterly"]["eps"][-1]["value"], 0.7)
        self.assertEqual(amended["quarterly"]["eps"][-1]["value"], 0.75)

    def test_rejects_an_unidentifiable_user_agent_before_making_a_request(self) -> None:
        request_get = FixtureGet()

        with self.assertRaises(ProviderUnavailable) as raised:
            fetch_company_tickers(request_get=request_get, user_agent="")

        self.assertEqual(raised.exception.reason, "identifiable_user_agent_required")
        self.assertEqual(request_get.calls, [])


def fixture_hash(name: str) -> str:
    payload = json.loads((FIXTURES / name).read_text())
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


if __name__ == "__main__":
    unittest.main()
