"""A breach that is already terminal must not send the harness looking for prices."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

import numpy as np
import pandas as pd

from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot, ProviderUnavailable, SnapshotMeta


AS_OF = "2025-12-31"
POSITION = {"ticker": "TEST", "mode": "active", "entry_price": 100.0, "entry_date": "2025-10-01", "as_of": AS_OF}


class TerminalBreachTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[str] = []

        def refuse(ticker: str, as_of: str):
            self.calls.append(ticker)
            raise ProviderUnavailable(provider="fixture-prices", reason="unavailable", retryable=False)

        self.runtime = Runtime(price_history=refuse)

    def run_risk(self, **request: object) -> dict:
        return execute("ticker.risk", {**POSITION, **request}, runtime=self.runtime)

    def test_an_authorized_live_stop_breach_needs_no_daily_history(self) -> None:
        payload = self.run_risk(stop_price=94.0, live_stop_check=True, live_stop={"state": "triggered", "partial_session": True})

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(self.calls, [])
        self.assertEqual(payload["status"], "ok")

    def test_an_asserted_invalidation_trigger_needs_no_daily_history(self) -> None:
        payload = self.run_risk(invalidation={"price": 94.0, "condition": "completed close below the base low", "state": "triggered"})

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(self.calls, [])
        self.assertEqual(payload["status"], "ok")

    def test_an_unresolved_position_still_asks_the_provider(self) -> None:
        payload = self.run_risk(stop_price=94.0)

        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")
        self.assertEqual(self.calls, ["TEST"])


class AuditPreconditionTests(unittest.TestCase):
    def test_the_audit_depends_on_the_entry_date_not_the_entry_price(self) -> None:
        calls: list[str] = []

        def refuse(ticker: str, as_of: str):
            calls.append(ticker)
            raise ProviderUnavailable(provider="fixture-prices", reason="unavailable", retryable=False)

        request = {key: value for key, value in POSITION.items() if key != "entry_price"}
        execute("ticker.risk", {**request, "stop_price": 94.0}, runtime=Runtime(price_history=refuse))

        self.assertEqual(calls, ["TEST"])


class RoutingAgreesWithTheReducerTests(unittest.TestCase):
    """The operation must not decide breach or plan on its own terms."""

    def setUp(self) -> None:
        self.calls: list[str] = []

    def refuse(self, ticker: str, as_of: str):
        self.calls.append(ticker)
        raise ProviderUnavailable(provider="fixture-prices", reason="unavailable", retryable=False)

    def run_risk(self, **request: object) -> dict:
        return execute("ticker.risk", {**POSITION, **request}, runtime=Runtime(price_history=self.refuse))

    def test_an_untriggered_completed_stop_is_not_a_settled_breach(self) -> None:
        payload = self.run_risk(stop_price=94.0, completed_stop={"state": "not_triggered"})

        self.assertEqual(self.calls, ["TEST"])
        self.assertEqual(payload["data"]["verdict"], "INCOMPLETE")

    def test_a_triggered_stop_event_is_a_settled_breach(self) -> None:
        payload = self.run_risk(stop_price=94.0, stop_event={"state": "triggered"})

        self.assertEqual(self.calls, [])
        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(payload["status"], "ok")

    def test_a_state_only_invalidation_is_not_a_plan_worth_fetching_for(self) -> None:
        payload = self.run_risk(invalidation={"state": "triggered"})

        self.assertEqual(self.calls, [])
        self.assertEqual(payload["status"], "needs_input")
        self.assertIn("stop_or_invalidation", payload["data"]["missing"])


class SuppliedPathBreachTests(unittest.TestCase):
    """A breach the caller already supplied must not be overwritten by a fresh fetch."""

    def setUp(self) -> None:
        self.calls: list[str] = []

    def clear_history(self, ticker: str, as_of: str):
        self.calls.append(ticker)
        values = np.linspace(50, 150, 260)
        index = pd.bdate_range(end=AS_OF, periods=len(values))
        close = pd.Series(values, index=index)
        frame = pd.DataFrame(
            {"Open": close * 0.995, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(len(close), 1_000_000)},
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

    def run_risk(self, path: dict) -> dict:
        return execute(
            "ticker.risk",
            {**POSITION, "stop_price": 94.0, "completed_price_path": path},
            runtime=Runtime(price_history=self.clear_history),
        )

    def test_a_padded_breach_state_is_still_a_breach(self) -> None:
        payload = self.run_risk({"state": " breached "})

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(self.calls, [])

    def test_a_breach_reported_under_status_is_still_a_breach(self) -> None:
        payload = self.run_risk({"status": "breached"})

        self.assertEqual(payload["data"]["verdict"], "SELL")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
