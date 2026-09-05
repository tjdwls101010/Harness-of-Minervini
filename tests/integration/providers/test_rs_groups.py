from __future__ import annotations

from datetime import date, datetime, timezone
from importlib import resources
import json
import unittest

from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.rs import (
    industry_ranking_snapshot,
    industry_top_snapshot,
    sector_ranking_snapshot,
    top_snapshot,
)


FIXTURES = resources.files("tests.fixtures.providers.rs")


class FakeRSGroups:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def dates(self) -> dict[str, str]:
        self.calls.append(("dates", (), {}))
        return self.payload["dates"]  # type: ignore[return-value]

    def sector_ranking(self, date: str | None = None) -> list[dict[str, object]]:
        self.calls.append(("sector_ranking", (), {"date": date}))
        return self.payload["sector_ranking"]  # type: ignore[return-value]

    def industry_ranking(self, date: str | None = None, sector: str | None = None) -> list[dict[str, object]]:
        self.calls.append(("industry_ranking", (), {"date": date, "sector": sector}))
        return self.payload["industry_ranking"]  # type: ignore[return-value]

    def industry_top(self, industry: str, n: int = 20, date: str | None = None) -> list[dict[str, object]]:
        self.calls.append(("industry_top", (industry,), {"n": n, "date": date}))
        return self.payload["industry_top"]  # type: ignore[return-value]

    def top(self, n: int = 20, date: str | None = None) -> list[dict[str, object]]:
        self.calls.append(("top", (), {"n": n, "date": date}))
        return self.payload["top"]  # type: ignore[return-value]


class RSGroupsProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(FIXTURES.joinpath("groups.json").read_text())

    def test_group_snapshots_request_the_exact_declared_date_and_preserve_audit_metadata(self) -> None:
        client = FakeRSGroups(self.payload)
        retrieved_at = datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)

        sectors = sector_ranking_snapshot("2026-08-12", client=client, package_version="0.5.0", retrieved_at=retrieved_at)
        industries = industry_ranking_snapshot("2026-08-12", sector="Technology", client=client, package_version="0.5.0", retrieved_at=retrieved_at)
        leaders = industry_top_snapshot("Semiconductors", "2026-08-12", n=2, client=client, package_version="0.5.0", retrieved_at=retrieved_at)
        top = top_snapshot("2026-08-12", n=2, client=client, package_version="0.5.0", retrieved_at=retrieved_at)

        self.assertEqual(client.calls, [
            ("dates", (), {}),
            ("sector_ranking", (), {"date": "2026-08-12"}),
            ("dates", (), {}),
            ("industry_ranking", (), {"date": "2026-08-12", "sector": "Technology"}),
            ("dates", (), {}),
            ("industry_top", ("Semiconductors",), {"n": 2, "date": "2026-08-12"}),
            ("dates", (), {}),
            ("top", (), {"n": 2, "date": "2026-08-12"}),
        ])
        self.assertEqual(sectors.data[0], {"sector": "Technology", "avg_rs": 92.4, "count": 18})
        self.assertEqual(industries.data[0]["industry"], "Semiconductors")
        self.assertEqual(leaders.data[0]["ticker"], "ACME")
        self.assertEqual(top.data[0]["ticker"], "LEAD")
        for snapshot in (sectors, industries, leaders, top):
            self.assertEqual(snapshot.meta.as_of, date(2026, 8, 12))
            self.assertEqual(snapshot.meta.provider_version, "0.5.0")
            self.assertEqual(snapshot.meta.coverage, {
                "kind": "library_declared_date_range",
                "first": "2026-08-01",
                "last": "2026-08-14",
                "universe": "library_not_declared",
                "complete": None,
            })
            self.assertEqual(snapshot.meta.retrieved_at, retrieved_at)
            self.assertFalse(snapshot.meta.stale)

    def test_group_snapshot_retries_each_external_library_method_once(self) -> None:
        class FlakyRS(FakeRSGroups):
            def __init__(self, payload: dict[str, object]) -> None:
                super().__init__(payload)
                self.attempts = 0

            def sector_ranking(self, date: str | None = None) -> list[dict[str, object]]:
                self.attempts += 1
                if self.attempts == 1:
                    raise TimeoutError("frozen boundary timeout")
                return super().sector_ranking(date=date)

        client = FlakyRS(self.payload)

        snapshot = sector_ranking_snapshot("2026-08-12", client=client, package_version="0.5.0")

        self.assertEqual(client.attempts, 2)
        self.assertEqual(snapshot.data[0]["sector"], "Technology")

    def test_group_snapshot_retries_declared_dates_once_before_using_them(self) -> None:
        class FlakyDatesRS(FakeRSGroups):
            def __init__(self, payload: dict[str, object]) -> None:
                super().__init__(payload)
                self.date_attempts = 0

            def dates(self) -> dict[str, str]:
                self.date_attempts += 1
                if self.date_attempts == 1:
                    raise TimeoutError("frozen date boundary timeout")
                return super().dates()

        client = FlakyDatesRS(self.payload)

        snapshot = industry_top_snapshot("Semiconductors", "2026-08-12", client=client, package_version="0.5.0")

        self.assertEqual(client.date_attempts, 2)
        self.assertEqual(snapshot.data[0]["ticker"], "ACME")

    def test_group_snapshot_reports_missing_dates_stale_data_schema_and_version_as_typed_unavailable(self) -> None:
        cases = [
            ("missing", {**self.payload, "dates": {}}, {}, "declared_date_range_unavailable"),
            ("stale", self.payload, {"as_of": None, "now": date(2026, 8, 17), "max_staleness_days": 1}, "stale_snapshot"),
            ("schema", {**self.payload, "sector_ranking": [{"sector": "Technology"}]}, {}, "invalid_sector_ranking_schema"),
            ("version", self.payload, {"package_version": "0.5.1"}, "unsupported_package_version"),
        ]

        for name, payload, kwargs, reason in cases:
            with self.subTest(name=name):
                client = FakeRSGroups(payload)
                call_kwargs = {"client": client, "package_version": "0.5.0", **kwargs}
                if kwargs.get("as_of") is None and name == "stale":
                    with self.assertRaises(ProviderUnavailable) as raised:
                        sector_ranking_snapshot(**call_kwargs)
                else:
                    with self.assertRaises(ProviderUnavailable) as raised:
                        sector_ranking_snapshot("2026-08-12", **call_kwargs)

                self.assertEqual(raised.exception.provider, "ibd-rs-rating")
                self.assertEqual(raised.exception.operation, "sector_ranking")
                self.assertEqual(raised.exception.reason, reason)

    def test_top_snapshot_reports_missing_stale_schema_and_version_as_typed_unavailable(self) -> None:
        cases = [
            ("missing", {**self.payload, "top": None}, {"as_of": "2026-08-12"}, "top_missing"),
            ("stale", self.payload, {"as_of": None, "now": date(2026, 8, 17), "max_staleness_days": 1}, "stale_snapshot"),
            ("schema", {**self.payload, "top": [{"ticker": "LEAD"}]}, {"as_of": "2026-08-12"}, "invalid_top_schema"),
            ("version", self.payload, {"as_of": "2026-08-12", "package_version": "0.5.1"}, "unsupported_package_version"),
        ]

        for name, payload, kwargs, reason in cases:
            with self.subTest(name=name):
                client = FakeRSGroups(payload)
                call_kwargs = {"client": client, "package_version": "0.5.0", **kwargs}
                with self.assertRaises(ProviderUnavailable) as raised:
                    top_snapshot(**call_kwargs)

                self.assertEqual(raised.exception.provider, "ibd-rs-rating")
                self.assertEqual(raised.exception.operation, "top")
                self.assertEqual(raised.exception.reason, reason)


if __name__ == "__main__":
    unittest.main()
