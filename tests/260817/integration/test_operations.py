from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.minervini.ledger import Ledger
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta
from scripts.minervini.providers.nasdaq import SecurityRecord


AS_OF = "2025-12-31"


def price_snapshot(*, rising: bool = True) -> ProviderSnapshot[pd.DataFrame]:
    values = np.linspace(50, 150, 260) if rising else np.linspace(180, 80, 260)
    index = pd.bdate_range(end=AS_OF, periods=len(values))
    close = pd.Series(values, index=index)
    frame = pd.DataFrame(
        {
            "Open": close * 0.995,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000),
        },
        index=index,
    )
    return ProviderSnapshot(
        frame,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date.fromisoformat(AS_OF),
            coverage={"completed_only": True},
        ),
    )


def rs_snapshot() -> ProviderSnapshot[dict[str, object]]:
    return ProviderSnapshot(
        {"ticker": "TEST", "rating": 94, "rating_date": AS_OF},
        SnapshotMeta(
            provider="fixture-rs",
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date.fromisoformat(AS_OF),
            provider_version="0.5.0",
        ),
    )


def list_snapshot(provider: str, data: list[dict[str, object]]) -> ProviderSnapshot[list[dict[str, object]]]:
    return ProviderSnapshot(
        data,
        SnapshotMeta(
            provider=provider,
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date.fromisoformat(AS_OF),
            provider_version="0.5.0" if provider == "ibd-rs-rating" else None,
        ),
    )


class OperationCompositionTests(unittest.TestCase):
    def test_market_snapshot_composes_independent_sources_and_requires_trade_traction_for_regime(self) -> None:
        finviz = Path(__file__).resolve().parents[1] / "fixtures" / "market_evidence" / "finviz_partial.html"
        runtime = Runtime(
            price_history=lambda ticker, as_of: price_snapshot(),
            finviz_breadth=lambda as_of: ProviderSnapshot(
                finviz.read_text(encoding="utf-8"),
                SnapshotMeta(
                    provider="finviz",
                    retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                    as_of=date.fromisoformat(AS_OF),
                    content_sha256="fixture",
                ),
            ),
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
        self.assertEqual(payload["data"]["regime"]["judgment"], "cautious")
        self.assertEqual(payload["data"]["group_ranks"]["sectors"][0]["name"], "Zeta Technology")
        self.assertEqual(payload["data"]["leaders"][0]["ticker"], "LEAD")
        self.assertEqual({source["provider"] for source in payload["sources"]}, {"fixture-prices", "finviz", "ibd-rs-rating"})

        without_traction = execute("market.snapshot", {"as_of": AS_OF}, runtime=runtime)
        self.assertEqual(without_traction["status"], "needs_input")
        self.assertIn("trade_traction", {item["id"] for item in without_traction["missing"]})

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
        self.assertIn("fixture-rs", {item["provider"] for item in payload["missing"]})
        rs = next(signal for signal in payload["signals"] if signal["id"] == "trend_template.relative_strength_minimum")
        self.assertEqual(rs["state"], "unavailable")

    def test_market_candidates_filters_provider_records_and_preserves_pagination(self) -> None:
        records = [
            SecurityRecord("nasdaq:NASDAQ:GOOD", "GOOD", "NASDAQ", "Good Common Stock", "common_stock", False, True, None),
            SecurityRecord("nasdaq:NASDAQ:FUND", "FUND", "NASDAQ", "Fund ETF", "etf", False, False, "etf"),
        ]
        snapshot = ProviderSnapshot(
            records,
            SnapshotMeta(
                provider="nasdaq",
                retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                as_of=date(2026, 1, 2),
                content_sha256="frozen",
            ),
        )
        runtime = Runtime(security_master=lambda as_of: snapshot)

        payload = execute("market.candidates", {"limit": 1}, runtime=runtime)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual([item["ticker"] for item in payload["data"]["candidates"]], ["GOOD"])
        self.assertEqual(payload["data"]["page"]["page_size"], 1)
        self.assertEqual(payload["data"]["page"]["recommendation_count"], 0)

    def test_active_risk_with_missing_anchors_is_a_domain_needs_input_not_an_internal_error(self) -> None:
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "as_of": AS_OF},
            runtime=Runtime(),
        )

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertEqual(set(payload["data"]["missing"]), {"entry_date", "stop_or_invalidation"})

    def test_fundamentals_consumes_only_normalized_filed_sec_evidence(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "fundamentals" / "filed_evidence.json"
        sec_evidence = json.loads(fixture.read_text(encoding="utf-8"))
        snapshot = ProviderSnapshot(
            sec_evidence,
            SnapshotMeta(
                provider="sec",
                retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
                as_of=date(2026, 5, 10),
                coverage={"kind": "filed_facts"},
            ),
        )
        runtime = Runtime(fundamentals_evidence=lambda ticker, as_of, cik: snapshot)

        payload = execute(
            "ticker.fundamentals",
            {"ticker": "TEST", "as_of": "2026-05-10", "cik": "0000123456"},
            runtime=runtime,
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["ticker"], "TEST")
        self.assertEqual(payload["data"]["fundamentals_state"], "does_not_support_convergence")
        self.assertEqual(payload["sources"][0]["provider"], "sec")

    def test_historical_fundamentals_requires_stable_cik_instead_of_current_ticker_identity(self) -> None:
        runtime = Runtime(fundamentals_evidence=lambda ticker, as_of, cik: self.fail("must not use current identity"))

        payload = execute(
            "ticker.fundamentals",
            {"ticker": "TEST", "as_of": "2026-05-10"},
            runtime=runtime,
        )

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["missing"][0]["id"], "cik")

    def test_chart_operation_records_each_explicit_artifact_side_effect(self) -> None:
        runtime = Runtime(price_history=lambda ticker, as_of: price_snapshot())
        with tempfile.TemporaryDirectory() as temporary:
            payload = execute(
                "ticker.chart",
                {"ticker": "TEST", "as_of": AS_OF, "output_dir": temporary},
                runtime=runtime,
            )

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data"]["ticker"], "TEST")
            self.assertEqual([item["timeframe"] for item in payload["data"]["artifacts"]], ["weekly", "daily"])
            self.assertEqual({item["type"] for item in payload["side_effects"]}, {"chart_artifact", "artifact_manifest"})
            self.assertTrue(all(Path(item["path"]).exists() for item in payload["side_effects"]))

    def test_ledger_reads_are_side_effect_free_and_record_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.sqlite3"
            runtime = Runtime(ledger_factory=lambda: Ledger(path))

            empty = execute("watchlist.show", {}, runtime=runtime)

            self.assertEqual(empty["data"]["records"], [])
            self.assertFalse(path.exists())

            output_hash = hashlib.sha256(b"fixture-output").hexdigest()
            recorded = execute(
                "watchlist.record",
                {
                    "ticker": "TEST",
                    "instrument_id": "nasdaq:NASDAQ:TEST",
                    "as_of": AS_OF,
                    "output_hash": output_hash,
                    "verdict": "WAIT",
                    "condition": "completed close above 100",
                    "invalidation": "close below 94",
                    "doctrine_ids": ["setup.vcp_supply"],
                    "evidence_quality": "partial",
                    "note": "fixture",
                },
                runtime=runtime,
            )

            self.assertEqual(recorded["status"], "ok")
            self.assertTrue(path.exists())
            self.assertEqual(recorded["side_effects"][0]["type"], "sqlite_write")
            self.assertEqual(execute("watchlist.history", {"ticker": "TEST"}, runtime=runtime)["data"]["events"][0]["operation"], "record")


if __name__ == "__main__":
    unittest.main()
