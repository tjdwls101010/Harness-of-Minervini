"""Behavior checks for operations risk."""

from __future__ import annotations

import unittest
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot
from tests.integration.operations._operation_fixtures import AS_OF, price_snapshot, stale_price_snapshot


class OperationCompositionTests(unittest.TestCase):

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
