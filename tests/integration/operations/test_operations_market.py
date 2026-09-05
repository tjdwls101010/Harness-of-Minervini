"""Behavior checks for operations market."""

from __future__ import annotations

from tests.paths import FIXTURES
from tests.providers import rows_snapshot
import unittest
from datetime import date, datetime, timezone
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.nasdaq import SecurityRecord
from tests.integration.operations._operation_fixtures import AS_OF, list_snapshot, price_snapshot, stale_price_snapshot


class OperationCompositionTests(unittest.TestCase):

    def test_market_snapshot_composes_independent_sources_and_requires_trade_traction_for_regime(self) -> None:
        finviz = FIXTURES / "market_evidence" / "finviz_partial.html"
        runtime = Runtime(
            price_history=lambda ticker, as_of: price_snapshot(),
            finviz_breadth=lambda as_of: rows_snapshot(finviz.read_text(encoding="utf-8"), provider="finviz", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), content_sha256="fixture"),
            sector_ranking=lambda as_of: list_snapshot(
                "ibd-rs-rating",
                [
                    {"sector": "Zeta Technology", "avg_rs": 92.0, "count": 20},
                    {"sector": "Alpha Energy", "avg_rs": 80.0, "count": 12},
                ],
            ),
            industry_ranking=lambda as_of: list_snapshot(
                "ibd-rs-rating",
                [{"industry": "Semiconductors", "sector": "Zeta Technology", "avg_rs": 95.0, "count": 8}],
            ),
            market_leaders=lambda as_of, limit: list_snapshot(
                "ibd-rs-rating",
                [{"ticker": "LEAD", "rs_rating": 99, "rs_raw": 4.2}],
            ),
        )

        payload = execute(
            "market.snapshot",
            {"as_of": AS_OF, "trade_traction": "supports", "leader_limit": 10},
            runtime=runtime,
        )

        self.assertEqual(payload["status"], "partial")
        # Leaders measured from their own bars, traction supplied, index switch on.
        self.assertEqual(payload["data"]["regime"]["judgment"], "favorable")
        self.assertEqual(payload["data"]["group_ranks"]["sectors"][0]["name"], "Zeta Technology")
        self.assertEqual(payload["data"]["leaders"][0]["ticker"], "LEAD")
        self.assertEqual({source["provider"] for source in payload["sources"]}, {"fixture-prices", "finviz", "ibd-rs-rating"})

        without_traction = execute("market.snapshot", {"as_of": AS_OF}, runtime=runtime)
        self.assertEqual(without_traction["status"], "needs_input")
        self.assertIn("trade_traction", {item["id"] for item in without_traction["missing"]})

    def test_market_snapshot_does_not_read_the_index_switch_from_a_stale_session(self) -> None:
        runtime = Runtime(
            price_history=lambda ticker, as_of: stale_price_snapshot(),
            finviz_breadth=lambda as_of: (_ for _ in ()).throw(ProviderUnavailable("finviz", "raw_snapshot_unavailable")),
            sector_ranking=lambda as_of: list_snapshot("ibd-rs-rating", []),
            industry_ranking=lambda as_of: list_snapshot("ibd-rs-rating", []),
            market_leaders=lambda as_of, limit: list_snapshot("ibd-rs-rating", []),
        )

        payload = execute("market.snapshot", {"as_of": AS_OF, "trade_traction": "supports"}, runtime=runtime)

        self.assertIn("completed_price_evidence", {item["id"] for item in payload["missing"]})
        switch = next(s for s in payload["signals"] if s["id"] == "qqq_21ema_switch")
        self.assertEqual(switch["state"], "unavailable")

    def test_market_candidates_filters_provider_records_and_preserves_pagination(self) -> None:
        records = [
            SecurityRecord("nasdaq:NASDAQ:GOOD", "GOOD", "NASDAQ", "Good Common Stock", "common_stock", False, True, None),
            SecurityRecord("nasdaq:NASDAQ:FUND", "FUND", "NASDAQ", "Fund ETF", "etf", False, False, "etf"),
        ]
        snapshot = rows_snapshot(records, provider="nasdaq", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date(2026, 1, 2), content_sha256="frozen")
        runtime = Runtime(security_master=lambda as_of: snapshot)

        payload = execute("market.candidates", {"limit": 1}, runtime=runtime)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual([item["ticker"] for item in payload["data"]["candidates"]], ["GOOD"])
        self.assertEqual(payload["data"]["page"]["page_size"], 1)
        self.assertEqual(payload["data"]["exclusions"]["total_count"], 1)
        self.assertEqual(payload["data"]["exclusions"]["reason_counts"], {"etf_context_only": 1})
        self.assertEqual(len(payload["data"]["exclusions"]["samples"]), 1)
