"""Behavior checks for provider contracts."""

from __future__ import annotations

import unittest
from scripts.minervini.providers import ProviderUnavailable, RequestThrottle, fetch_with_one_retry, redact
from ._provider_fixtures import FakeClock


class ProviderContractTests(unittest.TestCase):

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
