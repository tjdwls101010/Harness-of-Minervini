"""Behavior checks for operations ticker."""

from __future__ import annotations

import unittest
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable
from tests.integration.operations._operation_fixtures import AS_OF, price_snapshot, rs_snapshot, stale_price_snapshot


class OperationCompositionTests(unittest.TestCase):

    def test_qualify_composes_completed_prices_and_first_party_rs_without_touching_the_ledger(self) -> None:
        runtime = Runtime(
            price_history=lambda ticker, as_of: price_snapshot(),
            rs_rating=lambda ticker, as_of: rs_snapshot(),
            ledger_factory=lambda: self.fail("analysis must not open the ledger"),
        )

        payload = execute("ticker.qualify", {"ticker": "test", "as_of": AS_OF}, runtime=runtime)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["ticker"], "TEST")
        self.assertEqual(payload["data"]["route"], "standard")
        self.assertEqual(payload["data"]["eligibility_state"], "eligible")
        self.assertEqual({source["provider"] for source in payload["sources"]}, {"fixture-prices", "fixture-rs"})
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["next_capabilities"], ["ticker.setup", "ticker.fundamentals"])

    def test_known_price_failure_stays_avoid_when_rs_is_unavailable(self) -> None:
        def unavailable_rs(ticker: str, as_of: str) -> ProviderSnapshot[dict[str, object]]:
            raise ProviderUnavailable("fixture-rs", "rating_missing", operation="rating")

        runtime = Runtime(
            price_history=lambda ticker, as_of: price_snapshot(rising=False),
            rs_rating=unavailable_rs,
        )

        payload = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["data"]["eligibility_state"], "avoid")
        self.assertIn("fixture-rs", {item.get("provider") for item in payload["missing"]})
        rs = next(signal for signal in payload["signals"] if signal["id"] == "trend_template.relative_strength_minimum")
        self.assertEqual(rs["state"], "unavailable")

    def test_an_unavailable_provider_reports_why_it_failed(self) -> None:
        def unavailable_rs(ticker: str, as_of: str) -> ProviderSnapshot[dict[str, object]]:
            raise ProviderUnavailable(
                "fixture-rs",
                "request_failed",
                operation="dates",
                detail="ConnectionError: certificate verify failed",
            )

        runtime = Runtime(
            price_history=lambda ticker, as_of: price_snapshot(),
            rs_rating=unavailable_rs,
        )

        payload = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

        gap = next(item for item in payload["missing"] if item["provider"] == "fixture-rs")
        self.assertEqual(gap["detail"], "ConnectionError: certificate verify failed")

    def test_qualify_refuses_to_judge_eligibility_from_a_session_behind_price_history(self) -> None:
        runtime = Runtime(
            price_history=lambda ticker, as_of: stale_price_snapshot(),
            rs_rating=lambda ticker, as_of: rs_snapshot(),
        )

        payload = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["data"]["eligibility_state"], "incomplete")
        self.assertIn("completed_price_evidence", {item["id"] for item in payload["missing"]})
        self.assertEqual(payload["next_capabilities"], [])

    def test_setup_refuses_to_judge_a_setup_from_a_session_behind_price_history(self) -> None:
        runtime = Runtime(price_history=lambda ticker, as_of: stale_price_snapshot())

        payload = execute("ticker.setup", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["data"]["setup_state"], "incomplete")
        self.assertIn("completed_price_evidence", {item["id"] for item in payload["missing"]})
