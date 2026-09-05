"""Behavior checks for operations."""

from __future__ import annotations

import unittest
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderUnavailable


class OperationCompositionTests(unittest.TestCase):

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
