"""Behavior checks for provider contracts finviz."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest
from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.finviz import raw_snapshot
from tests.integration.providers._provider_fixtures import FIXTURES


class ProviderContractTests(unittest.TestCase):

    def test_finviz_snapshot_keeps_raw_evidence_and_retrieval_metadata(self) -> None:
        html = FIXTURES.joinpath("finviz.html").read_text()

        snapshot = raw_snapshot(fetch=lambda: html, retrieved_at=datetime(2026, 8, 17, 22, 0, tzinfo=timezone.utc))

        self.assertEqual(snapshot.data, html)
        self.assertEqual(snapshot.meta.provider, "finviz")
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 17))
        self.assertEqual(snapshot.meta.content_sha256, "0c4e35e3e294803c44616d1e617c78034790a41448819f488b7d2b5204a747ca")

    def test_finviz_uses_the_new_york_session_date_across_utc_midnight(self) -> None:
        html = FIXTURES.joinpath("finviz.html").read_text()

        snapshot = raw_snapshot(
            fetch=lambda: html,
            as_of="2026-08-17",
            retrieved_at=datetime(2026, 8, 18, 0, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 17))

    def test_finviz_refuses_to_label_an_intraday_page_as_the_prior_completed_session(self) -> None:
        calls = 0

        def fetch() -> str:
            nonlocal calls
            calls += 1
            return "unused"

        with self.assertRaises(ProviderUnavailable) as raised:
            raw_snapshot(
                fetch=fetch,
                as_of="2026-08-14",
                retrieved_at=datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(raised.exception.reason, "historical_snapshot_unavailable")
        self.assertEqual(calls, 0)

    def test_finviz_refuses_an_undated_request_while_a_session_is_running(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            raw_snapshot(
                fetch=lambda: self.fail("an open session must never reach the network"),
                retrieved_at=datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(raised.exception.reason, "historical_snapshot_unavailable")

    def test_finviz_serves_the_completed_session_overnight_and_discloses_the_later_observation(self) -> None:
        html = FIXTURES.joinpath("finviz.html").read_text()

        snapshot = raw_snapshot(
            fetch=lambda: html,
            as_of="2026-08-17",
            retrieved_at=datetime(2026, 8, 18, 4, 57, tzinfo=timezone.utc),
        )

        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 17))
        self.assertTrue(snapshot.meta.coverage["observed_after_session_close"])
        self.assertFalse(snapshot.meta.stale)

    def test_finviz_measures_the_observation_against_the_session_close_not_the_calendar_day(self) -> None:
        html = FIXTURES.joinpath("finviz.html").read_text()

        snapshot = raw_snapshot(
            fetch=lambda: html,
            as_of="2026-08-17",
            retrieved_at=datetime(2026, 8, 17, 21, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(snapshot.meta.coverage["observed_after_session_close"])
        self.assertEqual(snapshot.meta.coverage["seconds_after_session_close"], 3600)

    def test_finviz_serves_the_friday_session_through_the_weekend(self) -> None:
        html = FIXTURES.joinpath("finviz.html").read_text()

        snapshot = raw_snapshot(
            fetch=lambda: html,
            as_of="2026-08-14",
            retrieved_at=datetime(2026, 8, 15, 16, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertTrue(snapshot.meta.coverage["observed_after_session_close"])

    def test_finviz_refuses_a_session_older_than_the_last_completed_one(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            raw_snapshot(
                fetch=lambda: self.fail("an older session must never reach the network"),
                as_of="2026-08-13",
                retrieved_at=datetime(2026, 8, 18, 4, 57, tzinfo=timezone.utc),
            )

        self.assertEqual(raised.exception.reason, "historical_snapshot_unavailable")

    def test_external_provider_retries_once_before_returning_a_snapshot(self) -> None:
        html = FIXTURES.joinpath("finviz.html").read_text()
        attempts = 0

        def fetch() -> str:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("frozen boundary timeout")
            return html

        snapshot = raw_snapshot(fetch=fetch, retrieved_at=datetime(2026, 8, 17, 22, 0, tzinfo=timezone.utc))

        self.assertEqual(attempts, 2)
        self.assertEqual(snapshot.data, html)
