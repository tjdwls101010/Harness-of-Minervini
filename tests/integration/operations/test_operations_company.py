"""Behavior checks for operations company."""

from __future__ import annotations

from tests.paths import FIXTURES
from tests.providers import rows_snapshot
import json
import unittest
from datetime import date, datetime, timezone
import pandas as pd
from scripts.minervini.clock import resolve_as_of
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers.nasdaq import SecurityRecord
from tests.integration.operations._operation_fixtures import AS_OF, classification_snapshot, list_snapshot, price_snapshot, rs_snapshot


class OperationCompositionTests(unittest.TestCase):

    def test_ticker_peers_composes_current_identity_exact_rs_and_completed_prices(self) -> None:
        peer_as_of = resolve_as_of().date.isoformat()
        records = [
            SecurityRecord("nasdaq-trader:NASDAQ:TEST", "TEST", "NASDAQ", "Test Common Stock", "common_stock", False, True, None),
            SecurityRecord("nasdaq-trader:NYSE:LEAD", "LEAD", "NYSE", "Lead Common Stock", "common_stock", False, True, None),
        ]
        master = rows_snapshot(records, provider="nasdaq", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date(2026, 1, 2), coverage={"kind": "current_security_master_only", "historical": False})
        runtime = Runtime(
            current_classification=lambda ticker: classification_snapshot(),
            security_master=lambda as_of: master,
            industry_top=lambda industry, as_of, limit: list_snapshot(
                "ibd-rs-rating",
                [{"ticker": "LEAD", "rs_rating": 98, "rs_raw": 3.1}],
            ),
            rs_rating=lambda ticker, as_of: rs_snapshot(as_of=peer_as_of),
            price_history=lambda ticker, as_of: price_snapshot(as_of=peer_as_of),
        )

        payload = execute("ticker.peers", {"ticker": "TEST", "limit": 10}, runtime=runtime)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["industry"], "Semiconductors")
        self.assertEqual(payload["data"]["target"]["ticker"], "TEST")
        self.assertEqual(payload["data"]["peers"][0]["ticker"], "LEAD")
        self.assertEqual({source["provider"] for source in payload["sources"]}, {"yfinance", "nasdaq", "ibd-rs-rating", "fixture-prices", "fixture-rs"})

    def test_ticker_peers_refuses_historical_taxonomy_reconstruction(self) -> None:
        runtime = Runtime(current_classification=lambda ticker: self.fail("current classification must not answer a historical request"))

        payload = execute("ticker.peers", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["missing"][0]["reason"], "historical_classification_unavailable")

    def test_fundamentals_consumes_only_normalized_filed_sec_evidence(self) -> None:
        fixture = FIXTURES / "fundamentals" / "filed_evidence.json"
        sec_evidence = json.loads(fixture.read_text(encoding="utf-8"))
        snapshot = rows_snapshot(sec_evidence, provider="sec", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date(2026, 5, 10), coverage={"kind": "filed_facts"})
        # The capability reads its own price now. Leaving the hook undeclared sends this test
        # to the live provider, so it passes or fails on whether the machine has a network.
        prices = pd.DataFrame(
            {"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1_000_000},
            index=pd.bdate_range("2024-01-02", "2026-05-08"),
        )
        runtime = Runtime(
            fundamentals_evidence=lambda ticker, as_of, cik: snapshot,
            price_history=lambda ticker, as_of: rows_snapshot(prices, provider="yfinance", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date(2026, 5, 8), coverage={"completed_only": True}),
        )

        payload = execute(
            "ticker.fundamentals",
            {"ticker": "TEST", "as_of": "2026-05-08", "cik": "0000123456"},
            runtime=runtime,
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["ticker"], "TEST")
        # 28% year-over-year clears the 20-25 minimum the source names, decelerating from 60
        # or not: how much of a slowdown matters is a judgement the source declined to bound.
        self.assertEqual(payload["data"]["fundamentals_state"], "supports_convergence")
        # 2025-Q4 was never filed, so the last two rates in this fixture are three quarters
        # apart. "The one before it" means the quarter before it, and there is none here.
        self.assertEqual(payload["data"]["growth"]["earnings_deceleration"]["reason"], "no_adjacent_quarter_to_compare")
        self.assertIsNone(payload["data"]["growth"]["earnings_deceleration"]["decelerated"])
        self.assertEqual(payload["sources"][0]["provider"], "sec")

    def test_historical_fundamentals_requires_stable_cik_instead_of_current_ticker_identity(self) -> None:
        runtime = Runtime(fundamentals_evidence=lambda ticker, as_of, cik: self.fail("must not use current identity"))

        payload = execute(
            "ticker.fundamentals",
            {"ticker": "TEST", "as_of": "2026-05-08"},
            runtime=runtime,
        )

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["missing"][0]["id"], "cik")
