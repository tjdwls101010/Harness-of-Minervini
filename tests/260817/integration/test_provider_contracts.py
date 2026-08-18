from __future__ import annotations

from datetime import date, datetime, timezone
from importlib import resources
import unittest

import pandas as pd

from scripts.minervini.providers import ProviderUnavailable, RequestThrottle, SnapshotMeta, fetch_with_one_retry, redact
from scripts.minervini.providers.finviz import raw_snapshot
from scripts.minervini.providers.nasdaq import (
    historical_security_master,
    parse_current_security_master,
)
from scripts.minervini.providers.rs import rating_snapshot
from scripts.minervini.providers.sec import select_filed_as_of
from scripts.minervini.providers.yfinance import completed_daily_bars


FIXTURES = resources.files("tests.260817.fixtures.providers")


class FakeTicker:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    def history(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(kwargs)
        return self.frame


class FakeClock:
    """A monotonic clock separating time the test passes from time a sleep costs."""

    def __init__(self, start: float, *, oversleep: float = 1.0) -> None:
        self.value = start
        self.waits: list[float] = []
        self.oversleep = oversleep

    def now(self) -> float:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value += seconds

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.value += seconds * self.oversleep


class FakeRS:
    def __init__(self) -> None:
        self.get_calls: list[tuple[str, str | None]] = []

    def dates(self) -> dict[str, str]:
        return {"first": "2026-08-01", "last": "2026-08-14"}

    def get(self, ticker: str, date: str | None = None) -> dict[str, object] | None:
        self.get_calls.append((ticker, date))
        if date == "2026-08-12":
            return {"ticker": ticker, "date": date, "rs_rating": 91}
        if date == "2026-08-14":
            return {"ticker": ticker, "date": date, "rs_rating": 93}
        return None


class ProviderContractTests(unittest.TestCase):
    def test_yfinance_never_returns_a_partial_or_future_daily_bar(self) -> None:
        index = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17"])
        ticker = FakeTicker(pd.DataFrame({"Close": [10.0, 11.0, 12.0, 99.0]}, index=index))

        snapshot = completed_daily_bars("ACME", as_of="2026-08-14", ticker=ticker)

        self.assertEqual(snapshot.data.index[-1].date().isoformat(), "2026-08-14")
        self.assertEqual(list(snapshot.data["Close"]), [10.0, 11.0, 12.0])
        self.assertEqual(ticker.calls[0]["end"], "2026-08-15")
        self.assertEqual(ticker.calls[0]["start"], "2023-08-10")
        self.assertFalse(ticker.calls[0]["auto_adjust"])
        self.assertFalse(ticker.calls[0]["actions"])
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertIsInstance(snapshot.meta, SnapshotMeta)

    def test_an_unfinished_final_bar_is_dropped_and_the_session_gap_is_declared(self) -> None:
        index = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-17"])
        frame = pd.DataFrame(
            {
                "Open": [10.0, 11.0, 12.0],
                "High": [10.5, 11.5, 12.5],
                "Low": [9.5, 10.5, 11.5],
                "Close": [10.2, 11.2, float("nan")],
                "Volume": [100, 200, 300],
            },
            index=index,
        )

        snapshot = completed_daily_bars("ACME", as_of="2026-08-17", ticker=FakeTicker(frame))

        self.assertEqual(snapshot.data.index[-1].date().isoformat(), "2026-08-14")
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertTrue(snapshot.meta.stale)
        self.assertEqual(snapshot.meta.coverage["requested_session"], "2026-08-17")
        self.assertEqual(snapshot.meta.coverage["last_completed_bar"], "2026-08-14")

    def test_a_complete_history_through_the_requested_session_is_not_stale(self) -> None:
        index = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-17"])
        frame = pd.DataFrame({"Close": [10.2, 11.2, 12.2]}, index=index)

        snapshot = completed_daily_bars("ACME", as_of="2026-08-17", ticker=FakeTicker(frame))

        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 17))
        self.assertFalse(snapshot.meta.stale)

    def test_an_infinite_price_is_not_a_completed_bar(self) -> None:
        index = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-17"])
        frame = pd.DataFrame({"Close": [10.2, 11.2, float("inf")]}, index=index)

        snapshot = completed_daily_bars("ACME", as_of="2026-08-17", ticker=FakeTicker(frame))

        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertTrue(snapshot.meta.stale)

    def test_a_repeated_session_never_truncates_the_history_to_the_wrong_bar(self) -> None:
        index = pd.to_datetime(["2026-08-13", "2026-08-14", "2026-08-14", "2026-08-17"])
        frame = pd.DataFrame({"Close": [10.2, 11.2, 11.3, float("nan")]}, index=index)

        snapshot = completed_daily_bars("ACME", as_of="2026-08-17", ticker=FakeTicker(frame))

        self.assertEqual(len(snapshot.data), 3)
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))

    def test_blank_rows_before_a_listing_started_are_trimmed_not_called_a_gap(self) -> None:
        index = pd.to_datetime(["2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"])
        frame = pd.DataFrame({"Close": [float("nan"), float("nan"), 11.2, 12.0]}, index=index)

        snapshot = completed_daily_bars("ACME", as_of="2026-08-14", ticker=FakeTicker(frame))

        self.assertEqual(len(snapshot.data), 2)
        self.assertEqual(snapshot.meta.as_of, date(2026, 8, 14))
        self.assertFalse(snapshot.meta.stale)

    def test_a_gap_inside_the_history_is_unavailable_rather_than_silently_compressed(self) -> None:
        index = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14"])
        frame = pd.DataFrame({"Close": [10.0, float("nan"), 12.0]}, index=index)

        with self.assertRaises(ProviderUnavailable) as raised:
            completed_daily_bars("ACME", as_of="2026-08-14", ticker=FakeTicker(frame))

        self.assertEqual(raised.exception.reason, "incomplete_daily_bars")

    def test_rs_uses_the_library_current_date_explicitly_and_never_backfills_history(self) -> None:
        current_client = FakeRS()
        current = rating_snapshot("ACME", client=current_client, package_version="0.5.0", as_of="2026-08-14")
        historical_client = FakeRS()
        historical = rating_snapshot("ACME", client=historical_client, package_version="0.5.0", as_of="2026-08-12")

        self.assertEqual(current_client.get_calls, [("ACME", "2026-08-14")])
        self.assertEqual(historical_client.get_calls, [("ACME", "2026-08-12")])
        self.assertEqual(current.data["rating"], 93)
        self.assertEqual(historical.data["rating"], 91)
        self.assertEqual(current.meta.provider_version, "0.5.0")
        self.assertEqual(current.meta.coverage["universe"], "library_not_declared")
        self.assertFalse(current.meta.stale)

    def test_rs_rejects_a_rating_that_is_too_stale_instead_of_using_a_proxy(self) -> None:
        client = FakeRS()

        with self.assertRaises(ProviderUnavailable) as raised:
            rating_snapshot("ACME", client=client, package_version="0.5.0", max_staleness_days=1, now=date(2026, 8, 17))

        self.assertEqual(raised.exception.provider, "ibd-rs-rating")
        self.assertEqual(raised.exception.reason, "stale_snapshot")

    def test_nasdaq_current_parser_marks_only_supported_common_and_adr_instruments_eligible(self) -> None:
        document = FIXTURES.joinpath("nasdaqlisted.txt").read_text()

        records = parse_current_security_master(document)
        by_symbol = {record.symbol: record for record in records}

        self.assertTrue(by_symbol["AAPL"].eligible)
        self.assertTrue(by_symbol["NIO"].eligible)
        self.assertTrue(by_symbol["NIO"].is_adr)
        self.assertFalse(by_symbol["TQQQ"].eligible)
        self.assertEqual(by_symbol["TQQQ"].exclusion_reason, "etf")
        self.assertFalse(by_symbol["SPACU"].eligible)
        self.assertEqual(by_symbol["SPACU"].exclusion_reason, "unit")

    def test_nasdaq_historical_security_master_is_honestly_unavailable(self) -> None:
        with self.assertRaises(ProviderUnavailable) as raised:
            historical_security_master("2026-08-12")

        self.assertEqual(raised.exception.reason, "historical_security_master_unavailable")

    def test_sec_selection_never_uses_a_filing_published_after_as_of(self) -> None:
        records = [
            {"value": 20, "filed_at": "2026-08-10", "form": "10-Q"},
            {"value": 30, "filed_at": "2026-08-15", "form": "10-Q"},
        ]

        selected = select_filed_as_of(records, "2026-08-12")

        self.assertEqual(selected, {"value": 20, "filed_at": "2026-08-10", "form": "10-Q"})

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

    def test_a_boundary_failure_preserves_the_underlying_error_for_diagnosis(self) -> None:
        def fetch() -> str:
            raise ConnectionError("Failed to connect to the Neon Data API: certificate verify failed")

        with self.assertRaises(ProviderUnavailable) as raised:
            fetch_with_one_retry("ibd-rs-rating", "dates", fetch, sleep=lambda _: None)

        self.assertEqual(raised.exception.reason, "request_failed")
        self.assertIn("ConnectionError", raised.exception.detail)
        self.assertIn("certificate verify failed", raised.exception.detail)

    def test_a_preserved_failure_never_carries_a_credential_or_an_operator_email(self) -> None:
        def fetch() -> str:
            raise RuntimeError(
                "401 for https://api.example.com/v1/rs?token=sk-live-abcdef123456 "
                "with Authorization: Bearer eyJhbGciOi and User-Agent: Acme analyst@example.com"
            )

        with self.assertRaises(ProviderUnavailable) as raised:
            fetch_with_one_retry("ibd-rs-rating", "dates", fetch, sleep=lambda _: None)

        detail = raised.exception.detail
        self.assertNotIn("sk-live-abcdef123456", detail)
        self.assertNotIn("eyJhbGciOi", detail)
        self.assertNotIn("analyst@example.com", detail)
        self.assertIn("RuntimeError", detail)
        self.assertIn("https://api.example.com/v1/rs", detail)

    def test_redaction_covers_the_shapes_a_credential_actually_arrives_in(self) -> None:
        leaks = [
            ("/v1/token/sk-live-abc", "sk-live-abc"),
            ('{"apikey":"sk-live-abc","token":"json-secret"}', "sk-live-abc"),
            ('{"apikey":"sk-live-abc","token":"json-secret"}', "json-secret"),
            ("Cookie: session=deadbeef", "deadbeef"),
            ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
            ("api_key=secretvalue", "secretvalue"),
            ("contact analyst@example.com", "analyst@example.com"),
        ]

        for message, secret in leaks:
            with self.subTest(message=message):
                self.assertNotIn(secret, redact(message))

    def test_a_directly_constructed_boundary_failure_is_redacted_too(self) -> None:
        error = ProviderUnavailable("sec", "request_failed", detail="User-Agent: Acme analyst@example.com")

        self.assertNotIn("analyst@example.com", error.detail)

    def test_the_retry_waits_before_hitting_a_rate_limited_boundary_again(self) -> None:
        waits: list[float] = []
        attempts = 0

        def fetch() -> str:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("first attempt")
            return "recovered"

        result = fetch_with_one_retry("sec", "company_tickers", fetch, backoff_seconds=0.25, sleep=waits.append)

        self.assertEqual(result, "recovered")
        self.assertEqual(waits, [0.25])

    def test_a_throttled_boundary_spaces_consecutive_requests(self) -> None:
        clock = FakeClock(100.0)
        throttle = RequestThrottle(0.15, monotonic=clock.now, sleep=clock.sleep)

        throttle.wait()
        clock.tick(0.05)
        throttle.wait()

        self.assertEqual(len(clock.waits), 1)
        self.assertAlmostEqual(clock.waits[0], 0.10)

    def test_a_throttled_boundary_never_waits_when_the_gap_already_passed(self) -> None:
        clock = FakeClock(100.0)
        throttle = RequestThrottle(0.15, monotonic=clock.now, sleep=clock.sleep)

        throttle.wait()
        clock.tick(0.9)
        throttle.wait()

        self.assertEqual(clock.waits, [])

    def test_a_throttled_boundary_rereads_the_clock_after_an_oversleep(self) -> None:
        clock = FakeClock(100.0, oversleep=4.0)
        throttle = RequestThrottle(0.15, monotonic=clock.now, sleep=clock.sleep)

        throttle.wait()
        clock.tick(0.05)
        throttle.wait()
        throttle.wait()

        # Assuming the requested delay rather than rereading would credit the
        # oversleep to the interval and let the third request go out immediately.
        self.assertEqual(len(clock.waits), 2)
        self.assertAlmostEqual(clock.waits[1], 0.15)


if __name__ == "__main__":
    unittest.main()
