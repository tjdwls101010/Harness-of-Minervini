from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.minervini.cache import ProviderCache
from scripts.minervini.clock import resolve_as_of
from scripts.minervini.ledger import Ledger
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta
from scripts.minervini.providers.nasdaq import SecurityRecord


AS_OF = "2025-12-31"


def price_snapshot(*, rising: bool = True, as_of: str = AS_OF) -> ProviderSnapshot[pd.DataFrame]:
    values = np.linspace(50, 150, 260) if rising else np.linspace(180, 80, 260)
    index = pd.bdate_range(end=as_of, periods=len(values))
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
            as_of=date.fromisoformat(as_of),
            coverage={"completed_only": True},
        ),
    )


def stale_price_snapshot(*, as_of: str = AS_OF) -> ProviderSnapshot[pd.DataFrame]:
    """A history the provider could only complete through the session before as_of."""

    snapshot = price_snapshot(as_of="2025-12-30")
    return ProviderSnapshot(
        snapshot.data,
        SnapshotMeta(
            provider="fixture-prices",
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date(2025, 12, 30),
            coverage={"completed_only": True, "requested_session": as_of, "last_completed_bar": "2025-12-30"},
            stale=True,
        ),
    )


def rs_snapshot(*, as_of: str = AS_OF) -> ProviderSnapshot[dict[str, object]]:
    return ProviderSnapshot(
        {"ticker": "TEST", "rating": 94, "rating_date": as_of},
        SnapshotMeta(
            provider="fixture-rs",
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date.fromisoformat(as_of),
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


def classification_snapshot() -> ProviderSnapshot[dict[str, str]]:
    return ProviderSnapshot(
        {
            "symbol": "TEST",
            "sector": "Technology",
            "industry": "Semiconductors",
            "industry_id": "yfinance:technology:semiconductors",
        },
        SnapshotMeta(
            provider="yfinance",
            retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            as_of=date(2026, 1, 2),
            coverage={"kind": "current_classification_only", "historical": False},
        ),
    )


class OperationCompositionTests(unittest.TestCase):
    def test_no_cache_bypasses_both_operation_cache_reads_and_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            calls = {"price": 0, "rs": 0}

            def prices(ticker: str, as_of: str) -> ProviderSnapshot[pd.DataFrame]:
                calls["price"] += 1
                return price_snapshot()

            def rating(ticker: str, as_of: str) -> ProviderSnapshot[dict[str, object]]:
                calls["rs"] += 1
                return rs_snapshot()

            runtime = Runtime(
                price_history=prices,
                rs_rating=rating,
                cache=ProviderCache(root=Path(temporary)),
            )

            first = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)
            cached = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)
            bypassed = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF, "no_cache": True}, runtime=runtime)
            restored = execute("ticker.qualify", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

            self.assertEqual([item["status"] for item in (first, cached, bypassed, restored)], ["ok", "ok", "ok", "ok"])
            self.assertEqual(calls, {"price": 2, "rs": 2})

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

    def test_risk_withholds_a_hold_or_sell_when_price_history_is_a_session_behind(self) -> None:
        runtime = Runtime(price_history=lambda ticker, as_of: stale_price_snapshot())

        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "as_of": AS_OF, "mode": "active", "entry_price": 100.0, "entry_date": "2025-12-01", "stop_price": 94.0},
            runtime=runtime,
        )

        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertIn("completed_price_evidence", {item["id"] for item in payload["missing"]})

    def test_a_proven_stop_breach_survives_price_history_that_stops_early(self) -> None:
        runtime = Runtime(price_history=lambda ticker, as_of: stale_price_snapshot())

        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "as_of": AS_OF, "mode": "active", "entry_price": 200.0, "entry_date": "2025-12-01", "stop_price": 190.0},
            runtime=runtime,
        )

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "breached")

    def test_chart_writes_no_artifact_from_a_session_behind_price_history(self) -> None:
        runtime = Runtime(price_history=lambda ticker, as_of: stale_price_snapshot())

        payload = execute("ticker.chart", {"ticker": "TEST", "as_of": AS_OF}, runtime=runtime)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["side_effects"], [])
        self.assertIn("completed_price_evidence", {item["id"] for item in payload["missing"]})

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

    def test_health_keeps_its_offline_contract_unless_a_probe_is_requested(self) -> None:
        runtime = Runtime(
            reachability_probes={"fixture-rs": lambda: self.fail("health must not reach a provider by default")},
        )

        payload = execute("health", {}, runtime=runtime)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["reachability"], {"checked": False, "providers": {}})
        self.assertTrue(payload["data"]["configuration"]["tls_ca_bundle"]["ready"])
        self.assertIn("sec_user_agent", payload["data"]["configuration"])

    def test_health_probe_names_the_provider_that_cannot_be_reached_and_why(self) -> None:
        def unreachable() -> None:
            raise ProviderUnavailable(
                "fixture-rs",
                "request_failed",
                operation="dates",
                detail="ConnectionError: certificate verify failed",
            )

        runtime = Runtime(
            reachability_probes={"fixture-rs": unreachable, "fixture-prices": lambda: None},
        )

        payload = execute("health", {"probe": True}, runtime=runtime)

        self.assertEqual(payload["status"], "partial")
        self.assertFalse(payload["data"]["ready"])
        self.assertTrue(payload["data"]["reachability"]["checked"])
        providers = payload["data"]["reachability"]["providers"]
        self.assertTrue(providers["fixture-prices"]["reachable"])
        self.assertFalse(providers["fixture-rs"]["reachable"])
        self.assertEqual(providers["fixture-rs"]["detail"], "ConnectionError: certificate verify failed")

    def test_a_probe_that_breaks_reports_an_unreachable_provider_not_an_internal_error(self) -> None:
        def broken() -> None:
            raise ModuleNotFoundError("No module named 'rs_rating'")

        runtime = Runtime(reachability_probes={"fixture-rs": broken})

        payload = execute("health", {"probe": True}, runtime=runtime)

        self.assertEqual(payload["status"], "partial")
        provider = payload["data"]["reachability"]["providers"]["fixture-rs"]
        self.assertFalse(provider["reachable"])
        self.assertIn("ModuleNotFoundError", provider["detail"])
        self.assertIn("fixture-rs", {item.get("provider") for item in payload["missing"]})

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
        self.assertEqual(payload["data"]["exclusions"]["total_count"], 1)
        self.assertEqual(payload["data"]["exclusions"]["reason_counts"], {"etf_context_only": 1})
        self.assertEqual(len(payload["data"]["exclusions"]["samples"]), 1)

    def test_ticker_peers_composes_current_identity_exact_rs_and_completed_prices(self) -> None:
        peer_as_of = resolve_as_of().date.isoformat()
        records = [
            SecurityRecord("nasdaq-trader:NASDAQ:TEST", "TEST", "NASDAQ", "Test Common Stock", "common_stock", False, True, None),
            SecurityRecord("nasdaq-trader:NYSE:LEAD", "LEAD", "NYSE", "Lead Common Stock", "common_stock", False, True, None),
        ]
        master = ProviderSnapshot(
            records,
            SnapshotMeta(
                provider="nasdaq",
                retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                as_of=date(2026, 1, 2),
                coverage={"kind": "current_security_master_only", "historical": False},
            ),
        )
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

    def test_active_risk_with_missing_anchors_is_a_domain_needs_input_not_an_internal_error(self) -> None:
        payload = execute(
            "ticker.risk",
            {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "as_of": AS_OF},
            runtime=Runtime(),
        )

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertEqual(set(payload["data"]["missing"]), {"entry_date", "stop_or_invalidation", "current_price"})

    def test_active_risk_audits_the_completed_price_path_for_hold_or_stop_breach(self) -> None:
        runtime = Runtime(price_history=lambda ticker, as_of: price_snapshot())
        common = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-10-01", "as_of": AS_OF}

        hold = execute("ticker.risk", {**common, "stop_price": 94.0}, runtime=runtime)
        # Its own entry, because a stop in force from the entry session sits below the price
        # the position was entered at.
        sell = execute("ticker.risk", {**common, "entry_price": 200.0, "stop_price": 155.0}, runtime=runtime)

        self.assertEqual(hold["data"]["verdict"], "HOLD")
        self.assertEqual(hold["data"]["current_price"], 150.0)
        self.assertEqual(hold["data"]["completed_price_path"]["state"], "clear")
        self.assertEqual(hold["data"]["completed_price_path"]["from"], "2025-10-01")
        self.assertEqual(hold["sources"][0]["provider"], "fixture-prices")
        self.assertEqual(sell["data"]["verdict"], "SELL")
        self.assertEqual(sell["data"]["completed_price_path"]["state"], "breached")
        self.assertIn("completed_stop_breach", sell["data"]["failed"])

    def test_active_risk_detects_a_recovered_historical_stop_breach(self) -> None:
        snapshot = price_snapshot()
        frame = snapshot.data.copy()
        breach_date = frame.loc["2025-10-01":].index[5]
        frame.loc[breach_date, "Low"] = 90.0
        recovered = ProviderSnapshot(frame, snapshot.meta)
        runtime = Runtime(price_history=lambda ticker, as_of: recovered)

        payload = execute(
            "ticker.risk",
            {
                "ticker": "TEST",
                "mode": "active",
                "entry_price": 100.0,
                "entry_date": "2025-10-01",
                "stop_price": 94.0,
                "as_of": AS_OF,
            },
            runtime=runtime,
        )

        self.assertEqual(payload["data"]["current_price"], 150.0)
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "breached")
        self.assertEqual(payload["data"]["completed_price_path"]["breach_date"], breach_date.date().isoformat())
        self.assertEqual(payload["data"]["completed_price_path"]["breach_low"], 90.0)

    def test_active_risk_is_incomplete_when_provider_history_starts_after_the_stop(self) -> None:
        snapshot = price_snapshot()
        truncated = ProviderSnapshot(snapshot.data.loc["2025-11-03":], snapshot.meta)
        runtime = Runtime(price_history=lambda ticker, as_of: truncated)

        payload = execute(
            "ticker.risk",
            {
                "ticker": "TEST",
                "mode": "active",
                "entry_price": 100.0,
                "entry_date": "2025-10-01",
                "stop_price": 94.0,
                "as_of": AS_OF,
            },
            runtime=runtime,
        )

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "unavailable")
        self.assertIn("completed_price_path", payload["data"]["missing"])
        path_gap = next(item for item in payload["missing"] if item["id"] == "completed_price_path")
        self.assertEqual(path_gap["provider"], "fixture-prices")
        self.assertEqual(path_gap["reason"], "history_starts_after_stop_effective_date")

    def test_active_risk_applies_a_changed_stop_only_from_its_effective_date(self) -> None:
        snapshot = price_snapshot()
        frame = snapshot.data.copy()
        prior_breach_date = frame.loc["2025-10-01":"2025-10-31"].index[5]
        frame.loc[prior_breach_date, "Low"] = 93.0
        changed_stop = ProviderSnapshot(frame, snapshot.meta)
        runtime = Runtime(price_history=lambda ticker, as_of: changed_stop)

        payload = execute(
            "ticker.risk",
            {
                "ticker": "TEST",
                "mode": "active",
                "entry_price": 100.0,
                "entry_date": "2025-10-01",
                "stop_price": 94.0,
                "stop_effective_date": "2025-11-03",
                "as_of": AS_OF,
            },
            runtime=runtime,
        )

        self.assertEqual(payload["data"]["verdict"], "HOLD")
        self.assertEqual(payload["data"]["completed_price_path"]["state"], "clear")
        self.assertEqual(payload["data"]["completed_price_path"]["from"], "2025-11-03")

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
        # The capability reads its own price now. Leaving the hook undeclared sends this test
        # to the live provider, so it passes or fails on whether the machine has a network.
        prices = pd.DataFrame(
            {"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1_000_000},
            index=pd.bdate_range("2024-01-02", "2026-05-08"),
        )
        runtime = Runtime(
            fundamentals_evidence=lambda ticker, as_of, cik: snapshot,
            price_history=lambda ticker, as_of: ProviderSnapshot(
                prices,
                SnapshotMeta(provider="yfinance", retrieved_at=datetime(2026, 5, 11, tzinfo=timezone.utc), as_of=date(2026, 5, 8), coverage={"completed_only": True}),
            ),
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
        self.assertIs(payload["data"]["growth"]["earnings_deceleration"]["decelerated"], True)
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

            empty = execute("watchlist.show", {"as_of": AS_OF}, runtime=runtime)

            self.assertEqual(empty["data"]["records"], [])
            self.assertEqual(empty["as_of"]["date"], AS_OF)
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
