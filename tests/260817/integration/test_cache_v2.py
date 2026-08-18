from __future__ import annotations

import json
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from scripts.minervini.cache import ProviderCache, resolve_cache_dir
from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta
from scripts.minervini.providers.nasdaq import SecurityRecord


class ProviderCacheIntegrationTests(unittest.TestCase):
    def test_call_uses_a_session_scoped_key_and_normalized_params(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(root=Path(directory))
            calls: list[str] = []

            def fetch() -> ProviderSnapshot[dict[str, str]]:
                calls.append("fetch")
                return ProviderSnapshot(
                    {"ticker": "AAPL"},
                    SnapshotMeta(
                        provider="fixture",
                        retrieved_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
                        as_of=date(2026, 8, 14),
                    ),
                )

            first = cache.call(
                "fixture",
                "daily_bars",
                {"ticker": " aapl ", "fields": ["Close", "Volume"]},
                "2026-08-14",
                fetch,
            )
            duplicate = cache.call(
                "fixture",
                "daily_bars",
                {"fields": ["Close", "Volume"], "ticker": "AAPL"},
                "2026-08-14",
                fetch,
            )
            other_session = cache.call(
                "fixture",
                "daily_bars",
                {"ticker": "AAPL", "fields": ["Close", "Volume"]},
                "2026-08-15",
                fetch,
            )

            self.assertEqual(first.data, {"ticker": "AAPL"})
            self.assertEqual(duplicate.data, {"ticker": "AAPL"})
            self.assertEqual(other_session.data, {"ticker": "AAPL"})
            self.assertEqual(calls, ["fetch", "fetch"])

    def test_entries_written_before_the_partial_bar_fix_are_never_served(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(root=Path(directory))
            calls: list[str] = []

            def fetch() -> ProviderSnapshot[dict[str, str]]:
                calls.append("fetch")
                return ProviderSnapshot(
                    {"ticker": "AAOI"},
                    SnapshotMeta(provider="yfinance", retrieved_at=datetime(2026, 8, 18, tzinfo=timezone.utc), as_of=date(2026, 8, 14)),
                )

            cache.call("yfinance", "ticker.qualify:daily_bars", {"ticker": "AAOI"}, "2026-08-17", fetch)
            entry = next(cache.path.glob("*.json"))
            document = json.loads(entry.read_text())
            document["cache_schema_version"] = "1"
            entry.write_text(json.dumps(document), encoding="utf-8")

            cache.call("yfinance", "ticker.qualify:daily_bars", {"ticker": "AAOI"}, "2026-08-17", fetch)

            self.assertEqual(calls, ["fetch", "fetch"])

    def test_resolve_cache_dir_uses_repo_state_by_default_and_environment_override(self) -> None:
        root = Path("/repository")

        self.assertEqual(resolve_cache_dir(root=root, environ={}), root / ".state" / "cache")
        self.assertEqual(
            resolve_cache_dir(root=root, environ={"MINERVINI_CACHE_DIR": "/tmp/minervini-cache"}),
            Path("/tmp/minervini-cache"),
        )

    def test_call_restores_ohlcv_dataframe_and_snapshot_metadata(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "cache" / "ohlcv.json"
        source = json.loads(fixture.read_text(encoding="utf-8"))
        frame = pd.DataFrame(source["rows"], columns=source["columns"])
        frame.index = pd.DatetimeIndex(source["index"])
        frame["Volume"] = frame["Volume"].astype("int64")
        snapshot = ProviderSnapshot(
            frame,
            SnapshotMeta(
                provider="fixture-prices",
                retrieved_at=datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc),
                as_of=date(2026, 8, 14),
                provider_version="1.2.3",
                coverage={"interval": "1d", "completed_only": True},
                content_sha256="fixture-sha",
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(root=Path(directory))
            cache.call("fixture-prices", "daily_bars", {"ticker": "AAPL"}, "2026-08-14", lambda: snapshot)
            restored = cache.call(
                "fixture-prices",
                "daily_bars",
                {"ticker": "AAPL"},
                "2026-08-14",
                lambda: self.fail("a valid cache entry must be restored"),
            )

        pd.testing.assert_frame_equal(restored.data, frame)
        self.assertEqual(restored.meta, snapshot.meta)

    def test_no_cache_bypasses_existing_entries_without_writing_a_new_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(root=Path(directory))
            calls: list[str] = []

            def fetch() -> ProviderSnapshot[dict[str, str]]:
                calls.append("fetch")
                return ProviderSnapshot(
                    {"call": str(len(calls))},
                    SnapshotMeta("fixture", datetime(2026, 8, 17, tzinfo=timezone.utc), date(2026, 8, 14)),
                )

            cached = cache.call("fixture", "profile", {"ticker": "AAPL"}, "2026-08-14", fetch)
            bypassed = cache.call("fixture", "profile", {"ticker": "AAPL"}, "2026-08-14", fetch, no_cache=True)
            after_bypass = cache.call("fixture", "profile", {"ticker": "AAPL"}, "2026-08-14", fetch)

            self.assertEqual((cached.data, bypassed.data, after_bypass.data), ({"call": "1"}, {"call": "2"}, {"call": "1"}))
            self.assertEqual(calls, ["fetch", "fetch"])

    def test_corrupt_or_schema_mismatched_entry_is_a_recoverable_miss(self) -> None:
        for invalid_document in ("{not-json", json.dumps({"cache_schema_version": "obsolete"})):
            with self.subTest(invalid_document=invalid_document), tempfile.TemporaryDirectory() as directory:
                cache = ProviderCache(root=Path(directory))
                calls: list[str] = []

                def fetch() -> ProviderSnapshot[dict[str, str]]:
                    calls.append("fetch")
                    return ProviderSnapshot(
                        {"call": str(len(calls))},
                        SnapshotMeta("fixture", datetime(2026, 8, 17, tzinfo=timezone.utc), date(2026, 8, 14)),
                    )

                cache.call("fixture", "profile", {"ticker": "AAPL"}, "2026-08-14", fetch)
                entry = next((Path(directory) / ".state" / "cache").glob("*.json"))
                entry.write_text(invalid_document, encoding="utf-8")
                recovered = cache.call("fixture", "profile", {"ticker": "AAPL"}, "2026-08-14", fetch)
                restored = cache.call(
                    "fixture",
                    "profile",
                    {"ticker": "AAPL"},
                    "2026-08-14",
                    lambda: self.fail("recovered entry must be reusable"),
                )

                self.assertEqual(calls, ["fetch", "fetch"])
                self.assertEqual(recovered.data, {"call": "2"})
                self.assertEqual(restored.data, {"call": "2"})

    def test_explicit_ttl_refreshes_current_snapshots_but_fixed_sessions_remain_stable(self) -> None:
        now = [datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)]
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(root=Path(directory), now=lambda: now[0])
            calls: list[str] = []

            def fetch() -> ProviderSnapshot[dict[str, str]]:
                calls.append("fetch")
                return ProviderSnapshot(
                    {"call": str(len(calls))},
                    SnapshotMeta("fixture", now[0], date(2026, 8, 14)),
                )

            first = cache.call("fixture", "current_profile", {"ticker": "AAPL"}, "2026-08-14", fetch, ttl_seconds=60)
            now[0] += timedelta(seconds=59)
            within_ttl = cache.call("fixture", "current_profile", {"ticker": "AAPL"}, "2026-08-14", fetch, ttl_seconds=60)
            now[0] += timedelta(seconds=2)
            refreshed = cache.call("fixture", "current_profile", {"ticker": "AAPL"}, "2026-08-14", fetch, ttl_seconds=60)
            now[0] += timedelta(days=7)
            fixed = cache.call("fixture", "fixed_daily_bars", {"ticker": "AAPL"}, "2026-08-14", fetch)
            stable = cache.call("fixture", "fixed_daily_bars", {"ticker": "AAPL"}, "2026-08-14", fetch)

            self.assertEqual((first.data, within_ttl.data, refreshed.data), ({"call": "1"}, {"call": "1"}, {"call": "2"}))
            self.assertEqual((fixed.data, stable.data), ({"call": "3"}, {"call": "3"}))
            self.assertEqual(calls, ["fetch", "fetch", "fetch"])

    def test_call_round_trips_json_values_without_reserving_payload_keys(self) -> None:
        snapshot = ProviderSnapshot(
            {"kind": "dataframe", "rows": ["ordinary", "json"], "nested": {"as_of": "not-a-date"}},
            SnapshotMeta("fixture", datetime(2026, 8, 17, tzinfo=timezone.utc), None),
        )
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(root=Path(directory))
            cache.call("fixture", "payload", {}, "2026-08-14", lambda: snapshot)
            restored = cache.call(
                "fixture",
                "payload",
                {},
                "2026-08-14",
                lambda: self.fail("JSON payload should be restored"),
            )

        self.assertEqual(restored, snapshot)

    def test_call_round_trips_security_master_records_without_pickle(self) -> None:
        records = [
            SecurityRecord(
                instrument_id="nasdaq-trader:NASDAQ:AAPL",
                symbol="AAPL",
                exchange="NASDAQ",
                security_name="Apple Inc. Common Stock",
                instrument_type="common_stock",
                is_adr=False,
                eligible=True,
                exclusion_reason=None,
            )
        ]
        snapshot = ProviderSnapshot(
            records,
            SnapshotMeta("nasdaq", datetime(2026, 8, 17, tzinfo=timezone.utc), date(2026, 8, 17)),
        )
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(root=Path(directory))
            cache.call("nasdaq", "security_master", {}, "2026-08-14", lambda: snapshot)
            restored = cache.call(
                "nasdaq",
                "security_master",
                {},
                "2026-08-14",
                lambda: self.fail("security master should be restored from JSON"),
            )

        self.assertEqual(restored, snapshot)

    def test_concurrent_misses_leave_one_complete_json_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(root=Path(directory))
            barrier = threading.Barrier(4)
            failures: list[BaseException] = []

            def request() -> None:
                try:
                    barrier.wait()
                    cache.call(
                        "fixture",
                        "concurrent",
                        {"ticker": "AAPL"},
                        "2026-08-14",
                        lambda: ProviderSnapshot(
                            {"value": "complete"},
                            SnapshotMeta("fixture", datetime(2026, 8, 17, tzinfo=timezone.utc), date(2026, 8, 14)),
                        ),
                    )
                except BaseException as error:  # Thread failures must reach the test assertion.
                    failures.append(error)

            threads = [threading.Thread(target=request) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(failures, [])
            entries = list((Path(directory) / ".state" / "cache").glob("*.json"))
            self.assertEqual(len(entries), 1)
            self.assertEqual(json.loads(entries[0].read_text(encoding="utf-8"))["snapshot"]["data"]["value"], {"value": "complete"})
            self.assertEqual(list(entries[0].parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
