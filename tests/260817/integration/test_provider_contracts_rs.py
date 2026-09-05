"""Behavior checks for provider contracts rs."""

from __future__ import annotations

from datetime import date
import unittest
from scripts.minervini.providers import ProviderUnavailable
from scripts.minervini.providers.rs import rating_snapshot
from ._provider_fixtures import FakeRS


class ProviderContractTests(unittest.TestCase):

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
