"""The envelope asked for a CIK and named nowhere to get one.

`ticker.fundamentals` against a past session returns `needs_input` with
`missing: [{"id": "cik", "reason": "stable_historical_identity_required"}]`, and no capability
in this harness produces one. The value is required, the interface does not carry it, and the
envelope's own `next_capabilities` is empty -- so an analyst reading it is told what is missing
and left to find it somewhere the harness cannot vouch for.

The lookup itself already exists: `providers.sec.fetch_company_tickers` is what `ticker.fundamentals`
calls when no `--cik` is given, and what the health probe uses. What was missing is a surface a
person can run.

Why it refuses a past session is the reason `--cik` is a caller's assertion in the first place.
`company_tickers.json` is a mutable current snapshot: a ticker can be reassigned, so today's
mapping is not evidence about who filed under that symbol a year ago. Answering a historical
request from it would be current security-master data relabelled as historical, which the
constitution refuses outright. So the capability answers for the current session and states what
it is; deciding that the identity held back then stays the analyst's assertion, made with `--cik`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta


COMPANY_TICKERS = {
    "AAPL": {"cik": "0000320193", "title": "Apple Inc."},
    "NVDA": {"cik": "0001045810", "title": "NVIDIA CORP"},
}


def _snapshot(payload):
    return ProviderSnapshot(
        payload,
        SnapshotMeta(
            provider="sec",
            retrieved_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
            as_of=None,
            coverage={"kind": "mutable_current_only", "documents": ["company_tickers"]},
            content_sha256="0" * 64,
        ),
    )


def runtime(*, fails: str | None = None) -> Runtime:
    def company_tickers():
        if fails is not None:
            raise ProviderUnavailable("sec", fails, operation="company_tickers")
        return _snapshot(COMPANY_TICKERS)

    return Runtime(company_tickers=company_tickers)


def resolve(ticker: str, **request) -> dict:
    return execute("ticker.cik", {"ticker": ticker, **request}, runtime=runtime())


class ACikHasAPlaceToComeFrom(unittest.TestCase):
    def test_a_listed_ticker_resolves_to_its_filing_identity(self) -> None:
        payload = resolve("AAPL")

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["ticker"], "AAPL")
        self.assertEqual(payload["data"]["cik"], "0000320193")
        self.assertEqual(payload["data"]["title"], "Apple Inc.")
        self.assertEqual([source["provider"] for source in payload["sources"]], ["sec"])

    def test_a_ticker_the_list_does_not_carry_is_unavailable_rather_than_guessed(self) -> None:
        """The source answered. This symbol is not in it, which is not the same as no answer."""

        payload = resolve("NOSUCH")

        self.assertEqual(payload["status"], "unavailable")
        self.assertIsNone(payload["data"].get("cik"))
        self.assertEqual([gap["reason"] for gap in payload["missing"]], ["ticker_not_found"])

    def test_a_provider_that_could_not_answer_is_a_different_gap(self) -> None:
        payload = execute("ticker.cik", {"ticker": "AAPL"}, runtime=runtime(fails="sec_unreachable"))

        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual([gap["reason"] for gap in payload["missing"]], ["sec_unreachable"])

    def test_a_past_session_is_refused_rather_than_answered_from_todays_map(self) -> None:
        """Today's mapping is not evidence about who filed under this symbol a year ago."""

        payload = resolve("AAPL", as_of="2025-08-14")

        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(
            [gap["reason"] for gap in payload["missing"]],
            ["ticker_to_cik_map_is_current_only"],
        )
        self.assertIsNone(payload["data"].get("cik"))


class TheEnvelopeSaysWhereTheValueComesFrom(unittest.TestCase):
    def test_the_fundamentals_gap_names_the_capability_that_closes_it(self) -> None:
        payload = execute(
            "ticker.fundamentals",
            {"ticker": "AAPL", "as_of": "2026-08-14"},
            runtime=Runtime(),
        )

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual([gap["id"] for gap in payload["missing"]], ["cik"])
        self.assertEqual(payload["next_capabilities"], ["ticker.cik"])


if __name__ == "__main__":
    unittest.main()
